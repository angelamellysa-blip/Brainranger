import json
import os
import random
import hashlib
from datetime import date

BANK_FILE = "bank_soal.json"

def _load():
    if os.path.exists(BANK_FILE):
        try:
            with open(BANK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save(data):
    try:
        with open(BANK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Bank soal save error: {e}")

def _soal_id(soal_text):
    return hashlib.md5(soal_text.encode()).hexdigest()[:8]

# ── Simpan soal dari sesi ke bank ────────────────────
def save_session(chat_id, topik, soal_list, kunci_list, pembahasan_list):
    data   = _load()
    key    = str(chat_id)
    today  = str(date.today())
    mapel  = topik.split("/")[0].strip() if "/" in topik else topik or "Lainnya"

    if key not in data:
        data[key] = []

    existing_ids = {s["id"] for s in data[key]}
    added = 0

    for i, soal in enumerate(soal_list):
        soal_id = _soal_id(soal)
        if soal_id in existing_ids:
            continue
        data[key].append({
            "id":          soal_id,
            "tanggal":     today,
            "topik":       topik,
            "mapel":       mapel,
            "soal":        soal,
            "kunci":       kunci_list[i]     if i < len(kunci_list)     else "",
            "pembahasan":  pembahasan_list[i] if i < len(pembahasan_list) else "",
            "salah_count": 0,
            "benar_count": 0,
            "last_benar":  None,
        })
        added += 1

    _save(data)
    print(f"Bank soal: +{added} soal baru untuk {chat_id} (mapel: {mapel})")
    return added

# ── Ambil list mapel yang tersedia ───────────────────
def get_mapel_list(chat_id):
    data = _load()
    result = {}
    for s in data.get(str(chat_id), []):
        m = s.get("mapel", "Lainnya")
        result[m] = result.get(m, 0) + 1
    return result  # {"Matematika": 15, "IPA": 8, ...}

# ── Ambil soal random untuk /latihan ─────────────────
def get_random_soal(chat_id, mapel=None, count=10):
    data = _load()
    pool = data.get(str(chat_id), [])
    if mapel and mapel != "Semua":
        pool = [s for s in pool if s.get("mapel") == mapel]
    if not pool:
        return []
    return random.sample(pool, min(count, len(pool)))

# ── Ambil soal yang pernah salah untuk /ulang ────────
def get_salah_soal(chat_id, mapel=None):
    data = _load()
    pool = data.get(str(chat_id), [])
    salah = [s for s in pool if s.get("last_benar") == False]
    if mapel and mapel != "Semua":
        salah = [s for s in salah if s.get("mapel") == mapel]
    random.shuffle(salah)
    return salah

# ── Update hasil jawaban ──────────────────────────────
def update_result(chat_id, soal_id, benar):
    data = _load()
    for s in data.get(str(chat_id), []):
        if s["id"] == soal_id:
            if benar:
                s["benar_count"] += 1
            else:
                s["salah_count"] += 1
            s["last_benar"] = benar
            break
    _save(data)

# ── Statistik bank soal ───────────────────────────────
def get_stats(chat_id):
    data  = _load()
    pool  = data.get(str(chat_id), [])
    total = len(pool)
    salah = sum(1 for s in pool if s.get("last_benar") == False)
    belum = sum(1 for s in pool if s.get("last_benar") is None)
    return {"total": total, "salah": salah, "belum_dicoba": belum}
