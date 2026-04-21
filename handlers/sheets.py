import os
import json
import base64
from datetime import datetime
import gspread
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER = ["Tanggal", "Nama", "Level", "Ranger", "Benar", "Total Soal", "Poin", "Jam Selesai"]

def get_sheets_client():
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
    if creds_b64:
        creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            creds_json, scopes=SCOPES
        )
    else:
        credentials = service_account.Credentials.from_service_account_file(
            "credentials.json", scopes=SCOPES
        )
    return gspread.authorize(credentials)

def log_session(ranger, correct, total, points):
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("SPREADSHEET_ID not set, skipping sheets log")
        return

    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(spreadsheet_id)

        try:
            sheet = spreadsheet.worksheet("Log Belajar")
        except gspread.exceptions.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet("Log Belajar", rows=1000, cols=10)
            sheet.append_row(HEADER)

        # Pastikan header ada jika sheet kosong
        existing = sheet.get_all_values()
        if not existing:
            sheet.append_row(HEADER)

        now = datetime.now()
        row = [
            now.strftime("%Y-%m-%d"),
            ranger["name"],
            ranger["level"],
            ranger["ranger"],
            correct,
            total,
            points,
            now.strftime("%H:%M"),
        ]
        sheet.append_row(row)
        print(f"Sheets: logged session for {ranger['name']} — {correct}/{total}, {points} poin")

    except Exception as e:
        print(f"Sheets logging error: {e}")
