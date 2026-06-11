"""
usage.py — Tracking pemakaian AI/TTS per keluarga + proteksi cost untuk BrainRanger.

Tiga lapis proteksi:
1. Hard cap per ranger per hari (sesi, dokumen, evaluasi jawaban) sesuai plan keluarga.
2. Kill-switch budget global: jika estimasi spend hari ini melewati DAILY_BUDGET_USD,
   semua panggilan AI di-pause otomatis sampai besok (atau /resume oleh superadmin).
3. Semua angka dicatat di usage.json supaya bisa diaudit via /usage.

Thread-safety: add_tokens/add_tts_chars dipanggil dari worker thread
(asyncio.to_thread), jadi semua mutasi dilindungi lock.
"""

import json
import os
import threading
import datetime

_BASE_DIR  = os.environ.get("DATA_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_FILE = os.path.join(_BASE_DIR, "usage.json")

WIB = datetime.timezone(datetime.timedelta(hours=7))

# Budget harian global (USD). Lewat ini → AI pause otomatis.
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "2.0"))

# Harga per 1 juta unit (USD) — update kalau pricing Anthropic/Google berubah
PRICE = {
    "sonnet_in":  3.00,   # Claude Sonnet input  / 1M token
    "sonnet_out": 15.00,  # Claude Sonnet output / 1M token
    "haiku_in":   1.00,   # Claude Haiku input   / 1M token
    "haiku_out":  5.00,   # Claude Haiku output  / 1M token
    "tts_chars":  4.00,   # Google TTS Standard  / 1M karakter
}

# Hard cap per ranger per hari, per plan keluarga
LIMITS = {
    "owner": {"sessions": 5, "docs": 4, "evals": 300, "photos_per_session": 15},
    "trial": {"sessions": 3, "docs": 2, "evals": 150, "photos_per_session": 10},
}
KEEP_DAYS = 35  # riwayat usage yang disimpan

_lock  = threading.Lock()
_cache = None

def get_limits(plan: str) -> dict:
    return LIMITS.get(plan, LIMITS["trial"])

def _today() -> str:
    return str(datetime.datetime.now(WIB).date())

# ── Load / save (panggil hanya saat memegang _lock) ───────
def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "days" in data:
                _cache = data
                return _cache
        except Exception as e:
            print(f"usage.json corrupt ({e}), mulai dari kosong")
    _cache = {"_meta": {}, "days": {}}
    return _cache

def _save():
    try:
        # Prune hari lama supaya file tidak membengkak
        days = _cache["days"]
        if len(days) > KEEP_DAYS:
            for d in sorted(days)[:-KEEP_DAYS]:
                del days[d]
        tmp = USAGE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
        os.replace(tmp, USAGE_FILE)
    except Exception as e:
        print(f"Error saving usage.json: {e}")

def _day_bucket(data, day=None):
    day = day or _today()
    return data["days"].setdefault(day, {"families": {}, "rangers": {}})

# ── Pencatatan ────────────────────────────────────────────
def add_tokens(family_id, model: str, input_tokens: int, output_tokens: int):
    """Catat token Claude. model: 'sonnet' | 'haiku'. Aman dipanggil dari thread."""
    if not family_id:
        return
    with _lock:
        data = _load()
        fam = _day_bucket(data)["families"].setdefault(family_id, {})
        fam[f"{model}_in"]  = fam.get(f"{model}_in", 0) + int(input_tokens)
        fam[f"{model}_out"] = fam.get(f"{model}_out", 0) + int(output_tokens)
        _save()

def add_tts_chars(family_id, chars: int):
    if not family_id:
        return
    with _lock:
        data = _load()
        fam = _day_bucket(data)["families"].setdefault(family_id, {})
        fam["tts_chars"] = fam.get("tts_chars", 0) + int(chars)
        _save()

def count_event(chat_id, kind: str):
    """Catat event per ranger hari ini. kind: 'sessions' | 'docs' | 'evals'."""
    with _lock:
        data = _load()
        r = _day_bucket(data)["rangers"].setdefault(str(chat_id), {})
        r[kind] = r.get(kind, 0) + 1
        _save()

