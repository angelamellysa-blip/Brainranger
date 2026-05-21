import os
import json
import base64
from datetime import datetime, date, timedelta
import gspread
from google.oauth2 import service_account

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

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

def _get_or_create_sheet(spreadsheet, name, rows=1000, cols=15):
    try:
        return spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(name, rows=rows, cols=cols)

def _ensure_header(sheet, header):
    existing = sheet.get_all_values()
    if not existing:
        sheet.append_row(header)
    elif existing[0] != header:
        sheet.insert_row(header, 1)

def _safe_int(val):
    try:
        return int(str(val).replace(",", ""))
    except Exception:
        return 0

def _rank_label(total_poin):
    p = _safe_int(total_poin)
    if p >= 1000: return "👑 Ranger Legendaris"
    if p >= 601:  return "💎 Ranger Elite"
    if p >= 301:  return "🔥 Ranger Tangguh"
    if p >= 101:  return "⚡ Ranger Aktif"
    return "🌱 Ranger Cadet"

# ── Public: dipanggil dari pomodoro.py ───────────────────
def log_session(ranger, correct, total, points, streak=0, longest_streak=0):
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("SPREADSHEET_ID not set, skipping sheets log")
        return

    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        now = datetime.now()
        pct = round((correct / total * 100) if total > 0 else 0, 1)

        # ── Tab 1: Log Harian ─────────────────────────
        sheet_log = _get_or_create_sheet(spreadsheet, "Log Harian")
        header_log = [
            "Tanggal", "Nama", "Ranger", "Level",
            "Benar", "Total Soal", "% Benar", "Poin", "Streak", "Jam Selesai"
        ]
        _ensure_header(sheet_log, header_log)
        sheet_log.append_row([
            now.strftime("%Y-%m-%d"),
            ranger["name"],
            ranger["ranger"],
            ranger["level"],
            correct,
            total,
            f"{pct}%",
            points,
            streak,
            now.strftime("%H:%M"),
        ])

        # ── Tab 2: Poin & Streak ──────────────────────
        _update_points_sheet(spreadsheet, ranger, points, streak, longest_streak)

        # ── Tab 3: Leaderboard ────────────────────────
        _update_leaderboard(spreadsheet)

        print(f"Sheets: logged {ranger['name']} — {correct}/{total}, {points} poin, streak {streak}")

    except Exception as e:
        print(f"Sheets logging error: {e}")

def _update_points_sheet(spreadsheet, ranger, points_today, streak, longest_streak):
    sheet = _get_or_create_sheet(spreadsheet, "Poin & Streak")
    header = [
        "Nama", "Ranger", "Level",
        "Total Poin", "Streak Saat Ini", "Streak Terpanjang", "Terakhir Aktif"
    ]
    _ensure_header(sheet, header)

    all_rows = sheet.get_all_values()
    today = datetime.now().strftime("%Y-%m-%d")

    for i, row in enumerate(all_rows[1:], start=2):
        if row and row[0] == ranger["name"]:
            current_total = _safe_int(row[3]) if len(row) > 3 else 0
            prev_longest  = _safe_int(row[5]) if len(row) > 5 else 0
            sheet.update(f"A{i}:G{i}", [[
                ranger["name"],
                ranger["ranger"],
                ranger["level"],
                current_total + points_today,
                streak,
                max(longest_streak, prev_longest),
                today,
            ]])
            return

    # Ranger belum ada di sheet — buat baris baru
    sheet.append_row([
        ranger["name"],
        ranger["ranger"],
        ranger["level"],
        points_today,
        streak,
        longest_streak,
        today,
    ])

def _update_leaderboard(spreadsheet):
    try:
        sheet_points = spreadsheet.worksheet("Poin & Streak")
    except gspread.exceptions.WorksheetNotFound:
        return

    sheet_lb = _get_or_create_sheet(spreadsheet, "Leaderboard")
    header = ["Rank", "Nama", "Ranger", "Level", "Total Poin", "Streak", "Status"]

    rows = sheet_points.get_all_values()[1:]
    if not rows:
        return

    rows_sorted = sorted(rows, key=lambda r: _safe_int(r[3]) if len(r) > 3 else 0, reverse=True)

    lb_data = [header]
    for i, row in enumerate(rows_sorted, start=1):
        total = row[3] if len(row) > 3 else "0"
        streak = row[4] if len(row) > 4 else "0"
        lb_data.append([
            i,
            row[0] if len(row) > 0 else "",
            row[1] if len(row) > 1 else "",
            row[2] if len(row) > 2 else "",
            total,
            streak,
            _rank_label(total),
        ])

    sheet_lb.clear()
    sheet_lb.update("A1", lb_data)

# ── Weekly summary (dipanggil tiap Jumat dari main.py) ───
def get_weekly_summary():
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        return None

    try:
        client = get_sheets_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        sheet_log = spreadsheet.worksheet("Log Harian")
        all_rows = sheet_log.get_all_values()[1:]

        # Ambil data 7 hari terakhir
        today = date.today()
        week_start = str(today - timedelta(days=6))

        summary = {}
        for row in all_rows:
            if not row or len(row) < 8:
                continue
            row_date = row[0]
            if row_date < week_start:
                continue
            name = row[1]
            correct = _safe_int(row[4])
            total = _safe_int(row[5])
            points = _safe_int(row[7])

            if name not in summary:
                summary[name] = {"sesi": 0, "benar": 0, "total": 0, "poin": 0}
            summary[name]["sesi"] += 1
            summary[name]["benar"] += correct
            summary[name]["total"] += total
            summary[name]["poin"] += points

        return summary

    except Exception as e:
        print(f"Weekly summary error: {e}")
        return None
