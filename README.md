# 🧠 LLM Assignment Grader

This project connects to **Google Sheets** and automatically grades assignment answers using an **LLM** (Large Language Model).  
It provides **partial credit**, **feedback**, and writes everything back into the Google Sheet.

---

## ⚙️ Setup Guide

### 🪄 1️⃣ Clone the Repository
```bash
git clone https://github.com/ITAI808/llm-grader-project1-updated.git
cd llm-grader


⚙️ 2️⃣ Install Dependencies
pip install -r requirements.txt



📄 3️⃣ Google Sheets Access

You will receive the file service_account.json separately.
Simply place it in the root directory of the project (the same folder as grader.py).


🔑 4️⃣ LLM Access

Get an API key from your LLM provider

Create a file named .env in the project root, and add the following line:

LLM_KEY=your_api_key_here

▶️ 5️⃣ Run the Grader
python3 grader.py