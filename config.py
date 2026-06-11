import os
from dotenv import load_dotenv

load_dotenv()
BRAINRANGER_AI_ANT_KEY = os.getenv("BRAINRANGER_AI_ANT_KEY")
# ── Telegram ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Multi-tenant family registry ──────────────────────
# Data keluarga (parent + rangers) sekarang di families.json,
# dikelola utils/families.py. Keluarga pertama di-seed otomatis
# dari env vars lama (PARENT_CHAT_ID, RANGER_*_CHAT_ID).
from utils.families import (
    SUPERADMIN_CHAT_ID,
    get_ranger, is_ranger, is_parent, is_superadmin,
    get_parent_of, get_parent_name,
    get_family_rangers, get_all_families, get_all_rangers,
)

# ── Google Sheets ─────────────────────────────────────
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

# ── Schedule ──────────────────────────────────────────
REMINDER_HOUR   = int(os.getenv("REMINDER_HOUR", "19"))
REMINDER_MINUTE = int(os.getenv("REMINDER_MINUTE", "0"))
DIGEST_HOUR     = int(os.getenv("DIGEST_HOUR", "21"))
DIGEST_MINUTE   = int(os.getenv("DIGEST_MINUTE", "0"))
