import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from config import get_ranger, is_ranger, PARENT_CHAT_ID
from handlers.ai_processor import process_photos
from utils.message_splitter import split_message

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
        "pembahasan": [],
        "points_today": 0,
        "topic": "",
        "all_sessions_done": False,
        "awaiting_answers": False,
        "current_question": 0,
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
        f"BrainRanger lagi activate power-mu... tunggu sebentar! ⚡"
    )

    try:
        # Proses semua foto ke Claude — 1 API call
       try:
        # Proses semua foto ke Claude — 1 API call
        result = await asyncio.to_thread(process_photos, photos, ranger)
            )
        )
    except Exception as e:
        await update.message.reply_text(
            f"Waduh ada error saat proses foto: {str(e)}\n"
            f"Coba lagi ya!"
        )
        return

    # Simpan ke state
    state["questions"] = result["soal"]
    state["keys"] = result["kunci"]
    state["pembahasan"] = result["pembahasan"]
    state["waiting_for_photo"] = False
    state["pending_photos"] = []

    # Kirim rangkuman text
    rangkuman = result["rangkuman"]
    chunks = split_message(f"📌 Rangkuman materi:\n\n{rangkuman}")
    for i, chunk in enumerate(chunks):
        prefix = f"(Rangkuman {i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        await update.message.reply_text(prefix + chunk)

    # Kirim soal
    soal_text = "❓ Soal latihan:\n\n"
    for i, soal in enumerate(result["soal"]):
        soal_text += f"{i+1}. {soal}\n\n"
    soal_text += "Jawab soal satu per satu ya! Ketik jawaban nomor 1 dulu."

    await update.message.reply_text(soal_text)

    # Set state untuk terima jawaban
    state["awaiting_answers"] = True
    state["current_question"] = 0
    state["answers"] = []

    # Start timer
    state["active"] = True
    state["session_start"] = datetime.now()

    context.job_queue.run_once(
        session_end,
        when=ranger["focus_minutes"] * 60,
        chat_id=chat_id,
        name=f"session_{chat_id}",
        data={"ranger": ranger, "session": state["current_session"]}
    )

    await update.message.reply_text(
        f"⏱ Timer {ranger['focus_minutes']} menit dimulai! Fokus ya! 🔥"
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

    # Koreksi
    correct_answer = state["keys"][current_q]
    pembahasan = state["pembahasan"][current_q] if current_q < len(state["pembahasan"]) else ""

    answer_lower = answer.lower()
    correct_lower = correct_answer.lower()
    is_correct = (
        answer_lower == correct_lower or
        answer_lower in correct_lower or
        correct_lower in answer_lower
    )

    if is_correct:
        state["points_today"] += 10
        result_text = f"✅ RANGER STRIKE! Jawaban tepat sasaran!\n\n"
    else:
        state["points_today"] += 2
        result_text = f"❌ Belum tepat, tapi tetap semangat!\nJawaban: {correct_answer}\n\n"

    result_text += f"📖 Pembahasan:\n{pembahasan}"

    await update.message.reply_text(result_text)

    state["current_question"] += 1

    # Cek apakah semua soal sudah dijawab
    if state["current_question"] >= len(state["questions"]):
        state["awaiting_answers"] = False
        correct_count = sum(
            1 for i, ans in enumerate(state["answers"])
            if i < len(state["keys"]) and (
                ans.lower() == state["keys"][i].lower() or
                ans.lower() in state["keys"][i].lower() or
                state["keys"][i].lower() in ans.lower()
            )
        )
        await update.message.reply_text(
            f"{ranger['emoji']} Semua soal selesai!\n\n"
            f"Skor: {correct_count}/{len(state['questions'])} benar\n"
            f"Lanjut fokus belajar ya! Timer masih jalan ⏱"
        )
    else:
        await update.message.reply_text(
            f"Lanjut soal {state['current_question'] + 1} ya!"
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
                f"Kalau sudah siap, ketik /lanjut"
            )
        )
    else:
        state["all_sessions_done"] = True
        correct_count = sum(
            1 for i, ans in enumerate(state["answers"])
            if i < len(state["keys"]) and (
                ans.lower() == state["keys"][i].lower() or
                ans.lower() in state["keys"][i].lower() or
                state["keys"][i].lower() in ans.lower()
            )
        )
        total_q = len(state["questions"])

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"{ranger['emoji']} MISI SELESAI, {ranger['name']}! ⚡\n\n"
                f"Full 2 sesi completed!\n"
                f"Soal benar: {correct_count}/{total_q}\n"
                f"Power hari ini: +{state['points_today']} ⚡\n\n"
                f"{ranger['ranger']} makin kuat! 🔥"
            )
        )
        await context.bot.send_message(
            chat_id=PARENT_CHAT_ID,
            text=(
                f"{ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
                f"selesai belajar! ✅\n"
                f"Soal benar: {correct_count}/{total_q}\n"
                f"Power: +{state['points_today']} ⚡"
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