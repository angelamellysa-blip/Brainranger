import asyncio
import base64
import os
import random
from telegram import Update
from telegram.ext import ContextTypes
from config import get_ranger, PARENT_CHAT_ID
from handlers.ai_processor import process_photos, evaluate_answer
from utils.message_splitter import split_message, to_html, strip_markdown
from utils.state_manager import load_all_states, save_all_states
from utils.points import add_points, update_streak, get_streak, get_total_points, get_rank
from utils.bank_soal import save_session, get_mapel_list, get_random_soal, get_salah_soal, update_result, get_stats
from handlers.sheets import log_session
from handlers.svg_generator import needs_illustration, generate_svg, generate_illustration, svg_to_png

session_state = load_all_states()

# Isi dengan sticker file_id dari Telegram.
# Cara dapat file_id: kirim sticker ke bot → lihat log "Sticker file_id: ..."
CELEBRATION_STICKERS = [
    "CAACAgIAAxkBAAIE42oO3LQ2LbxMgybRC0Ut6vQ2XhlkAAJiAQACIjeOBFTDGCohfmzkOwQ",
]

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
        "points_at_start": 0,
        "mode": "normal",             # "normal" | "latihan" | "ulang"
        "waiting_for_mapel_pick": False,
        "latihan_soal_ids": [],       # soal IDs dari bank untuk update hasil
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
    state["points_at_start"] = get_total_points(chat_id)
    save_all_states(session_state)

    streak, _ = get_streak(chat_id)
    total = get_total_points(chat_id)
    rank_emoji, rank_name = get_rank(total)

    if streak >= 10:
        streak_msg = f"🔥 Streak {streak} hari! Luar biasa, pertahankan!\n"
    elif streak >= 5:
        streak_msg = f"🔥 Streak {streak} hari berturut-turut! Jangan putus!\n"
    elif streak >= 2:
        streak_msg = f"⚡ Streak {streak} hari! Terus semangat!\n"
    elif streak == 1:
        streak_msg = f"✨ Streak dimulai! Pertahankan ya!\n"
    else:
        streak_msg = f"💪 Yuk mulai streak hari ini!\n"

    await update.message.reply_text(
        f"{ranger['emoji']} {ranger['ranger']} siap tempur!\n\n"
        f"{streak_msg}"
        f"Rank: {rank_emoji} {rank_name} | Total: {total} ⚡\n\n"
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
    state["topic"] = result.get("topik", "")
    state["waiting_for_photo"] = False
    state["pending_photos"] = []
    state["active"] = True
    save_all_states(session_state)

    # ── Kirim rangkuman text ──────────────────────────
    rangkuman = result["rangkuman"]
    topik = state.get("topic", "")
    topik_header = f"📚 {topik}\n\n" if topik else ""
    rangkuman_html = to_html(rangkuman)
    chunks = split_message(f"{topik_header}📌 Rangkuman materi:\n\n{rangkuman_html}")
    for i, chunk in enumerate(chunks):
        prefix = f"(Rangkuman {i+1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        await update.message.reply_text(prefix + chunk, parse_mode="HTML")

    # ── Ilustrasi untuk rangkuman jika materi visual ──
    if needs_illustration(rangkuman):
        try:
            svg = await asyncio.to_thread(generate_illustration, rangkuman[:400], ranger["level"])
            if svg:
                png = await asyncio.to_thread(svg_to_png, svg)
                if png:
                    await update.message.reply_photo(photo=png, caption="📐 Ilustrasi materi")
        except Exception as e:
            print(f"Ilustrasi rangkuman gagal: {e}")

    # ── Generate & kirim podcast audio ───────────────
    rangkuman_tts = strip_markdown(rangkuman)
    try:
        from handlers.tts import generate_podcast
        podcast_path = await asyncio.to_thread(
            generate_podcast,
            rangkuman_tts,
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

    total_soal = len(state["questions"])
    await update.message.reply_text(
        f"✅ Materi siap!\n\n"
        f"Ada {total_soal} soal menunggumu.\n"
        f"Kalau sudah siap, ketik /lanjut untuk mulai test! 💪"
    )

# ── /lanjut → mulai sesi test ─────────────────────────
async def handle_lanjut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)

    if not state.get("questions"):
        await update.message.reply_text(
            f"{ranger['emoji']} Belum ada materi yang diproses.\n"
            f"Ketik /mulai dulu ya!"
        )
        return

    state["current_session"] = 2
    state["awaiting_answers"] = True
    state["current_question"] = 0
    state["answers"] = []
    state["correct_count"] = 0
    save_all_states(session_state)

    total_soal = len(state["questions"])
    await update.message.reply_text(
        f"{ranger['emoji']} Siap ditest! 📝\n\n"
        f"Ada {total_soal} soal yang harus dijawab.\n"
        f"Jawab satu per satu ya!"
    )

    await send_next_question(context.bot, chat_id, state, ranger)

# ── Kirim soal berikutnya ─────────────────────────────
async def send_next_question(bot, chat_id, state, ranger):
    current_q = state["current_question"]
    total_q = len(state["questions"])

    if current_q >= total_q:
        return

    soal = state["questions"][current_q]
    caption = f"❓ Soal {current_q + 1}/{total_q}\n\n{soal}"

    if needs_illustration(soal):
        try:
            svg = await asyncio.to_thread(generate_svg, soal, ranger["level"])
            if svg:
                png = await asyncio.to_thread(svg_to_png, svg)
                if png:
                    await bot.send_photo(chat_id=chat_id, photo=png, caption=caption)
                    return
        except Exception as e:
            print(f"Ilustrasi soal gagal, fallback ke teks: {e}")

    await bot.send_message(chat_id=chat_id, text=caption)

# ── Handler jawaban ───────────────────────────────────
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)

    # Handle pilihan mapel saat /latihan
    if state.get("waiting_for_mapel_pick"):
        await handle_mapel_pick(update, context, state, ranger)
        return

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

    try:
        verdict, catatan = await asyncio.to_thread(
            evaluate_answer,
            soal,
            answer,
            correct_answer,
            ranger["level"]
        )
    except Exception:
        simple_match = (
            answer.lower() == correct_answer.lower() or
            answer.lower() in correct_answer.lower() or
            correct_answer.lower() in answer.lower()
        )
        verdict = "BENAR" if simple_match else "SALAH"
        catatan = ""

    if verdict == "BENAR":
        state["points_today"] += 10
        state["correct_count"] += 1
        add_points(chat_id, 10)
        result_text = "✅ RANGER STRIKE! Jawaban tepat sasaran! +10 ⚡\n\n"
    elif verdict == "SEBAGIAN":
        state["points_today"] += 5
        state["correct_count"] += 1
        add_points(chat_id, 5)
        catatan_text = f"\n💡 Yang kurang: {catatan}" if catatan else ""
        result_text = f"⚠️ Hampir benar! +5 ⚡{catatan_text}\n\n"
    else:
        state["points_today"] += 2
        add_points(chat_id, 2)
        result_text = f"❌ Belum tepat, tapi tetap semangat! +2 ⚡\nJawaban: {correct_answer}\n\n"

    result_text += f"📖 Pembahasan:\n{pembahasan}"
    await update.message.reply_text(result_text)

    # Update bank soal jika mode latihan/ulang
    # BENAR=True (keluar dari /ulang), SEBAGIAN/SALAH=False (tetap muncul di /ulang)
    if state.get("mode") in ("latihan", "ulang"):
        soal_ids = state.get("latihan_soal_ids", [])
        if current_q < len(soal_ids):
            await asyncio.to_thread(update_result, chat_id, soal_ids[current_q], verdict == "BENAR")

    state["current_question"] += 1
    save_all_states(session_state)

    if state["current_question"] >= len(state["questions"]):
        state["awaiting_answers"] = False
        state["all_sessions_done"] = True
        correct = state["correct_count"]
        total_q = len(state["questions"])
        save_all_states(session_state)

        state["session_logged"] = True
        streak, longest_streak = update_streak(chat_id)
        topik = state.get("topic", "")

        # Simpan soal ke bank soal
        await asyncio.to_thread(
            save_session,
            chat_id, topik,
            state["questions"], state["keys"], state["pembahasan"]
        )

        await asyncio.to_thread(log_session, ranger, correct, total_q, state["points_today"], streak, longest_streak, topik)

        mode = state.get("mode", "normal")

        if mode in ("latihan", "ulang"):
            # Selesai latihan/ulang — tidak notif Angela, tidak log sheets
            label = "LATIHAN" if mode == "latihan" else "ULANG SOAL"
            await update.message.reply_text(
                f"🎯 {label} SELESAI!\n\n"
                f"Benar: {correct}/{total_q}\n"
                f"Power: +{state['points_today']} ⚡\n\n"
                f"Ketik /latihan untuk latihan lagi atau /ulang untuk soal yang masih salah!"
            )
            await send_celebration(context.bot, chat_id)
        else:
            # Sesi normal
            new_total = get_total_points(chat_id)
            old_total = state.get("points_at_start", 0)
            old_rank  = get_rank(old_total)
            new_rank  = get_rank(new_total)

            await update.message.reply_text(
                f"{ranger['emoji']} MISI SELESAI, {ranger['name']}! ⚡\n\n"
                f"Soal benar: {correct}/{total_q}\n"
                f"Power hari ini: +{state['points_today']} ⚡\n"
                f"Total power: {new_total} ⚡\n\n"
                f"{ranger['ranger']} makin kuat! 🔥"
            )

            if old_rank != new_rank:
                await update.message.reply_text(
                    f"🎉 LEVEL UP, {ranger['name']}!\n\n"
                    f"{old_rank[0]} {old_rank[1]}\n"
                    f"     ↓\n"
                    f"{new_rank[0]} {new_rank[1]}\n\n"
                    f"Pencapaian baru! Terus pertahankan! 💪"
                )

            await send_celebration(context.bot, chat_id)

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

