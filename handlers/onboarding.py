"""
onboarding.py — Registrasi keluarga baru via invite code.

Flow:
1. Superadmin: /invite            → kode BRGR-XXXXXX untuk parent baru
2. Parent baru: /daftar BRGR-XXX  → keluarga terbentuk (plan trial)
3. Parent: /tambahanak            → flow tanya nama & jenjang → kode ANAK-XXXXXX
4. Anak kirim kode ANAK-XXXXXX    → terdaftar sebagai ranger, warna otomatis

Keamanan: kode dibuat di utils/families.py (secrets, single-use, expired 7 hari,
terikat tipe & keluarga). Flow /tambahanak hanya jalan untuk parent terdaftar.
"""

import re
from telegram import Update
from telegram.ext import ContextTypes
from utils.families import (
    is_parent, is_superadmin, is_ranger,
    create_parent_invite, create_ranger_invite, use_invite,
    get_family_rangers, get_parent_name,
    MAX_RANGERS_PER_FAMILY, INVITE_TTL_DAYS,
)

# Flow state /tambahanak (in-memory; flow-nya pendek, aman hilang saat restart)
_flows = {}

LEVEL_OPTIONS = {
    "1": ("SD Kelas 1", 15),  # SD kelas 1-3
    "2": ("SD Kelas 4", 20),  # SD kelas 4-6
    "3": ("SMP",        25),
}

_CODE_RE = re.compile(r"^(BRGR|ANAK)-[A-Z0-9]{4,8}$", re.IGNORECASE)

# ── /invite (superadmin) ──────────────────────────────────
async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_superadmin(update.effective_chat.id):
        return
    code = create_parent_invite()
    await update.message.reply_text(
        f"🎟 Kode undangan keluarga baru:\n\n"
        f"`{code}`\n\n"
        f"Bagikan ke orang tua keluarga trial. Cara pakai:\n"
        f"1. Buka bot ini di Telegram\n"
        f"2. Ketik: /daftar {code}\n\n"
        f"⏳ Berlaku {INVITE_TTL_DAYS} hari, sekali pakai.",
        parse_mode="Markdown",
    )

# ── /daftar <kode> ────────────────────────────────────────
async def handle_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_parent(chat_id) or is_ranger(chat_id):
        await update.message.reply_text("Kamu sudah terdaftar di BrainRanger! 😊")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Cara daftar: /daftar KODE\n"
            "Contoh: /daftar BRGR-AB2CD3\n\n"
            "Belum punya kode? Minta ke pemilik bot ya!"
        )
        return

    await _register_with_code(update, args[0])

async def _register_with_code(update: Update, code: str):
    chat_id = update.effective_chat.id
    tg_name = (update.effective_user.first_name or "").strip()

    try:
        result = use_invite(code, chat_id, name=tg_name)
    except ValueError as e:
        await update.message.reply_text(f"❌ {e}")
        return

    if result["type"] == "parent":
        await update.message.reply_text(
            f"🎉 Selamat datang di BrainRanger, {tg_name or 'Bunda/Ayah'}!\n\n"
            f"Keluargamu sudah terdaftar. Langkah berikutnya:\n"
            f"1. Ketik /tambahanak untuk mendaftarkan anak\n"
            f"2. Bot akan kasih kode — minta anak kirim kode itu ke bot ini\n"
            f"3. Anak langsung bisa mulai belajar dengan /mulai\n\n"
            f"Kamu akan menerima laporan belajar anak otomatis setiap hari. "
            f"Ketik /help untuk lihat semua perintah!"
        )
    else:
        p = result["profile"]
        await update.message.reply_text(
            f"🎉 Selamat datang, {p['name']}!\n"
            f"Kamu sekarang adalah {p['emoji']} {p['ranger']}!\n\n"
            f"Siap activate brain power? Ketik /mulai untuk sesi belajar pertamamu! ⚡"
        )

# ── /tambahanak (parent) ──────────────────────────────────
async def handle_tambahanak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_parent(chat_id):
        return

    if len(get_family_rangers(chat_id)) >= MAX_RANGERS_PER_FAMILY:
        await update.message.reply_text(
            f"Keluargamu sudah punya {MAX_RANGERS_PER_FAMILY} ranger (maksimal)."
        )
        return

    _flows[chat_id] = {"step": "name"}
    await update.message.reply_text(
        "Siapa nama anak yang mau didaftarkan?\n"
        "(ketik `batal` untuk membatalkan)",
        parse_mode="Markdown",
    )

# ── Teks bebas dari parent (flow) atau user belum terdaftar ──
async def handle_freeform_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dipanggil dari handle_answer ketika pengirim BUKAN ranger.
    Menangani: flow /tambahanak milik parent, dan kode undangan
    yang dikirim sebagai teks biasa oleh user belum terdaftar.
    """
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # 1. Flow /tambahanak
    flow = _flows.get(chat_id)
    if flow and is_parent(chat_id):
        if text.lower() == "batal":
            del _flows[chat_id]
            await update.message.reply_text("Oke, dibatalkan.")
            return

        if flow["step"] == "name":
            if not (1 <= len(text) <= 30):
                await update.message.reply_text("Nama 1-30 karakter ya. Coba lagi:")
                return
            flow["name"] = text
            flow["step"] = "level"
            await update.message.reply_text(
                f"Jenjang sekolah {text}? Ketik nomornya:\n\n"
                f"1. SD Kelas 1-3\n"
                f"2. SD Kelas 4-6\n"
                f"3. SMP"
            )
            return

        if flow["step"] == "level":
            opt = LEVEL_OPTIONS.get(text)
            if not opt:
                await update.message.reply_text("Ketik 1, 2, atau 3 ya!")
                return
            level, focus = opt
            profile = {
                "name": flow["name"], "level": level,
                "focus_minutes": focus, "break_minutes": 5, "sessions": 2,
            }
            try:
                code = create_ranger_invite(chat_id, profile)
            except ValueError as e:
                del _flows[chat_id]
                await update.message.reply_text(f"❌ {e}")
                return
            del _flows[chat_id]
            await update.message.reply_text(
                f"✅ {flow['name']} siap didaftarkan!\n\n"
                f"Kode untuk {flow['name']}:\n\n"
                f"`{code}`\n\n"
                f"Minta {flow['name']} buka bot ini di Telegram-nya sendiri "
                f"lalu kirim kode di atas sebagai pesan.\n"
                f"⏳ Berlaku {INVITE_TTL_DAYS} hari, sekali pakai.\n\n"
                f"Mau daftarkan anak lagi? Ketik /tambahanak",
                parse_mode="Markdown",
            )
            return

    # 2. User belum terdaftar kirim kode sebagai teks biasa
    if _CODE_RE.match(text) and not is_parent(chat_id) and not is_ranger(chat_id):
        await _register_with_code(update, text)
        return
