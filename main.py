import logging
import asyncio
import datetime
import os
import sys
import traceback
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import (
    TELEGRAM_BOT_TOKEN, SUPERADMIN_CHAT_ID,
    REMINDER_HOUR, REMINDER_MINUTE, DIGEST_HOUR, DIGEST_MINUTE,
    get_ranger, is_ranger, is_parent, is_superadmin,
    get_parent_name, get_family_rangers, get_all_families, get_all_rangers,
)
from utils.points import get_today_points, get_total_points, get_all_today, get_streak, get_rank
from utils.bank_soal import get_weak_topics
from handlers.pomodoro import (
    handle_mulai, handle_photo, handle_document, handle_selesai,
    handle_lanjut, handle_skip, handle_answer,
    handle_latihan, handle_ulang, handle_ujian,
    handle_status, handle_bankinfo, handle_sticker, get_state, init_session
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
        nama = get_parent_name(chat_id) or "Bunda/Ayah"
        await update.message.reply_text(
            f"Hei {nama}! BrainRanger aktif.\n"
            "Ketik /squad untuk lihat status Ranger di keluargamu."
        )
    else:
        await update.message.reply_text(
            "Maaf, kamu tidak terdaftar di BrainRanger."
        )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Chat ID kamu: {update.effective_chat.id}"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_parent(chat_id):
        nama = get_parent_name(chat_id) or "Orang Tua"
        msg = (
            f"🦸 BrainRanger — Perintah untuk {nama}\n\n"
            "📋 STATUS & MONITORING\n"
            "/squad — Status real-time Ranger di keluargamu (poin, streak, rank)\n\n"
            "🛠 LAINNYA\n"
            "/id — Lihat Chat ID kamu\n"
            "/help — Tampilkan perintah ini\n"
        )
        if is_superadmin(chat_id):
            msg += (
                "\n👑 SUPERADMIN\n"
                "/usage — Laporan pemakaian AI & cost per keluarga\n"
                "/pause — Pause semua fitur AI\n"
                "/resume — Aktifkan lagi fitur AI\n"
                "/testreminder — Kirim reminder belajar ke semua Ranger sekarang\n"
                "/restart — Restart bot\n"
            )
    elif get_ranger(chat_id):
        ranger = get_ranger(chat_id)
        msg = (
            f"{ranger['emoji']} BrainRanger — Perintah untuk {ranger['name']}\n\n"
            "📚 SESI BELAJAR\n"
            "/mulai — Mulai sesi belajar baru (kirim foto, PDF, atau Word)\n"
            "/selesai — Selesai kirim file, proses materi\n"
            "/lanjut — Mulai mengerjakan soal\n"
            "/skip — Skip belajar hari ini\n\n"
            "🎯 LATIHAN SOAL\n"
            "/latihan — Latihan soal dari bank soal (pilih mapel)\n"
            "/ulang — Ulangi soal yang pernah dijawab salah\n"
            "/ujian — Simulasi ujian per mapel (soal lebih banyak)\n\n"
            "⚡ POWER & RANK\n"
            "/power — Lihat poin hari ini dan total power\n"
            "/status — Cek status sesi belajar saat ini\n\n"
            "🛠 LAINNYA\n"
            "/id — Lihat Chat ID kamu\n"
            "/help — Tampilkan perintah ini\n"
        )
    else:
        msg = "Maaf, kamu tidak terdaftar di BrainRanger."
    await update.message.reply_text(msg)

def _ranger_status_block(cid, r):
    state  = get_state(cid)
    today  = get_today_points(cid)
    total  = get_total_points(cid)
    streak, _ = get_streak(cid)
    rank_emoji, rank_name = get_rank(total)

    if state.get("all_sessions_done"):
        correct = state.get("correct_count", 0)
        total_q = len(state.get("questions", []))
        status  = f"✅ Selesai ({correct}/{total_q} benar)"
    elif state.get("active"):
        status = "🟢 Sedang belajar"
    else:
        status = "⚪ Belum mulai"

    streak_str = f"{streak} hari 🔥" if streak >= 3 else f"{streak} hari"

    weak = get_weak_topics(cid, top_n=1)
    weak_str = f"⚠️ Lemah: {weak[0]['mapel']} ({weak[0]['salah']}x)" if weak else "✨ Belum ada data"

    return (
        f"{r['emoji']} {r['name']} ({r['ranger']})\n"
        f"   {status}\n"
        f"   Hari ini: +{today} ⚡ | Total: {total} ⚡\n"
        f"   Streak: {streak_str} | {rank_emoji} {rank_name}\n"
        f"   {weak_str}\n\n"
    )

async def squad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_parent(chat_id):
        return
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
    msg = f"🦸 BrainRanger Squad\n{now.strftime('%d %b %Y, %H:%M')} WIB\n"
    msg += "━━━━━━━━━━━━━━━\n\n"

    if is_superadmin(chat_id):
        # Superadmin lihat semua keluarga, dikelompokkan per keluarga
        families = get_all_families()
        for fam_id, fam in families.items():
            if len(families) > 1:
                msg += f"👨‍👩‍👧 {fam.get('parent_name') or fam_id} ({fam_id})\n"
            for cid, r in fam["rangers"].items():
                msg += _ranger_status_block(cid, r)
    else:
        # Parent biasa HANYA lihat ranger keluarganya sendiri
        for cid, r in get_family_rangers(chat_id).items():
            msg += _ranger_status_block(cid, r)

    await update.message.reply_text(msg)

async def power(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return
    today  = get_today_points(chat_id)
    total  = get_total_points(chat_id)
    streak, _ = get_streak(chat_id)
    rank_emoji, rank_name = get_rank(total)

    # Progress ke rank berikutnya
    RANK_THRESHOLDS = [101, 301, 601, 1000]
    next_threshold  = next((t for t in RANK_THRESHOLDS if t > total), None)
    if next_threshold:
        progress_msg = f"Menuju rank berikutnya: {next_threshold - total} ⚡ lagi"
    else:
        progress_msg = "Kamu sudah di rank tertinggi! 👑"

    streak_str = f"{streak} hari 🔥" if streak >= 3 else f"{streak} hari"

    await update.message.reply_text(
        f"{ranger['emoji']} Power Report — {ranger['name']}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"⚡ Hari ini    : +{today}\n"
        f"⚡ Total power : {total}\n\n"
        f"{rank_emoji} Rank   : {rank_name}\n"
        f"🔥 Streak  : {streak_str}\n\n"
        f"📈 {progress_msg}"
    )

async def check_inactive_rangers(context: ContextTypes.DEFAULT_TYPE):
    from datetime import date
    for fam_id, fam in get_all_families().items():
        belum = []
        for cid, r in fam["rangers"].items():
            state = get_state(cid)
            if state.get("all_sessions_done"):
                continue
            session_start = state.get("session_start")
            started_today = bool(session_start and session_start.startswith(str(date.today())))
            if not started_today:
                belum.append((cid, r))

        if not belum:
            continue

        # Notif ke parent keluarga ini saja
        parent_id = fam.get("parent_chat_id")
        if parent_id:
            names = "\n".join([f"{r['emoji']} {r['name']} ({r['ranger']})" for _, r in belum])
            try:
                await context.bot.send_message(
                    chat_id=parent_id,
                    text=f"⚠️ Ranger belum mulai belajar malam ini:\n\n{names}"
                )
            except Exception as e:
                print(f"Gagal kirim inactive notif ke parent {fam_id}: {e}")

        # Reminder personal ke masing-masing anak + streak warning
        for cid, r in belum:
            streak, _ = get_streak(cid)
            if streak >= 2:
                streak_warn = (
                    f"\n\n⚠️ Streak {streak} hari kamu mau putus malam ini!\n"
                    f"Jangan sampai terputus — belajar sebentar saja sudah cukup! 🔥"
                )
            else:
                streak_warn = ""
            try:
                await context.bot.send_message(
                    chat_id=cid,
                    text=(
                        f"{r['emoji']} Hei {r['name']}! Kamu belum belajar hari ini.\n"
                        f"Masih ada waktu, ketik /mulai sekarang! ⚡"
                        f"{streak_warn}"
                    )
                )
            except Exception as e:
                print(f"Gagal kirim inactive reminder ke {r['name']}: {e}")

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    for chat_id, ranger in get_all_rangers().items():
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
    if SUPERADMIN_CHAT_ID:
        await context.bot.send_message(
            chat_id=SUPERADMIN_CHAT_ID,
            text="🔔 Reminder belajar sudah dikirim ke semua Ranger!"
        )

async def send_weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    if datetime.datetime.now().weekday() != 4:  # 4 = Jumat
        return
    from handlers.sheets import get_weekly_summary
    summary = await asyncio.to_thread(get_weekly_summary)
    if not summary:
        return

    msg = f"📊 Rekap Mingguan BrainRanger\n\n"
    for name, data in summary.items():
        avg = round(data["benar"] / data["total"] * 100, 1) if data["total"] > 0 else 0
        msg += (
            f"👤 {name}\n"
            f"   Sesi: {data['sesi']} | Poin: {data['poin']} ⚡\n"
            f"   Rata-rata benar: {avg}%\n\n"
        )
    if SUPERADMIN_CHAT_ID:
        await context.bot.send_message(chat_id=SUPERADMIN_CHAT_ID, text=msg)

async def send_digest(context: ContextTypes.DEFAULT_TYPE):
    today_points = get_all_today()
    # Setiap parent hanya menerima digest anak-anaknya sendiri
    for fam_id, fam in get_all_families().items():
        parent_id = fam.get("parent_chat_id")
        if not parent_id or not fam["rangers"]:
            continue
        msg = "📊 Digest Belajar Hari Ini\n\n"
        for cid, r in fam["rangers"].items():
            state = get_state(cid)
            pts = today_points.get(cid, 0)
            done = "✅ selesai" if state.get("all_sessions_done") else "⏳ belum selesai"
            msg += f"{r['emoji']} {r['name']}: {done} — {pts} poin ⚡\n"
        try:
            await context.bot.send_message(chat_id=parent_id, text=msg)
        except Exception as e:
            print(f"Gagal kirim digest ke parent {fam_id}: {e}")

async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    await send_reminders(context)

async def usage_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    from utils.usage import (
        get_usage_summary, get_today_cost, is_ai_paused, get_pause_info,
        DAILY_BUDGET_USD,
    )
    summary  = get_usage_summary(days=7)
    rangers  = summary.pop("_rangers", {})
    families = get_all_families()

    msg = "📈 Usage Report (7 hari terakhir)\n━━━━━━━━━━━━━━━\n\n"
    if not summary:
        msg += "Belum ada pemakaian AI tercatat.\n"
    for fid, u in sorted(summary.items()):
        fam_name = families.get(fid, {}).get("parent_name") or fid
        sonnet = u.get("sonnet_in", 0) + u.get("sonnet_out", 0)
        haiku  = u.get("haiku_in", 0) + u.get("haiku_out", 0)
        # Hitung event hari ini untuk ranger-ranger keluarga ini
        fam_ranger_ids = {str(cid) for cid in families.get(fid, {}).get("rangers", {})}
        sesi  = sum(r.get("sessions", 0) for cid, r in rangers.items() if cid in fam_ranger_ids)
        evals = sum(r.get("evals", 0) for cid, r in rangers.items() if cid in fam_ranger_ids)
        msg += (
            f"👨‍👩‍👧 {fam_name} ({fid})\n"
            f"   Hari ini: {sesi} sesi, {evals} evaluasi — ${u['today_cost']:.3f}\n"
            f"   7 hari: Sonnet {sonnet:,} tok | Haiku {haiku:,} tok | "
            f"TTS {u.get('tts_chars', 0):,} kar\n"
            f"   💰 Estimasi 7 hari: ${u['cost']:.2f}\n\n"
        )

    today_cost = get_today_cost()
    pct = round(today_cost / DAILY_BUDGET_USD * 100) if DAILY_BUDGET_USD else 0
    msg += f"━━━━━━━━━━━━━━━\n💵 Total hari ini: ${today_cost:.3f} / ${DAILY_BUDGET_USD:.2f} ({pct}%)\n"
    if is_ai_paused():
        msg += f"🛑 AI sedang PAUSED — {get_pause_info()}\nKetik /resume untuk aktifkan.\n"
    else:
        msg += "🟢 AI aktif\n"
    await update.message.reply_text(msg)

async def pause_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    from utils.usage import set_ai_paused
    set_ai_paused(True, "di-pause manual oleh superadmin", manual=True)
    await update.message.reply_text("🛑 Semua fitur AI di-PAUSE. Ketik /resume untuk aktifkan lagi.")

async def resume_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    from utils.usage import set_ai_paused
    set_ai_paused(False)
    await update.message.reply_text("🟢 Fitur AI aktif kembali!")

async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    await update.message.reply_text("🔄 Restarting BrainRanger... tunggu beberapa detik ya!")
    os.execv(sys.executable, [sys.executable] + sys.argv)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    tb_str = "".join(traceback.format_exception(
        type(context.error), context.error, context.error.__traceback__
    ))
    logging.error(f"[ERROR HANDLER]\n{tb_str}")

    # Notif ke superadmin supaya tahu ada yang error
    if not SUPERADMIN_CHAT_ID:
        return
    try:
        error_msg = str(context.error)[:300]
        update_info = ""
        if hasattr(update, "effective_chat") and update.effective_chat:
            update_info = f" (chat: {update.effective_chat.id})"
        await context.bot.send_message(
            chat_id=SUPERADMIN_CHAT_ID,
            text=f"⚠️ BrainRanger error{update_info}:\n{error_msg}\n\nBot tetap jalan, bukan crash."
        )
    except Exception:
        pass

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("help",          help_command))
    app.add_handler(CommandHandler("id",            get_id))
    app.add_handler(CommandHandler("squad",         squad))
    app.add_handler(CommandHandler("power",         power))
    app.add_handler(CommandHandler("mulai",         handle_mulai))
    app.add_handler(CommandHandler("selesai",       handle_selesai))
    app.add_handler(CommandHandler("lanjut",        handle_lanjut))
    app.add_handler(CommandHandler("skip",          handle_skip))
    app.add_handler(CommandHandler("latihan",       handle_latihan))
    app.add_handler(CommandHandler("ulang",         handle_ulang))
    app.add_handler(CommandHandler("ujian",         handle_ujian))
    app.add_handler(CommandHandler("status",         handle_status))
    app.add_handler(CommandHandler("bankinfo",       handle_bankinfo))
    app.add_handler(CommandHandler("testreminder",  test_reminder))
    app.add_handler(CommandHandler("restart",       restart_bot))
    app.add_handler(CommandHandler("usage",         usage_report))
    app.add_handler(CommandHandler("pause",         pause_ai))
    app.add_handler(CommandHandler("resume",        resume_ai))
    app.add_handler(MessageHandler(filters.PHOTO,       handle_photo))
    app.add_handler(MessageHandler(
        filters.Document.PDF |
        filters.Document.MimeType(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ) |
        filters.Document.MimeType("application/msword"),
        handle_document
    ))
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
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

    app.job_queue.run_daily(
        check_inactive_rangers,
        time=datetime.time(
            hour=20,
            minute=0,
            tzinfo=datetime.timezone(datetime.timedelta(hours=7))
        ),
        name="inactive_check"
    )

    app.job_queue.run_daily(
        send_weekly_summary,
        time=datetime.time(
            hour=21,
            minute=30,
            tzinfo=datetime.timezone(datetime.timedelta(hours=7))
        ),
        name="weekly_summary"
    )

    print("BrainRanger bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()