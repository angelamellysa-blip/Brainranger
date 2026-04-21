import asyncio
import base64
import os
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import get_ranger, PARENT_CHAT_ID
from handlers.ai_processor import process_photos, evaluate_answer
from utils.message_splitter import split_message
from utils.state_manager import load_all_states, save_all_states
from utils.points import add_points
from handlers.sheets import log_session

session_state = load_all_states()

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
        "pembahasan": [],
        "rangkuman": "",
        "points_today": 0,
        "topic": "",
        "all_sessions_done": False,
        "awaiting_answers": False,
        "current_question": 0,
        "correct_count": 0,
    }
    save_all_states(session_state)

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

    init_session(chat_id)
    state = get_state(chat_id)
    state["waiting_for_photo"] = True
    state["current_session"] = 1
    save_all_states(session_state)

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
    state["pending_photos"].append(base64.b64encode(bytes(photo_bytes)).decode("utf-8"))

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

    # Force reset data lama
    state["questions"] = []
    state["keys"] = []
    state["pembahasan"] = []
    state["rangkuman"] = ""
    state["answers"] = []
    state["correct_count"] = 0
    state["current_question"] = 0
    state["awaiting_answers"] = False

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
        f"BrainRanger lagi activate power-mu... tunggu sebentar! ⚡"
    )

    photos_bytes = [base64.b64decode(p) if isinstance(p, str) else p for p in photos]

    try:
        result = await asyncio.to_thread(process_photos, photos_bytes, ranger)
    except Exception as e:
        await update.message.reply_text(
            f"Waduh ada error saat proses foto: {str(e)}\n"
            f"Coba lagi ya!"
        )
        return

    # Cek apakah foto tidak terbaca
    if result["rangkuman"].startswith("FOTO_TIDAK_TERBACA"):
        await update.message.reply_text(
            f"{ranger['emoji']} Foto kurang jelas nih!\n\n"
            f"Tips foto yang bagus:\n"
            f"• Pastikan cahaya cukup terang\n"
            f"• Kamera tegak lurus di atas buku\n"
            f"• Tulisan tidak terlipat atau tertutup\n"
            f"• Jarak kamera sekitar 20-30cm dari buku\n\n"
            f"Coba ketik /mulai dan upload foto ulang ya!"
        )
        init_session(chat_id)
        return

    # Simpan ke state
    state["questions"] = result["soal"]
    state["keys"] = result["kunci"]
    state["pembahasan"] = result["pembahasan"]
    state["rangkuman"] = result["rangkuman"]
    state["waiting_for_photo"] = False
    state["pending_photos"] = []
    save_all_states(session_state)

    # ── SESI 1: Kirim rangkuman + audio ──────────────
    rangkuman = result["rangkuman"]
    chunks = split_message(f"📌 Rangkuman materi:\n\n{rangkuman}")
    for i, chunk in enumerate(chunks):
        prefix = f"(Rangkuman {i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        await update.message.reply_text(prefix + chunk)

    # Generate & kirim podcast audio
    try:
        from handlers.tts import generate_podcast
        podcast_path = await asyncio.to_thread(
            generate_podcast,
            rangkuman,
            ranger["name"],
            ranger["level"]
        )
        with open(podcast_path, "rb") as audio:
            await update.message.reply_audio(
                audio=audio,
                title=f"Podcast Materi - {ranger['name']}",
                caption="Dengerin sambil belajar ya! 🎧",
            )
        os.remove(podcast_path)
    except Exception as e:
        print(f"TTS error: {e}")
        await update.message.reply_text(
            "Audio podcast tidak tersedia, tapi rangkuman text sudah ada ya!"
        )

    # Start timer sesi 1
    state["active"] = True
    state["session_start"] = datetime.now().isoformat()
    save_all_states(session_state)

    context.job_queue.run_once(
        session_end,
        when=ranger["focus_minutes"] * 60,
        chat_id=chat_id,
        name=f"session_{chat_id}",
        data={"ranger": ranger, "session": 1}
    )

    await update.message.reply_text(
        f"⏱ Sesi 1 dimulai — {ranger['focus_minutes']} menit!\n\n"
        f"Baca rangkuman & dengerin podcast dulu ya.\n"
        f"Nanti setelah timer selesai, kamu akan ditest! 💪"
    )

# ── Session end ───────────────────────────────────────
async def session_end(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id
    ranger = job.data["ranger"]
    session = job.data["session"]
    state = get_state(chat_id)
    state["active"] = False
    save_all_states(session_state)

    if session == 1:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{ranger['emoji']} Sesi 1 selesai! Semoga sudah paham materinya!\n\n"
                f"Break {ranger['break_minutes']} menit dulu ya.\n\n"
                f"Setelah siap, ketik /lanjut untuk mulai sesi test! 📝"
            )
        )
    else:
        state["all_sessions_done"] = True
        total_q = len(state["questions"])
        correct = state["correct_count"]
        save_all_states(session_state)

        # Log ke Google Sheets (hanya jika belum di-log dari handle_answer)
        if not state.get("session_logged"):
            await asyncio.to_thread(log_session, ranger, correct, total_q, state["points_today"])

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{ranger['emoji']} MISI SELESAI, {ranger['name']}! ⚡\n\n"
                f"Full 2 sesi completed!\n"
                f"Soal benar: {correct}/{total_q}\n"
                f"Power hari ini: +{state['points_today']} ⚡\n\n"
                f"{ranger['ranger']} makin kuat! 🔥"
            )
        )
        await context.bot.send_message(
            chat_id=PARENT_CHAT_ID,
            text=(
                f"{ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
                f"selesai belajar! ✅\n"
                f"Soal benar: {correct}/{total_q}\n"
                f"Power: +{state['points_today']} ⚡"
            )
        )