def get_event_count(chat_id, kind: str) -> int:
    with _lock:
        data = _load()
        return data["days"].get(_today(), {}).get("rangers", {}).get(str(chat_id), {}).get(kind, 0)

# ── Estimasi cost ─────────────────────────────────────────
def estimate_cost(fam_usage: dict) -> float:
    return sum(fam_usage.get(k, 0) * price / 1_000_000 for k, price in PRICE.items())

def get_today_cost() -> float:
    with _lock:
        data = _load()
        fams = data["days"].get(_today(), {}).get("families", {})
        return sum(estimate_cost(f) for f in fams.values())

# ── Kill-switch ───────────────────────────────────────────
def is_ai_paused() -> bool:
    with _lock:
        meta = _load()["_meta"]
        if not meta.get("ai_paused"):
            return False
        # Pause karena budget berlaku per hari — besok otomatis aktif lagi.
        # Pause manual (/pause) bertahan sampai /resume.
        if not meta.get("manual") and meta.get("pause_date") != _today():
            meta["ai_paused"] = False
            meta["pause_reason"] = ""
            _save()
            return False
        return True

def set_ai_paused(paused: bool, reason: str = "", manual: bool = True):
    with _lock:
        meta = _load()["_meta"]
        meta["ai_paused"]    = paused
        meta["pause_reason"] = reason if paused else ""
        meta["pause_date"]   = _today() if paused else ""
        meta["manual"]       = manual if paused else False
        _save()

def check_budget():
    """
    Cek budget harian. Jika terlampaui dan belum pause → pause otomatis
    dan return pesan alert (sekali). Selain itu return None.
    """
    with _lock:
        data = _load()
        fams = data["days"].get(_today(), {}).get("families", {})
        cost = sum(estimate_cost(f) for f in fams.values())
        meta = data["_meta"]
        if cost >= DAILY_BUDGET_USD and not meta.get("ai_paused"):
            meta["ai_paused"]    = True
            meta["pause_reason"] = f"budget harian ${DAILY_BUDGET_USD:.2f} terlampaui (estimasi ${cost:.2f})"
            meta["pause_date"]   = _today()
            meta["manual"]       = False
            _save()
            return (
                f"🛑 BUDGET HARIAN TERLAMPAUI\n\n"
                f"Estimasi spend hari ini: ${cost:.2f} (batas ${DAILY_BUDGET_USD:.2f})\n"
                f"Semua fitur AI di-PAUSE otomatis sampai besok.\n\n"
                f"Ketik /resume untuk mengaktifkan lagi sekarang."
            )
        return None

def get_pause_info() -> str:
    with _lock:
        meta = _load()["_meta"]
        return meta.get("pause_reason", "")

# ── Ringkasan untuk /usage ────────────────────────────────
def get_usage_summary(days: int = 7) -> dict:
    """
    Agregasi usage `days` hari terakhir per keluarga:
    {family_id: {"cost": usd, "sonnet_in": .., ..., "today_cost": usd}}
    plus key "_rangers": {chat_id: {"sessions": n, "docs": n, "evals": n}} untuk hari ini.
    """
    with _lock:
        data   = _load()
        today  = _today()
        cutoff = str(datetime.datetime.now(WIB).date() - datetime.timedelta(days=days - 1))
        result = {}
        for day, bucket in data["days"].items():
            if day < cutoff:
                continue
            for fid, fam in bucket.get("families", {}).items():
                agg = result.setdefault(fid, {"cost": 0.0, "today_cost": 0.0})
                for k in PRICE:
                    agg[k] = agg.get(k, 0) + fam.get(k, 0)
                agg["cost"] += estimate_cost(fam)
                if day == today:
                    agg["today_cost"] += estimate_cost(fam)
        result["_rangers"] = data["days"].get(today, {}).get("rangers", {})
        return result
