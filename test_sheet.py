import gspread
from google.oauth2.service_account import Credentials

# Use the exact filename of your JSON key
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
client = gspread.authorize(creds)

# Replace this with your real Google Sheet ID
SPREADSHEET_ID = "14Tqt3uJgOhP3sLasf8c0eSCv70uwdjE5MBSRn0CyyhI"
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

print("✅ Connected to sheet:", sheet.title)
print("First row:", sheet.row_values(1))
