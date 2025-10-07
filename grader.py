#!/usr/bin/env python3
import os
import re
import csv
import json
import time
from collections import Counter

from dotenv import load_dotenv
load_dotenv()


import requests
import gspread
from google.oauth2.service_account import Credentials


# ------------------------------
# 1) CONFIG — EDIT THESE
# ------------------------------
# Google Sheets (your grading sheet)
SERVICE_ACCOUNT_FILE = "service_account.json"
SPREADSHEET_ID = "14Tqt3uJgOhP3sLasf8c0eSCv70uwdjE5MBSRn0CyyhI"
TAB_NAME = "Sheet1"

# (Optional) A second sheet with past answers / notes to mine common mistakes
# If you have one, put its ID here; if not, leave blank.
HISTORICAL_SHEET_ID = os.getenv("COMMON_MISTAKES_SHEET_ID", "").strip()  # "" = disabled

# University LLM
LLM_URL   = "https://chat.binghamton.edu/api/chat/completions"
LLM_MODEL = "gpt-oss:20b"          # you can try: "llama3.1:70B", "mixtral:8x22b-instruct", etc.
LLM_KEY = os.getenv("LLM_KEY")
print("Loaded LLM_KEY:", os.getenv("LLM_KEY"))
  # if you prefer env var, replace with: os.getenv("BING_API_KEY")
LLM_TIMEOUT = 60

# Per-question max points (you said each is 0.5 and total 2.0)
MAX_PER_Q = 0.5

# Canonical answers (from your assignment)
CORRECT = {
    "Bits answer":    "01010111 01101000 01100001 01110100 00100111 01110011 00100000 01110101 01110000 00111111",
    "Decimal answer": "087 104 097 116 039 115 032 117 112 063",
    "Hex answer":     "57 68 61 74 27 73 20 75 70 3F",
    "Base64 answer":  "V2hhdCdzIHVwPw==",
}

# ------------------------------
# 2) GOOGLE SHEETS SETUP
# ------------------------------
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(TAB_NAME)
rows = sheet.get_all_values()
header = rows[0]
students = rows[1:]
print(f"✅ Connected to sheet: {sheet.title}")
print("Headers:", header)

# Create / find output columns
existing = {h for h in header}
col_feedback = header.index("Feedback") + 1 if "Feedback" in existing else len(header) + 1
col_grade    = header.index("Grade") + 1    if "Grade"    in existing else len(header) + (1 if "Feedback" in existing else 2)
if "Feedback" not in existing: sheet.update_cell(1, col_feedback, "Feedback")
if "Grade" not in existing:    sheet.update_cell(1, col_grade, "Grade")

# ------------------------------
# 3) OPTIONAL: LEARN COMMON MISTAKES FROM A HISTORICAL SHEET
# ------------------------------
def mine_common_mistakes_from_sheet(sheet_id: str) -> list[str]:
    if not sheet_id:
        return []
    try:
        ws = gc.open_by_key(sheet_id).sheet1
        data = ws.get_all_values()
        # Very light mining: count short “mistake tags” in the last column(s)
        flat = " ".join([" ".join(r) for r in data[1:]])
        tags = []
        # Look for obvious patterns we care about:
        if re.search(r"\bpadding\b", flat, re.I):    tags.append("base64 padding/==' missing")
        if re.search(r"\bCRLF\b|\bnewline\b", flat, re.I): tags.append("extra newline (CRLF) in Base64")
        if re.search(r"\bbytes? missing\b|\bincomplete\b", flat, re.I): tags.append("incomplete byte sequence in Bits")
        if re.search(r"\bspacing\b|\bspaces\b", flat, re.I): tags.append("spacing/formatting differences")
        if re.search(r"\bleading zero\b", flat, re.I): tags.append("leading-zero formatting in Decimal/Hex")
        # de-dup, keep top few
        seen = []
        for t in tags:
            if t not in seen: seen.append(t)
        return seen[:6]
    except Exception as e:
        print(f"⚠️  Could not read historical sheet: {e}")
        return []

COMMON_MISTAKES_HINTS = mine_common_mistakes_from_sheet(HISTORICAL_SHEET_ID)

