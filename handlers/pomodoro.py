import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import get_ranger, is_ranger, PARENT_CHAT_ID

session_state = {}

def init_session(chat_id):
    session_state[chat_id] = {
        "active": False,
        "waiting_for_photo": False,
        "current_session": 0,
        "session_start": None,
        "pending_photos": [],
        "questions": [],
        "answers": [],
        "keys": [],
        "points_today": 0,
        "topic": "",
        "all_sessions_done": False,
    }

def get_state(chat_id):
    if chat_id not in session_state:
        init_session(chat_id)
    return session_state[chat_id]

# ── /mulai ────────────────────────────────────────────
async def handle_mulai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)

    if not ranger:
        return

    state = get_state(chat_id)

    if state["active"]:
        await update.message.reply_text(
            f"{ranger['emoji']} Sesi sedang berjalan! Selesaikan dulu ya."
        )
        return

    state["waiting_for_photo"] = True
    state["pending_photos"] = []
    state["current_session"] = 1

    await update.message.reply_text(
        f"{ranger['emoji']} {ranger['ranger']} siap tempur!\n\n"
        f"Foto halaman buku yang mau kamu pelajari sekarang.\n"
        f"Boleh kirim lebih dari 1 foto.\n"
        f"Kalau sudah semua, ketik /selesai"
    )

# ── Handler foto ──────────────────────────────────────
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)

    if not ranger:
        return

    state = get_state(chat_id)

    if not state.get("waiting_for_photo"):
        return

    photo = await update.message.photo[-1].get_file()
    photo_bytes = await photo.download_as_bytearray()
    state["pending_photos"].append(bytes(photo_bytes))

    count = len(state["pending_photos"])
    await update.message.reply_text(
        f"Foto {count} diterima!\n"
        f"Kirim foto berikutnya atau ketik /selesai kalau sudah semua."
    )

# ── /selesai ──────────────────────────────────────────
async def handle_selesai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)

    if not ranger:
        return

    state = get_state(chat_id)

    if not state.get("waiting_for_photo"):
        return

    photos = state["pending_photos"]

    if not photos:
        await update.message.reply_text(
            "Belum ada foto! Kirim foto bukumu dulu ya!"
        )
        return

    await update.message.reply_text(
        f"{ranger['emoji']} {len(photos)} foto diterima!\n"
        f"Rangkuman & soal sedang disiapkan... (fitur ini coming soon)\n\n"
        f"Untuk sekarang langsung mulai timer ya!\n"
        f"Sesi {state['current_session']} dimulai — {ranger['focus_minutes']} menit fokus! ⚡"
    )

    state["waiting_for_photo"] = False
    state["active"] = True
    state["session_start"] = datetime.now()

    # Schedule session end
    context.job_queue.run_once(
        session_end,
        when=ranger["focus_minutes"] * 60,
        chat_id=chat_id,
        name=f"session_{chat_id}",
        data={"ranger": ranger, "session": state["current_session"]}
    )

# ── Session end ───────────────────────────────────────
async def session_end(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    ranger = job.data["ranger"]
    session = job.data["session"]
    state = get_state(chat_id)
    state["active"] = False

    if session == 1:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{ranger['emoji']} Sesi 1 selesai! Keren!\n\n"
                f"Break {ranger['break_minutes']} menit dulu ya.\n"
                f"Kalau sudah siap lanjut, ketik /lanjut"
            )
        )
    else:
        state["all_sessions_done"] = True
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{ranger['emoji']} MISI SELESAI, {ranger['name']}!\n\n"
                f"Full 2 sesi completed! {ranger['ranger']} makin kuat! ⚡\n"
                f"Poin hari ini coming soon — tunggu update berikutnya!"
            )
        )
        # Notif parent
        await context.bot.send_message(
            chat_id=PARENT_CHAT_ID,
            text=(
                f"{ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
                f"selesai belajar hari ini! ✅"
            )
        )

# ── /lanjut ───────────────────────────────────────────
async def handle_lanjut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)

    if not ranger:
        return

    state = get_state(chat_id)
    state["active"] = True
    state["current_session"] = 2

    await update.message.reply_text(
        f"{ranger['emoji']} Sesi 2 dimulai!\n"
        f"{ranger['focus_minutes']} menit lagi — gas pol! 🔥"
    )

    context.job_queue.run_once(
        session_end,
        when=ranger["focus_minutes"] * 60,
        chat_id=chat_id,
        name=f"session2_{chat_id}",
        data={"ranger": ranger, "session": 2}
    )

# ── /skip ─────────────────────────────────────────────
async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)

    if not ranger:
        return

    await update.message.reply_text(
        f"{ranger['emoji']} Oke {ranger['name']}, skip hari ini.\n"
        f"Besok semangat lagi ya! 💪"
    )

    await context.bot.send_message(
        chat_id=PARENT_CHAT_ID,
        text=f"⚠️ {ranger['name']} ({ranger['ranger']}) skip belajar hari ini."
    )