# ── /lanjut → mulai sesi 2 (TEST) ────────────────────
async def handle_lanjut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)

    # Validasi — pastikan ada soal
    if not state.get("questions"):
        await update.message.reply_text(
            f"{ranger['emoji']} Belum ada materi yang diproses.\n"
            f"Ketik /mulai dulu ya!"
        )
        return

    state["active"] = True
    state["current_session"] = 2
    state["awaiting_answers"] = True
    state["current_question"] = 0
    state["answers"] = []
    state["correct_count"] = 0
    save_all_states(session_state)

    await update.message.reply_text(
        f"{ranger['emoji']} Sesi 2 dimulai — saatnya ditest! 📝\n\n"
        f"Ada {len(state['questions'])} soal yang harus dijawab.\n"
        f"Jawab satu per satu ya!\n\n"
        f"⏱ Timer {ranger['focus_minutes']} menit dimulai!"
    )

    # Kirim soal pertama
    await send_next_question(context.bot, chat_id, state, ranger)

    # Start timer sesi 2
    context.job_queue.run_once(
        session_end,
        when=ranger["focus_minutes"] * 60,
        chat_id=chat_id,
        name=f"session2_{chat_id}",
        data={"ranger": ranger, "session": 2}
    )

# ── Kirim soal berikutnya ─────────────────────────────
async def send_next_question(bot, chat_id, state, ranger):
    current_q = state["current_question"]
    total_q = len(state["questions"])

    if current_q >= total_q:
        return

    soal = state["questions"][current_q]
    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"❓ Soal {current_q + 1}/{total_q}\n\n"
            f"{soal}"
        )
    )

# ── Handler jawaban ───────────────────────────────────
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)
    if not state.get("awaiting_answers"):
        return

    current_q = state["current_question"]
    if current_q >= len(state["questions"]):
        return

    answer = update.message.text.strip()
    state["answers"].append(answer)

    correct_answer = state["keys"][current_q]
    pembahasan = state["pembahasan"][current_q] if current_q < len(state["pembahasan"]) else ""
    soal = state["questions"][current_q]

    # Evaluasi jawaban via Claude
    try:
        is_correct = await asyncio.to_thread(
            evaluate_answer,
            soal,
            answer,
            correct_answer,
            ranger["level"]
        )
    except Exception:
        is_correct = (
            answer.lower() == correct_answer.lower() or
            answer.lower() in correct_answer.lower() or
            correct_answer.lower() in answer.lower()
        )

    if is_correct:
        state["points_today"] += 10
        state["correct_count"] += 1
        add_points(chat_id, 10)
        result_text = f"✅ RANGER STRIKE! Jawaban tepat sasaran!\n\n"
    else:
        state["points_today"] += 2
        add_points(chat_id, 2)
        result_text = f"❌ Belum tepat, tapi tetap semangat!\nJawaban: {correct_answer}\n\n"

    result_text += f"📖 Pembahasan:\n{pembahasan}"
    await update.message.reply_text(result_text)

    state["current_question"] += 1
    save_all_states(session_state)

    # Cek apakah semua soal sudah dijawab
    if state["current_question"] >= len(state["questions"]):
        state["awaiting_answers"] = False
        state["all_sessions_done"] = True
        correct = state["correct_count"]
        total_q = len(state["questions"])
        save_all_states(session_state)

        # Cancel timer sesi 2 agar tidak double notif
        for job in context.job_queue.get_jobs_by_name(f"session2_{chat_id}"):
            job.schedule_removal()

<<<<<<< HEAD
=======
        # Log ke Google Sheets
        state["session_logged"] = True
        await asyncio.to_thread(log_session, ranger, correct, total_q, state["points_today"])

>>>>>>> 04f1258 (feat: Google Sheets session logging)
        await update.message.reply_text(
            f"{ranger['emoji']} MISI SELESAI, {ranger['name']}! ⚡\n\n"
            f"Full 2 sesi completed!\n"
            f"Soal benar: {correct}/{total_q}\n"
            f"Power hari ini: +{state['points_today']} ⚡\n\n"
            f"{ranger['ranger']} makin kuat! 🔥"
        )
        await context.bot.send_message(
            chat_id=PARENT_CHAT_ID,
            text=(
                f"{ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
                f"selesai belajar! ✅\n"
                f"Soal benar: {correct}/{total_q}\n"
                f"Power: +{state['points_today']} ⚡"
            )
        )
    else:
        await send_next_question(context.bot, chat_id, state, ranger)

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