# ------------------------------
# 4) LLM CALL (JSON-only reply)
# ------------------------------
def ask_llm_json(prompt: str) -> dict:
    headers = {"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"}
    payload = {"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]}

    try:
        r = requests.post(LLM_URL, headers=headers, json=payload, timeout=LLM_TIMEOUT)
        if r.status_code != 200:
            return {"error": f"{r.status_code} {r.text[:500]}"}
        text = r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return {"error": str(e)}

    # Try to extract a JSON object
    m = re.search(r"\{.*\}", text, re.S)
    block = m.group(0) if m else text
    try:
        data = json.loads(block)
        return data
    except Exception:
        # Fallback: permissive parse for "Score: X" lines
        score = 0.0
        m2 = re.search(r"score\s*[:=]\s*([0-9]*\.?[0-9]+)", text, re.I)
        if m2:
            try: score = float(m2.group(1))
            except: pass
        fb = re.search(r"feedback\s*[:=]\s*(.+)", text, re.I)
        feedback = fb.group(1).strip() if fb else text.strip()
        return {"score": score, "feedback": feedback, "raw": text}

# ------------------------------
# 5) RUBRIC + PROMPT
# ------------------------------
def build_prompt(q_name: str, student_ans: str, correct_ans: str) -> str:
    return f"""
You are a **very generous, fair, and human-like** grader for a university course.  
Always assume good intent from the student and give the **highest reasonable score** when in doubt.


Your goal is to evaluate how *close* the student's answer is to the correct one, using reasoning — not strict matching.

Grading principles:
1. Be **generous**: reward understanding even when formatting or small syntax differs.
2. Treat answers as *equivalent* if they differ only by whitespace, line breaks, capitalization, or missing padding symbols like '=='.
3. Grade proportionally to how close the student's answer is to the correct one, not just exact matches.
   - Small differences (1–2 wrong characters, spacing, or minor formatting errors) should still earn 80–90% of the credit.
   - If the answer shows clear understanding but misses a small detail, be generous (≈0.4–0.45 for a 0.5-point question).
   - If large parts are missing but the intent is correct, partial credit (≈0.2–0.3) is fine.
   - Only assign 0.0 if the answer is clearly unrelated or blank.
4. Consider typical “copy/paste” or encoding artifacts (like newlines, padding `==`, or CRLF) as minor issues, not full errors.
5. Strive for internal consistency — answers with similar correctness should get similar scores.
6. Always use reasoning, not string comparison — imagine how a human professor would grade fairly.
7. Respond only in this JSON format, no extra text:
8. Ensure **consistency**: if two answers contain the same type of mistake (for example, missing padding, newline errors, or partial sequences), they should receive similar scores.


{{
  "score": <number between 0.0 and 0.5>,
  "feedback": "<brief natural explanation, 1–2 sentences + score>",
  "mistake_tag": "<short label like 'minor copy error', 'incomplete', 'exact'>"
}}

Question: {q_name}
Correct answer: {correct_ans}
Student answer: {student_ans}
"""


# ------------------------------
# 6) MAIN LOOP
# ------------------------------
mistake_counter = Counter()

for r_idx, row in enumerate(students, start=2):
    student_id = row[0] if row else f"Row{r_idx}"
    print(f"\n👩‍🎓 Grading {student_id}")
    total = 0.0
    feedback_parts = []

    for q_name, correct in CORRECT.items():
        if q_name not in header:
            continue
        cidx = header.index(q_name)
        student_ans = row[cidx].strip() if cidx < len(row) else ""

        prompt = build_prompt(q_name, student_ans, correct)
        result = ask_llm_json(prompt)

        if "error" in result:
            print(f"  {q_name}: ❌ {result['error']}")
            feedback_parts.append(f"{q_name}: API error")
            continue

        score = float(result.get("score", 0.0))
        fb = str(result.get("feedback", "")).strip()
        tag = str(result.get("mistake_tag", "")).strip() or "unspecified"
        print(f"  {q_name}: score={score:.2f}  tag={tag}  fb={fb}")

        total += max(0.0, min(MAX_PER_Q, score))
        feedback_parts.append(f"{q_name} ({score:.2f}): {fb}")
        mistake_counter[tag] += 1

    # Write to sheet
    sheet.update_cell(r_idx, col_feedback, " | ".join(feedback_parts))
    sheet.update_cell(r_idx, col_grade, f"{total:.2f}")
    # small pause to be nice to Sheets API
    time.sleep(0.4)

# Optional CSV log
with open("grading_log.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Student ID", "Grade", "Feedback"])
    for r_idx, row in enumerate(students, start=2):
        sid = row[0] if row else f"Row{r_idx}"
        g = sheet.cell(r_idx, col_grade).value
        fb = sheet.cell(r_idx, col_feedback).value
        w.writerow([sid, g, fb])

print("\n✅ Done. Wrote Grade + Feedback. Most common mistake tags this run:")
for tag, cnt in mistake_counter.most_common()[:10]:
    print(f"  • {tag}: {cnt}")
