import asyncio
import base64
import datetime
import os
import random
from telegram import Update
from telegram.ext import ContextTypes
from config import get_ranger, PARENT_CHAT_ID
from handlers.ai_processor import process_photos, process_text_content, evaluate_answer
from utils.doc_extractor import extract_document
from utils.message_splitter import split_message, to_html, strip_markdown
from utils.state_manager import load_all_states, save_all_states
from utils.points import add_points, update_streak, get_streak, get_total_points, get_rank
from utils.bank_soal import save_session, compute_soal_ids, get_mapel_list, get_random_soal, get_salah_soal, update_result, get_stats, get_weak_topics, UJIAN_SOAL_COUNT
from handlers.sheets import log_session, log_skip
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
        "mode": "normal",             # "normal" | "latihan" | "ulang" | "ujian"
        "waiting_for_skip_reason": False,
        "waiting_for_mapel_pick": False,
        "latihan_soal_ids": [],       # soal IDs dari bank untuk update hasil
        "ujian_results": {},          # {"Matematika": {"benar": 5, "total": 10}, ...}
        "ujian_mapel_done": [],       # mapel yang sudah dikerjakan di sesi ujian
        "pending_document_text": "",  # teks hasil ekstrak PDF/DOCX
        "document_ready": False,      # True jika dokumen sudah di-upload dan siap proses
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
    state["session_start"] = str(datetime.datetime.now())
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
    save_all_states(session_state)  # simpan agar foto tidak hilang jika bot restart

    count = len(state["pending_photos"])
    await update.message.reply_text(
        f"Foto {count} diterima!\n"
        f"Kirim foto berikutnya atau ketik /selesai kalau sudah semua."
    )

# ── Handler dokumen (PDF / DOCX) ─────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)
    if not state.get("waiting_for_photo"):
        await update.message.reply_text(
            f"{ranger['emoji']} Kamu belum mulai sesi belajar.\n"
            f"Ketik /mulai dulu, baru kirim foto atau dokumen ya!"
        )
        return

    doc       = update.message.document
    mime_type = doc.mime_type or ""
    file_name = doc.file_name or ""

    # Validasi tipe file
    allowed_mimes = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
    allowed_ext = {".pdf", ".docx", ".doc"}
    ext = os.path.splitext(file_name.lower())[1]

    if mime_type not in allowed_mimes and ext not in allowed_ext:
        await update.message.reply_text(
            f"{ranger['emoji']} Format file tidak didukung.\n\n"
            f"Yang bisa diupload:\n"
            f"• 📄 PDF (.pdf)\n"
            f"• 📝 Word (.docx)\n\n"
            f"Atau kamu bisa kirim foto buku langsung ya!"
        )
        return

    await update.message.reply_text(
        f"{ranger['emoji']} Dokumen diterima! Sedang membaca isi file... ⏳"
    )

    # Download file
    try:
        tg_file    = await doc.get_file()
        file_bytes = await tg_file.download_as_bytearray()
    except Exception as e:
        await update.message.reply_text(
            f"Gagal download file: {str(e)}\n"
            f"Coba kirim ulang atau pakai foto saja ya!"
        )
        return

    # Extract teks
    result = extract_document(bytes(file_bytes), mime_type or f"application/{ext.lstrip('.')}")

    if result["scanned"]:
        await update.message.reply_text(
            f"{ranger['emoji']} PDF ini sepertinya hasil scan (tidak ada teks).\n\n"
            f"Untuk PDF scan, gunakan foto halaman buku langsung ya!\n"
            f"Caranya ketik /mulai lalu kirim foto seperti biasa. 📸"
        )
        return

    if not result["success"]:
        err = result.get("error") or "Tidak ada teks yang bisa dibaca"
        await update.message.reply_text(
            f"{ranger['emoji']} Gagal membaca dokumen: {err}\n\n"
            f"Coba format lain atau kirim foto langsung ya!"
        )
        return

    # Simpan ke state
    state["pending_document_text"] = result["text"]
    state["document_ready"]        = True
    state["pending_photos"]        = []   # clear foto jika ada
    save_all_states(session_state)

    truncate_note = (
        "\n\n⚠️ Dokumen terlalu panjang — hanya 6.000 kata pertama yang diproses."
        if result["truncated"] else ""
    )
    file_type = "PDF" if mime_type == "application/pdf" else "Word"
    word_count = len(result["text"].split())

    await update.message.reply_text(
        f"✅ {file_type} berhasil dibaca!\n"
        f"📊 {word_count:,} kata terdeteksi.{truncate_note}\n\n"
        f"Ketik /selesai untuk mulai proses materi! ⚡"
    )


