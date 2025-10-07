from dotenv import load_dotenv
import os

load_dotenv()
print("LLM_KEY =", os.getenv("LLM_KEY"))

