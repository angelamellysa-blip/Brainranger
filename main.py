import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, get_ranger, is_ranger, is_parent
from handlers.pomodoro import (
    handle_mulai, handle_photo, handle_selesai,
    handle_lanjut, handle_skip, get_state, init_session
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ── Handlers ──────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    init_session(chat_id)

    if ranger:
        await update.message.reply_text(
            f"{ranger['emoji']} Hei {ranger['name']}!\n"
            f"Selamat datang di BrainRanger!\n"
            f"Kamu adalah {ranger['ranger']} — siap activate brain power! ⚡"
        )
    elif is_parent(chat_id):
        await update.message.reply_text(
            "Hei Angela! BrainRanger aktif.\n"
            "Ketik /squad untuk lihat status 3 Ranger."
        )
    else:
        await update.message.reply_text(
            "Maaf, kamu tidak terdaftar di BrainRanger."
        )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Chat ID kamu: {update.effective_chat.id}"
    )

async def squad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_parent(chat_id):
        return

    from config import RANGERS
    msg = "🦸 BrainRanger Squad Status\n\n"
    for cid, r in RANGERS.items():
        state = get_state(cid)
        active = "🟢 aktif" if state.get("active") else "⚪ belum mulai"
        msg += f"{r['emoji']} {r['name']} ({r['ranger']}) — {active}\n"

    await update.message.reply_text(msg)

async def power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return
    state = get_state(chat_id)
    await update.message.reply_text(
        f"{ranger['emoji']} Power Points {ranger['name']}\n\n"
        f"Poin hari ini: {state['points_today']}\n"
        f"(Fitur lengkap coming soon!)"
    )

# ── Main ──────────────────────────────────────────────
def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("id",      get_id))
    app.add_handler(CommandHandler("squad",   squad))
    app.add_handler(CommandHandler("power",   power))
    app.add_handler(CommandHandler("mulai",   handle_mulai))
    app.add_handler(CommandHandler("selesai", handle_selesai))
    app.add_handler(CommandHandler("lanjut",  handle_lanjut))
    app.add_handler(CommandHandler("skip",    handle_skip))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("BrainRanger bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()