# ── /selesai ──────────────────────────────────────────
async def handle_selesai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)

    # Guard dulu sebelum reset apapun
    if not state.get("waiting_for_photo"):
        await update.message.reply_text(
            f"{ranger['emoji']} Tidak ada foto yang sedang menunggu diproses.\n"
            f"Ketik /mulai untuk mulai sesi belajar baru ya!"
        )
        return

    # Reset data lama hanya jika memang sedang dalam mode upload foto
    state["questions"] = []
    state["keys"] = []
    state["pembahasan"] = []
    state["rangkuman"] = ""
    state["answers"] = []
    state["correct_count"] = 0
    state["current_question"] = 0
    state["awaiting_answers"] = False

    # ── Branch: dokumen (PDF/DOCX) ───────────────────
    if state.get("document_ready"):
        doc_text = state.get("pending_document_text", "")
        if not doc_text.strip():
            await update.message.reply_text(
                "Teks dokumen tidak ditemukan. Coba upload ulang atau pakai foto ya!"
            )
            return

        await update.message.reply_text(
            f"{ranger['emoji']} Memproses dokumen...\n"
            f"BrainRanger lagi activate power-mu dari file ini! ⚡"
        )

        try:
            result = await asyncio.to_thread(process_text_content, doc_text, ranger)
        except Exception as e:
            await update.message.reply_text(
                f"Waduh ada error saat proses dokumen: {str(e)}\n"
                f"Coba lagi ya!"
            )
            return

    # ── Branch: foto ─────────────────────────────────
    else:
        photos = state["pending_photos"]
        if not photos:
            await update.message.reply_text(
                f"{ranger['emoji']} Belum ada foto atau dokumen!\n\n"
                f"Kamu bisa:\n"
                f"• 📸 Kirim foto halaman buku\n"
                f"• 📄 Upload file PDF atau Word (.docx)\n\n"
                f"Lalu ketik /selesai kalau sudah."
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
    state["pending_document_text"] = ""   # clear setelah diproses
    state["document_ready"] = False
    state["active"] = True

    # Simpan soal ke bank SEKARANG (sebelum sesi jawab) supaya update_result bisa jalan
    topik_bank = result.get("topik", "")
    try:
        await asyncio.to_thread(
            save_session, chat_id, topik_bank,
            result["soal"], result["kunci"], result["pembahasan"]
        )
    except Exception as e:
        print(f"save_session error (handle_selesai): {e}")
    # Selalu set IDs — meski save_session gagal, soal mungkin sudah ada di bank (dedup)
    state["latihan_soal_ids"] = compute_soal_ids(result["soal"])
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

    # ── Generate SVG + Podcast secara paralel ────────
    from handlers.tts import generate_podcast
    rangkuman_tts = strip_markdown(rangkuman)

    async def _gen_svg():
        if not needs_illustration(rangkuman):
            return None
        try:
            svg = await asyncio.to_thread(generate_illustration, rangkuman[:400], ranger["level"])
            if svg:
                return await asyncio.to_thread(svg_to_png, svg)
        except Exception as e:
            print(f"Ilustrasi rangkuman gagal: {e}")
        return None

    async def _gen_audio():
        try:
            return await asyncio.to_thread(
                generate_podcast, rangkuman_tts, ranger["name"], ranger["level"]
            )
        except Exception as e:
            print(f"TTS error: {e}")
        return None

    png, podcast_path = await asyncio.gather(_gen_svg(), _gen_audio())

    if png:
        await update.message.reply_photo(photo=png, caption="📐 Ilustrasi materi")

    if podcast_path:
        try:
            with open(podcast_path, "rb") as audio:
                await update.message.reply_audio(
                    audio=audio,
                    title=f"Podcast Materi - {ranger['name']}",
                    caption="Dengerin sambil belajar ya! 🎧",
                )
            os.remove(podcast_path)
        except Exception as e:
            print(f"Audio send error: {e}")
    else:
        await update.message.reply_text(
            "Audio podcast tidak tersedia, tapi rangkuman text sudah ada ya!"
        )

    total_soal = len(state["questions"])
    await update.message.reply_text(
        f"✅ Materi siap!\n\n"
        f"Ada {total_soal} soal menunggumu.\n"
        f"Kalau sudah siap, ketik /lanjut untuk mulai test! 💪"
    )

# ── /lanjut → mulai atau resume sesi test ────────────
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

    current_q = state.get("current_question", 0)
    total_soal = len(state["questions"])

    # Resume sesi yang sedang berjalan (misal setelah bot restart)
    if current_q > 0 and current_q < total_soal:
        state["awaiting_answers"] = True
        save_all_states(session_state)
        await update.message.reply_text(
            f"↩️ Melanjutkan sesi sebelumnya...\n\n"
            f"Kamu sudah di soal {current_q + 1}/{total_soal}.\n"
            f"Jawaban sebelumnya ({current_q} soal) tetap tersimpan! ✅"
        )
        await send_next_question(context.bot, chat_id, state, ranger)
        return

    # Mulai fresh dari soal 1
    state["current_session"] = 2
    state["awaiting_answers"] = True
    state["current_question"] = 0
    state["answers"] = []
    state["correct_count"] = 0
    save_all_states(session_state)

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

    # Handle alasan skip
    if state.get("waiting_for_skip_reason"):
        await handle_skip_reason(update, context, state, ranger)
        return

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

    # Update bank soal untuk SEMUA mode (termasuk normal)
    # BENAR=True (keluar dari /ulang), SEBAGIAN/SALAH=False (tetap muncul di /ulang)
    soal_ids = state.get("latihan_soal_ids", [])
    if soal_ids and current_q < len(soal_ids):
        try:
            await asyncio.to_thread(update_result, chat_id, soal_ids[current_q], verdict == "BENAR")
        except Exception as e:
            print(f"update_result error soal {current_q}: {e}")

    state["current_question"] += 1
    save_all_states(session_state)

    if state["current_question"] >= len(state["questions"]):
        state["awaiting_answers"] = False
        correct = state["correct_count"]
        total_q = len(state["questions"])
        mode    = state.get("mode", "normal")
        save_all_states(session_state)

        if mode == "ujian":
            # Simpan hasil mapel ini
            current_mapel = state.get("ujian_current_mapel", "")
            if current_mapel:
                if "ujian_results" not in state:
                    state["ujian_results"] = {}
                state["ujian_results"][current_mapel] = {
                    "benar": correct,
                    "total": total_q,
                }
                if "ujian_mapel_done" not in state:
                    state["ujian_mapel_done"] = []
                if current_mapel not in state["ujian_mapel_done"]:
                    state["ujian_mapel_done"].append(current_mapel)

            # Tampilkan hasil mapel ini
            pct = round(correct / total_q * 100) if total_q > 0 else 0
            status_icon = "✅" if pct >= 70 else "⚠️" if pct >= 40 else "❌"
            await update.message.reply_text(
                f"{status_icon} Selesai ujian {current_mapel}!\n\n"
                f"Benar: {correct}/{total_q} ({pct}%)\n"
                f"Power: +{state['points_today']} ⚡"
            )
            await send_celebration(context.bot, chat_id)

            # Tawarkan mapel berikutnya
            await _show_ujian_mapel_picker(update, context, chat_id, ranger, state)
            return

        elif mode in ("latihan", "ulang"):
            # Selesai latihan/ulang — tidak notif Angela, tidak log sheets, tidak update streak
            label = "LATIHAN" if mode == "latihan" else "ULANG SOAL"
            await update.message.reply_text(
                f"🎯 {label} SELESAI!\n\n"
                f"Benar: {correct}/{total_q}\n"
                f"Power: +{state['points_today']} ⚡\n\n"
                f"Ketik /latihan untuk latihan lagi atau /ulang untuk soal yang masih salah!"
            )
            await send_celebration(context.bot, chat_id)
        else:
            # Sesi normal — set done, update streak, log ke sheets
            # (save_session sudah dipanggil di handle_selesai sebelum sesi jawab)
            state["all_sessions_done"] = True
            save_all_states(session_state)  # pastikan all_sessions_done tersimpan
            streak, longest_streak = update_streak(chat_id)
            topik = state.get("topic", "")

            asyncio.create_task(asyncio.to_thread(
                log_session, ranger, correct, total_q,
                state["points_today"], streak, longest_streak, topik
            ))

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

            # ── Insight topik lemah ───────────────────
            weak = get_weak_topics(chat_id, top_n=3)
            if weak:
                top = weak[0]
                weak_lines = "\n".join(
                    f"  {'🔴' if i == 0 else '🟡'} {w['mapel']} — {w['salah']}x salah"
                    for i, w in enumerate(weak)
                )
                await update.message.reply_text(
                    f"📊 Analisis belajarmu:\n\n"
                    f"{weak_lines}\n\n"
                    f"💡 Paling perlu diulang: {top['mapel']}\n"
                    f"Ketik /ulang untuk latihan soal yang masih salah!"
                )

            await context.bot.send_message(
                chat_id=PARENT_CHAT_ID,
                text=(
                    f"{ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
                    f"selesai belajar! ✅\n"
                    f"Soal benar: {correct}/{total_q}\n"
                    f"Power: +{state['points_today']} ⚡"
                    + (f"\n📊 Topik lemah: {weak[0]['mapel']} ({weak[0]['salah']}x salah)" if weak else "")
                )
            )
    else:
        await send_next_question(context.bot, chat_id, state, ranger)

# ── /ujian ───────────────────────────────────────────
async def handle_ujian(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    mapel_list = get_mapel_list(chat_id)
    if not mapel_list:
        await update.message.reply_text(
            f"{ranger['emoji']} Bank soal masih kosong!\n\n"
            f"Selesaikan minimal 1 sesi belajar dulu sebelum ujian. 💪"
        )
        return

    count = UJIAN_SOAL_COUNT.get(ranger["level"], 10)
    state = get_state(chat_id)
    state["mode"]              = "ujian"
    state["waiting_for_mapel_pick"] = True
    state["awaiting_answers"]  = False
    state["ujian_results"]     = {}
    state["ujian_mapel_done"]  = []
    state["ujian_current_mapel"] = ""
    state["points_today"]      = 0   # reset di awal ujian, akumulasi lintas mapel
    save_all_states(session_state)

    msg = (
        f"📝 Mode Ujian — {ranger['name']}\n"
        f"Setiap mapel: {count} soal\n\n"
        f"Pilih mapel yang mau diujikan (ketik nomornya):\n\n"
        f"0. Selesai ujian & lihat rekap\n"
    )
    mapel_options = list(mapel_list.items())
    for i, (mapel, jumlah) in enumerate(mapel_options, start=1):
        done_mark = " ✅" if mapel in state["ujian_mapel_done"] else ""
        msg += f"{i}. {mapel} ({jumlah} soal tersedia){done_mark}\n"

    state["mapel_options"] = mapel_options
    await update.message.reply_text(msg)

# ── Tampilkan mapel picker ujian (setelah selesai 1 mapel) ──
async def _show_ujian_mapel_picker(update, context, chat_id, ranger, state):
    mapel_list   = get_mapel_list(chat_id)
    mapel_options = list(mapel_list.items())
    done_list    = state.get("ujian_mapel_done", [])
    count        = UJIAN_SOAL_COUNT.get(ranger["level"], 10)

    sisa = [(m, j) for m, j in mapel_options if m not in done_list]

    if not sisa:
        # Semua mapel sudah dikerjakan, langsung rekap
        await _send_ujian_recap(update, context, chat_id, ranger, state)
        return

    state["waiting_for_mapel_pick"] = True
    state["mode"] = "ujian"
    save_all_states(session_state)

    msg = (
        f"✅ Mapel selesai! Lanjut ujian mapel lain?\n\n"
        f"Setiap mapel: {count} soal\n\n"
        f"0. Selesai & lihat rekap\n"
    )
    semua_options = []
    idx = 1
    for mapel, jumlah in mapel_options:
        done_mark = " ✅" if mapel in done_list else ""
        msg += f"{idx}. {mapel} ({jumlah} soal){done_mark}\n"
        semua_options.append((mapel, jumlah))
        idx += 1

    state["mapel_options"] = semua_options
    await update.message.reply_text(msg)

# ── Rekap akhir ujian ─────────────────────────────────
async def _send_ujian_recap(update, context, chat_id, ranger, state):
    results = state.get("ujian_results", {})
    if not results:
        await update.message.reply_text("Belum ada mapel yang diselesaikan.")
        return

    total_benar = sum(v["benar"] for v in results.values())
    total_soal  = sum(v["total"] for v in results.values())
    pct_total   = round(total_benar / total_soal * 100) if total_soal > 0 else 0

    lines = ""
    for mapel, v in results.items():
        pct = round(v["benar"] / v["total"] * 100) if v["total"] > 0 else 0
        icon = "✅" if pct >= 70 else "⚠️" if pct >= 40 else "❌"
        lines += f"  {icon} {mapel}: {v['benar']}/{v['total']} ({pct}%)\n"

    total_power = state.get("points_today", 0)
    recap_msg = (
        f"🏆 REKAP UJIAN — {ranger['name']}\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"{lines}\n"
        f"Total: {total_benar}/{total_soal} ({pct_total}%)\n"
        f"⚡ Power diraih: +{total_power}\n\n"
    )
    if pct_total >= 80:
        recap_msg += "🌟 Luar biasa! Siap menghadapi ujian!"
    elif pct_total >= 60:
        recap_msg += "💪 Bagus! Tinggal perkuat yang masih ⚠️"
    else:
        recap_msg += "📚 Masih perlu latihan lagi. Ketik /ulang ya!"

    await update.message.reply_text(recap_msg)

    # Notif Angela
    await context.bot.send_message(
        chat_id=PARENT_CHAT_ID,
        text=(
            f"📝 {ranger['emoji']} {ranger['name']} selesai ujian simulasi!\n\n"
            f"{lines}\n"
            f"Total: {total_benar}/{total_soal} ({pct_total}%)"
        )
    )

    # Reset mode
    state["mode"] = "normal"
    state["waiting_for_mapel_pick"] = False
    save_all_states(session_state)

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

    state["mapel_options"] = mapel_options
    await update.message.reply_text(msg)

# ── /ulang ────────────────────────────────────────────
async def handle_ulang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    state = get_state(chat_id)

    # Filter berdasarkan mapel yang dipelajari hari ini (jika ada)
    from datetime import date as _date
    session_start = state.get("session_start", "")
    topik_hari_ini = state.get("topic", "")
    is_today = bool(session_start and session_start.startswith(str(_date.today())))

    if topik_hari_ini and is_today:
        mapel_filter = topik_hari_ini.split("/")[0].strip() if "/" in topik_hari_ini else topik_hari_ini or None
    else:
        mapel_filter = None  # Tidak ada sesi hari ini, tampilkan semua

    salah_list = get_salah_soal(chat_id, mapel=mapel_filter)

    if not salah_list:
        stats = get_stats(chat_id)
        if stats["total"] == 0:
            # Bank soal belum ada sama sekali
            await update.message.reply_text(
                f"{ranger['emoji']} Bank soal masih kosong!\n\n"
                f"Selesaikan minimal 1 sesi belajar dulu, baru bisa pakai /ulang. 💪"
            )
        elif mapel_filter and get_salah_soal(chat_id):
            # Ada soal salah tapi di mapel lain, bukan mapel hari ini
            await update.message.reply_text(
                f"{ranger['emoji']} Tidak ada soal salah untuk {mapel_filter}!\n\n"
                f"Semua soal {mapel_filter} yang pernah dicoba sudah benar 🎉\n"
                f"Ketik /latihan untuk latihan mapel lain."
            )
        elif stats["belum_dicoba"] == stats["total"]:
            # Semua soal ada tapi belum pernah dicoba
            await update.message.reply_text(
                f"{ranger['emoji']} Belum ada soal yang tercatat salah.\n\n"
                f"Bank soal punya {stats['total']} soal tapi belum ada riwayat jawaban.\n"
                f"Lakukan sesi belajar baru (/mulai) dan jawab beberapa soal salah, "
                f"baru /ulang bisa dipakai! 💪"
            )
        else:
            # Ada soal, sudah pernah dicoba, tapi semua benar
            await update.message.reply_text(
                f"{ranger['emoji']} Tidak ada soal yang salah!\n\n"
                f"Semua soal yang pernah dicoba sudah dijawab benar 🎉\n"
                f"Ketik /latihan untuk latihan soal random."
            )
        return

    # Batasi jumlah soal ulang sesuai level
    limit = UJIAN_SOAL_COUNT.get(ranger["level"], 10)
    total_salah = len(salah_list)
    salah_list  = salah_list[:limit]

    state = get_state(chat_id)
    state["mode"] = "ulang"
    state["awaiting_answers"] = True
    state["waiting_for_mapel_pick"] = False
    state["current_question"] = 0
    state["correct_count"] = 0
    state["points_today"] = 0
    state["questions"]  = [s["soal"]       for s in salah_list]
    state["keys"]       = [s["kunci"]      for s in salah_list]
    state["pembahasan"] = [s["pembahasan"] for s in salah_list]
    state["latihan_soal_ids"] = [s["id"]   for s in salah_list]
    save_all_states(session_state)

    sisa_msg = f" ({total_salah - limit} soal salah lainnya bisa diulang berikutnya)" if total_salah > limit else ""
    mapel_label = f" — {mapel_filter}" if mapel_filter else " — semua mapel"
    await update.message.reply_text(
        f"🔄 Mengulang soal yang salah{mapel_label}\n\n"
        f"Ada {len(salah_list)} soal yang perlu diulang.{sisa_msg}\n"
        f"Jawab satu per satu ya!"
    )
    await send_next_question(context.bot, chat_id, state, ranger)

# ── Handle pilihan mapel saat /latihan ───────────────
async def handle_mapel_pick(update: Update, context: ContextTypes.DEFAULT_TYPE, state, ranger):
    chat_id = update.effective_chat.id
    text    = update.message.text.strip()

    mapel_options = state.get("mapel_options", [])

    try:
        pick = int(text)
    except ValueError:
        await update.message.reply_text("Ketik nomor yang tersedia ya!")
        return

    mode = state.get("mode", "latihan")

    # Pilih 0 = selesai ujian & rekap
    if pick == 0:
        if mode == "ujian":
            state["waiting_for_mapel_pick"] = False
            save_all_states(session_state)
            await _send_ujian_recap(update, context, chat_id, ranger, state)
            return
        else:
            mapel = "Semua"
    elif 1 <= pick <= len(mapel_options):
        mapel = mapel_options[pick - 1][0]
    else:
        await update.message.reply_text("Nomor tidak tersedia, coba lagi!")
        return

    # Jumlah soal adaptive per level (berlaku untuk semua mode)
    count = UJIAN_SOAL_COUNT.get(ranger["level"], 10)

    soal_list = get_random_soal(chat_id, mapel if mapel != "Semua" else None, count=count)
    if not soal_list:
        await update.message.reply_text(f"Belum ada soal untuk {mapel}.")
        return

    state["waiting_for_mapel_pick"] = False
    state["awaiting_answers"]  = True
    state["current_question"]  = 0
    state["correct_count"]     = 0
    if mode != "ujian":
        state["points_today"]  = 0   # ujian: points_today akumulasi lintas mapel
    state["questions"]         = [s["soal"]       for s in soal_list]
    state["keys"]              = [s["kunci"]      for s in soal_list]
    state["pembahasan"]        = [s["pembahasan"] for s in soal_list]
    state["latihan_soal_ids"]  = [s["id"]         for s in soal_list]
    if mode == "ujian":
        state["ujian_current_mapel"] = mapel
    save_all_states(session_state)

    if mode == "ujian":
        label_prefix = "📝 Ujian"
    else:
        label_prefix = "🎯 Latihan"

    label = f"Mapel: {mapel}" if mapel != "Semua" else "Semua mapel"
    await update.message.reply_text(
        f"{label_prefix} dimulai! ({label})\n\n"
        f"Ada {len(soal_list)} soal.\n"
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

# ── /status ───────────────────────────────────────────
async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    state   = get_state(chat_id)
    mode    = state.get("mode", "normal")
    mode_label = {
        "normal":  "Sesi Belajar",
        "latihan": "Latihan",
        "ulang":   "Ulang Soal",
        "ujian":   "Ujian",
    }.get(mode, mode)

    if state.get("all_sessions_done") and not state.get("waiting_for_skip_reason"):
        from utils.points import get_today_points
        today  = get_today_points(chat_id)
        streak, _ = get_streak(chat_id)
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"✅ Belajar hari ini sudah selesai!\n"
            f"⚡ Poin hari ini: +{today}\n"
            f"🔥 Streak: {streak} hari\n\n"
            f"Ketik /latihan atau /ujian untuk latihan tambahan!"
        )
    elif state.get("awaiting_answers"):
        current_q = state.get("current_question", 0)
        total_q   = len(state.get("questions", []))
        correct   = state.get("correct_count", 0)
        pts       = state.get("points_today", 0)
        mapel_info = f" — {state.get('ujian_current_mapel', '')}" if mode == "ujian" else ""
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"📝 Mode: {mode_label}{mapel_info}\n"
            f"❓ Soal: {current_q}/{total_q}\n"
            f"✅ Benar: {correct}\n"
            f"⚡ Poin sesi ini: +{pts}\n\n"
            f"Ketik jawabanmu untuk lanjut!"
        )
    elif state.get("waiting_for_photo"):
        count = len(state.get("pending_photos", []))
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"📸 Upload foto ({count} foto diterima)\n"
            f"Kirim lebih banyak foto atau ketik /selesai"
        )
    elif state.get("questions") and not state.get("awaiting_answers"):
        total_q = len(state.get("questions", []))
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"✅ Materi sudah diproses ({total_q} soal siap)\n"
            f"Ketik /lanjut untuk mulai mengerjakan soal!"
        )
    elif state.get("waiting_for_mapel_pick"):
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"📋 Menunggu pilihan mapel\n"
            f"Ketik nomor mapel yang ingin dikerjakan!"
        )
    else:
        streak, _ = get_streak(chat_id)
        streak_str = f"🔥 Streak: {streak} hari" if streak > 0 else "💪 Belum ada streak"
        await update.message.reply_text(
            f"{ranger['emoji']} Status {ranger['name']}\n\n"
            f"😴 Belum mulai belajar hari ini.\n"
            f"{streak_str}\n\n"
            f"Ketik /mulai untuk mulai! ⚡"
        )