# ── /latihan ─────────────────────────────────────────
async def handle_latihan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    mapel_list = get_mapel_list(chat_id)
    if not mapel_list:
        await update.message.reply_text(
            f"{ranger['emoji']} Bank soal kamu masih kosong!\n\n"
            f"Selesaikan minimal 1 sesi belajar dulu, baru bisa latihan. 💪"
        )
        return

    state = get_state(chat_id)
    state["mode"] = "latihan"
    state["waiting_for_mapel_pick"] = True
    state["awaiting_answers"] = False
    save_all_states(session_state)

    stats = get_stats(chat_id)
    msg = (
        f"🎯 Mode Latihan — {ranger['name']}\n"
        f"Bank soal: {stats['total']} soal | Belum dicoba: {stats['belum_dicoba']}\n\n"
        f"Pilih mata pelajaran (ketik nomornya):\n\n"
        f"0. Semua mapel (random)\n"
    )
    mapel_options = list(mapel_list.items())
    for i, (mapel, count) in enumerate(mapel_options, start=1):
        msg += f"{i}. {mapel} ({count} soal)\n"

    context.user_data["mapel_options"] = mapel_options
    await update.message.reply_text(msg)

# ── /ulang ────────────────────────────────────────────
async def handle_ulang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    salah_list = get_salah_soal(chat_id)
    if not salah_list:
        await update.message.reply_text(
            f"{ranger['emoji']} Tidak ada soal yang salah di bank soal!\n\n"
            f"Semua soal sudah pernah dijawab benar 🎉\n"
            f"Ketik /latihan untuk latihan soal random."
        )
        return

    state = get_state(chat_id)
    state["mode"] = "ulang"
    state["awaiting_answers"] = True
    state["waiting_for_mapel_pick"] = False
    state["current_question"] = 0
    state["correct_count"] = 0
    state["points_today"] = 0
    state["questions"]  = [s["soal"]      for s in salah_list]
    state["keys"]       = [s["kunci"]     for s in salah_list]
    state["pembahasan"] = [s["pembahasan"] for s in salah_list]
    state["latihan_soal_ids"] = [s["id"]  for s in salah_list]
    save_all_states(session_state)

    await update.message.reply_text(
        f"🔄 Mengulang soal yang salah — {ranger['name']}\n\n"
        f"Ada {len(salah_list)} soal yang perlu diulang.\n"
        f"Jawab satu per satu ya!"
    )
    await send_next_question(context.bot, chat_id, state, ranger)

