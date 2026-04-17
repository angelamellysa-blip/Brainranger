import os
from dotenv import load_dotenv

load_dotenv()
BRAINRANGER_AI_ANT_KEY = os.getenv("BRAINRANGER_AI_ANT_KEY")
# ── Telegram ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PARENT_CHAT_ID = int(os.getenv("PARENT_CHAT_ID", "0"))

# ── Ranger Chat IDs ───────────────────────────────────
RANGER_BIRU_CHAT_ID   = int(os.getenv("RANGER_BIRU_CHAT_ID", "0"))
RANGER_KUNING_CHAT_ID = int(os.getenv("RANGER_KUNING_CHAT_ID", "0"))
RANGER_PUTIH_CHAT_ID  = int(os.getenv("RANGER_PUTIH_CHAT_ID", "0"))

# ── Ranger Profiles ───────────────────────────────────
RANGERS = {
    RANGER_BIRU_CHAT_ID: {
        "name": "Kirana",
        "ranger": "Ranger Biru",
        "emoji": "🔵",
        "chat_id": RANGER_BIRU_CHAT_ID,
        "level": "SMP",
        "focus_minutes": 25,
        "break_minutes": 5,
        "sessions": 2,
    },
    RANGER_KUNING_CHAT_ID: {
        "name": "Kanaya",
        "ranger": "Ranger Kuning",
        "emoji": "🟡",
        "chat_id": RANGER_KUNING_CHAT_ID,
        "level": "SD Kelas 4",
        "focus_minutes": 20,
        "break_minutes": 5,
        "sessions": 2,
    },
    RANGER_PUTIH_CHAT_ID: {
        "name": "Kiandra",
        "ranger": "Ranger Putih",
        "emoji": "⚪",
        "chat_id": RANGER_PUTIH_CHAT_ID,
        "level": "SD Kelas 1",
        "focus_minutes": 15,
        "break_minutes": 5,
        "sessions": 2,
    },
}

# ── Schedule ──────────────────────────────────────────
REMINDER_HOUR   = int(os.getenv("REMINDER_HOUR", "19"))
REMINDER_MINUTE = int(os.getenv("REMINDER_MINUTE", "0"))
DIGEST_HOUR     = int(os.getenv("DIGEST_HOUR", "21"))
DIGEST_MINUTE   = int(os.getenv("DIGEST_MINUTE", "0"))

# ── Helper ────────────────────────────────────────────
def get_ranger(chat_id):
    return RANGERS.get(chat_id)

def is_ranger(chat_id):
    return chat_id in RANGERS

def is_parent(chat_id):
    return chat_id == PARENT_CHAT_ID