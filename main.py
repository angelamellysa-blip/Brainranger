import logging
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, PARENT_CHAT_ID, REMINDER_HOUR, REMINDER_MINUTE, DIGEST_HOUR, DIGEST_MINUTE, get_ranger, is_ranger, is_parent
from utils.points import get_today_points, get_total_points, get_all_today
from handlers.pomodoro import (
    handle_mulai, handle_photo, handle_selesai,
    handle_lanjut, handle_skip, handle_answer,
    get_state, init_session
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

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
    today = get_today_points(chat_id)
    total = get_total_points(chat_id)
    await update.message.reply_text(
        f"{ranger['emoji']} Power Points {ranger['name']}\n\n"
        f"Poin hari ini: {today} ⚡\n"
        f"Total semua waktu: {total} ⚡"
    )

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    from config import RANGERS
    for chat_id, ranger in RANGERS.items():
        if chat_id == 0:
            continue
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"{ranger['emoji']} Hei {ranger['name']}!\n\n"
                    f"{ranger['ranger']} — misi hari ini menunggumu!\n"
                    f"Yuk belajar sekarang, ketik /mulai untuk mulai! ⚡"
                )
            )
        except Exception as e:
            print(f"Gagal kirim reminder ke {ranger['name']}: {e}")
    await context.bot.send_message(
        chat_id=PARENT_CHAT_ID,
        text="🔔 Reminder belajar sudah dikirim ke semua Ranger!"
    )

async def send_digest(context: ContextTypes.DEFAULT_TYPE):
    from config import RANGERS
    today_points = get_all_today()
    msg = "📊 Digest Belajar Hari Ini\n\n"
    for cid, r in RANGERS.items():
        if cid == 0:
            continue
        state = get_state(cid)
        pts = today_points.get(cid, 0)
        done = "✅ selesai" if state.get("all_sessions_done") else "⏳ belum selesai"
        msg += f"{r['emoji']} {r['name']}: {done} — {pts} poin ⚡\n"
    await context.bot.send_message(chat_id=PARENT_CHAT_ID, text=msg)

async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_parent(update.effective_chat.id):
        return
    await send_reminders(context)

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("id",            get_id))
    app.add_handler(CommandHandler("squad",         squad))
    app.add_handler(CommandHandler("power",         power))
    app.add_handler(CommandHandler("mulai",         handle_mulai))
    app.add_handler(CommandHandler("selesai",       handle_selesai))
    app.add_handler(CommandHandler("lanjut",        handle_lanjut))
    app.add_handler(CommandHandler("skip",          handle_skip))
    app.add_handler(CommandHandler("testreminder",  test_reminder))
    app.add_handler(MessageHandler(filters.PHOTO,   handle_photo))
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_answer
    ))

    app.job_queue.run_daily(
        send_reminders,
        time=datetime.time(
            hour=REMINDER_HOUR,
            minute=REMINDER_MINUTE,
            tzinfo=datetime.timezone(datetime.timedelta(hours=7))
        ),
        name="daily_reminder"
    )

    app.job_queue.run_daily(
        send_digest,
        time=datetime.time(
            hour=DIGEST_HOUR,
            minute=DIGEST_MINUTE,
            tzinfo=datetime.timezone(datetime.timedelta(hours=7))
        ),
        name="daily_digest"
    )

    print("BrainRanger bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()