# ── Handle pilihan mapel saat /latihan ───────────────
async def handle_mapel_pick(update: Update, context: ContextTypes.DEFAULT_TYPE, state, ranger):
    chat_id = update.effective_chat.id
    text    = update.message.text.strip()

    mapel_options = context.user_data.get("mapel_options", [])

    try:
        pick = int(text)
    except ValueError:
        await update.message.reply_text("Ketik nomor yang tersedia ya!")
        return

    if pick == 0:
        mapel = "Semua"
    elif 1 <= pick <= len(mapel_options):
        mapel = mapel_options[pick - 1][0]
    else:
        await update.message.reply_text("Nomor tidak tersedia, coba lagi!")
        return

    soal_list = get_random_soal(chat_id, mapel if mapel != "Semua" else None, count=10)
    if not soal_list:
        await update.message.reply_text(f"Belum ada soal untuk {mapel}.")
        return

    state["waiting_for_mapel_pick"] = False
    state["awaiting_answers"]  = True
    state["current_question"]  = 0
    state["correct_count"]     = 0
    state["points_today"]      = 0
    state["questions"]         = [s["soal"]       for s in soal_list]
    state["keys"]              = [s["kunci"]      for s in soal_list]
    state["pembahasan"]        = [s["pembahasan"] for s in soal_list]
    state["latihan_soal_ids"]  = [s["id"]         for s in soal_list]
    save_all_states(session_state)

    label = f"Mapel: {mapel}" if mapel != "Semua" else "Semua mapel"
    await update.message.reply_text(
        f"🎯 Latihan dimulai! ({label})\n\n"
        f"Ada {len(soal_list)} soal random dari bank soal kamu.\n"
        f"Jawab satu per satu ya!"
    )
    await send_next_question(context.bot, chat_id, state, ranger)

# ── Kirim apresiasi sticker ───────────────────────────
async def send_celebration(bot, chat_id):
    if CELEBRATION_STICKERS:
        try:
            await bot.send_sticker(chat_id=chat_id, sticker=random.choice(CELEBRATION_STICKERS))
            return
        except Exception as e:
            print(f"Sticker error: {e}")
    # Fallback jika list kosong atau gagal
    await bot.send_message(chat_id=chat_id, text="🎉🏆⚡🌟🎊💥🔥👑")

# ── Capture sticker file_id (untuk setup CELEBRATION_STICKERS) ──
async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sticker = update.message.sticker
    await update.message.reply_text(f"file_id: {sticker.file_id}")

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