# ── /bankinfo — diagnosa bank soal (debug) ───────────
async def handle_bankinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    ranger  = get_ranger(chat_id)
    if not ranger:
        return

    from utils.bank_soal import BANK_FILE
    stats    = get_stats(chat_id)
    mapels   = get_mapel_list(chat_id)
    state    = get_state(chat_id)
    soal_ids = state.get("latihan_soal_ids", [])

    mapel_lines = "\n".join(f"  • {m}: {n} soal" for m, n in mapels.items()) or "  (kosong)"
    msg = (
        f"🔧 Bank Info — {ranger['name']}\n\n"
        f"📁 File: {BANK_FILE}\n\n"
        f"📊 Statistik:\n"
        f"  Total soal   : {stats['total']}\n"
        f"  Salah (False): {stats['salah']}\n"
        f"  Belum dicoba : {stats['belum_dicoba']}\n"
        f"  Sudah benar  : {stats['total'] - stats['salah'] - stats['belum_dicoba']}\n\n"
        f"📚 Per mapel:\n{mapel_lines}\n\n"
        f"🔑 latihan_soal_ids aktif: {len(soal_ids)} ID"
    )
    await update.message.reply_text(msg)

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

    state = get_state(chat_id)

    # Hentikan sesi apapun yang sedang berjalan
    state["awaiting_answers"]       = False
    state["waiting_for_mapel_pick"] = False
    state["waiting_for_skip_reason"] = True
    save_all_states(session_state)

    await update.message.reply_text(
        f"{ranger['emoji']} Oke {ranger['name']}, skip hari ini.\n\n"
        f"Boleh tulis alasannya? (biar Angela tau 😊)"
    )

# ── Handler alasan skip ───────────────────────────────
async def handle_skip_reason(update: Update, context: ContextTypes.DEFAULT_TYPE, state, ranger):
    chat_id = update.effective_chat.id
    reason  = update.message.text.strip()

    state["waiting_for_skip_reason"] = False
    state["all_sessions_done"] = True  # Anggap hari ini selesai (skip)
    save_all_states(session_state)

    await update.message.reply_text(
        f"📝 Noted! Alasan kamu sudah dicatat.\n\n"
        f"Semangat besok ya {ranger['name']}! 💪"
    )

    await context.bot.send_message(
        chat_id=PARENT_CHAT_ID,
        text=(
            f"⚠️ {ranger['emoji']} {ranger['name']} ({ranger['ranger']}) "
            f"skip belajar hari ini.\n"
            f"📝 Alasan: {reason}"
        )
    )

    # Simpan ke Sheets (fire-and-forget)
    asyncio.create_task(asyncio.to_thread(log_skip, ranger, reason))
