"""
families.py — Registry multi-tenant keluarga untuk BrainRanger.

Semua keluarga (parent + rangers) disimpan di families.json (DATA_DIR).
Keluarga pertama (fam_001) di-seed otomatis dari env vars lama,
sehingga backward compatible dengan deployment single-family.

SECURITY INVARIANTS — wajib dijaga oleh semua kode yang memakai modul ini:
1. Satu chat_id hanya boleh terdaftar di SATU keluarga, sebagai parent ATAU ranger
   (divalidasi di add_family/add_ranger).
2. Parent hanya boleh melihat data ranger di keluarganya sendiri —
   selalu akses via get_family_rangers(parent_chat_id), jangan get_all_rangers().
3. Superadmin (= PARENT_CHAT_ID dari env) adalah satu-satunya yang boleh
   melihat lintas keluarga dan memakai command operasional (/restart, dll).
4. File ditulis secara atomik (tmp + os.replace) supaya tidak corrupt
   kalau proses mati di tengah penulisan.
"""

import json
import os
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.environ.get("DATA_DIR") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILIES_FILE = os.path.join(_BASE_DIR, "families.json")

# Superadmin = pemilik bot (Angela). Tetap dari env, bukan dari families.json,
# supaya tidak bisa diubah lewat data file.
SUPERADMIN_CHAT_ID = int(os.getenv("PARENT_CHAT_ID", "0"))

_cache = None

# ── Seed dari env vars (keluarga pertama) ─────────────────
def _seed_from_env() -> dict:
    parent_id = SUPERADMIN_CHAT_ID
    seed_rangers = {}

    env_rangers = [
        ("RANGER_BIRU_CHAT_ID", {
            "name": "Kirana", "ranger": "Ranger Biru", "emoji": "🔵",
            "level": "SMP", "focus_minutes": 25, "break_minutes": 5, "sessions": 2,
        }),
        ("RANGER_KUNING_CHAT_ID", {
            "name": "Kanaya", "ranger": "Ranger Kuning", "emoji": "🟡",
            "level": "SD Kelas 4", "focus_minutes": 20, "break_minutes": 5, "sessions": 2,
        }),
        ("RANGER_PUTIH_CHAT_ID", {
            "name": "Kiandra", "ranger": "Ranger Putih", "emoji": "⚪",
            "level": "SD Kelas 1", "focus_minutes": 15, "break_minutes": 5, "sessions": 2,
        }),
    ]
    for env_key, profile in env_rangers:
        cid = int(os.getenv(env_key, "0"))
        if cid:
            seed_rangers[str(cid)] = profile

    if not parent_id and not seed_rangers:
        return {"families": {}}

    return {
        "families": {
            "fam_001": {
                "parent_chat_id": parent_id,
                "parent_name": os.getenv("PARENT_NAME", "Angela"),
                "plan": "owner",
                "rangers": seed_rangers,
            }
        }
    }

# ── Load / save ───────────────────────────────────────────
def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache

    if os.path.exists(FAMILIES_FILE):
        try:
            with open(FAMILIES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("families"), dict):
                _cache = data
                return _cache
            raise ValueError("struktur families.json tidak valid")
        except Exception as e:
            # Jangan timpa file rusak — simpan untuk forensik, lalu re-seed
            # supaya minimal keluarga pemilik tetap jalan.
            print(f"families.json corrupt ({e}), backup ke .corrupt dan re-seed dari env")
            try:
                os.replace(FAMILIES_FILE, FAMILIES_FILE + ".corrupt")
            except Exception:
                pass

    _cache = _seed_from_env()
    _save()
    return _cache

def _save():
    try:
        tmp = FAMILIES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, FAMILIES_FILE)
    except Exception as e:
        print(f"Error saving families.json: {e}")

def reload_families():
    """Paksa baca ulang dari disk (dipakai setelah edit manual file)."""
    global _cache
    _cache = None
    _load()

# ── Lookup internal ───────────────────────────────────────
def _find_chat_id(chat_id: int):
    """Return (role, family_id) untuk chat_id, atau None jika tidak terdaftar."""
    for fam_id, fam in _load()["families"].items():
        if fam.get("parent_chat_id") == chat_id:
            return ("parent", fam_id)
        if str(chat_id) in fam.get("rangers", {}):
            return ("ranger", fam_id)
    return None

# ── Public API: identitas & otorisasi ─────────────────────
def get_ranger(chat_id):
    """Profil ranger untuk chat_id, atau None. Profil mencakup chat_id & family_id."""
    for fam_id, fam in _load()["families"].items():
        profile = fam.get("rangers", {}).get(str(chat_id))
        if profile:
            result = dict(profile)
            result["chat_id"]   = int(chat_id)
            result["family_id"] = fam_id
            return result
    return None

def is_ranger(chat_id) -> bool:
    found = _find_chat_id(chat_id)
    return bool(found and found[0] == "ranger")

def is_parent(chat_id) -> bool:
    """True jika chat_id adalah parent dari SALAH SATU keluarga."""
    found = _find_chat_id(chat_id)
    return bool(found and found[0] == "parent")

def is_superadmin(chat_id) -> bool:
    return bool(SUPERADMIN_CHAT_ID) and chat_id == SUPERADMIN_CHAT_ID

def get_parent_of(ranger_chat_id):
    """Chat ID parent dari keluarga si ranger, atau None."""
    for fam in _load()["families"].values():
        if str(ranger_chat_id) in fam.get("rangers", {}):
            return fam.get("parent_chat_id") or None
    return None

def get_plan_of(chat_id) -> str:
    """Plan keluarga si chat_id (parent atau ranger). Default paling ketat: trial."""
    found = _find_chat_id(chat_id)
    if not found:
        return "trial"
    return _load()["families"][found[1]].get("plan", "trial")

def get_parent_name(parent_chat_id) -> str:
    for fam in _load()["families"].values():
        if fam.get("parent_chat_id") == parent_chat_id:
            return fam.get("parent_name", "")
    return ""

# ── Public API: data per keluarga ─────────────────────────
def get_family_rangers(parent_chat_id) -> dict:
    """
    Rangers milik keluarga si parent SAJA: {chat_id(int): profile}.
    Ini satu-satunya cara parent boleh mengakses data ranger.
    """
    for fam in _load()["families"].values():
        if fam.get("parent_chat_id") == parent_chat_id:
            return {int(cid): dict(p) for cid, p in fam.get("rangers", {}).items()}
    return {}

def get_all_families() -> dict:
    """
    Semua keluarga (untuk scheduler & superadmin):
    {family_id: {"parent_chat_id", "parent_name", "rangers": {chat_id(int): profile}}}
    """
    result = {}
    for fam_id, fam in _load()["families"].items():
        result[fam_id] = {
            "parent_chat_id": fam.get("parent_chat_id", 0),
            "parent_name":    fam.get("parent_name", ""),
            "plan":           fam.get("plan", "trial"),
            "rangers":        {int(cid): dict(p) for cid, p in fam.get("rangers", {}).items()},
        }
    return result

def get_all_rangers() -> dict:
    """Semua ranger lintas keluarga (HANYA untuk scheduler/superadmin)."""
    result = {}
    for fam in _load()["families"].values():
        for cid, p in fam.get("rangers", {}).items():
            result[int(cid)] = dict(p)
    return result

# ── Public API: mutasi (dipakai onboarding Phase 2) ───────
def add_family(parent_chat_id: int, parent_name: str, plan: str = "trial") -> str:
    """Daftarkan keluarga baru. Raise ValueError jika chat_id sudah terdaftar."""
    parent_chat_id = int(parent_chat_id)
    if _find_chat_id(parent_chat_id):
        raise ValueError(f"chat_id {parent_chat_id} sudah terdaftar")

    data = _load()
    nums = [int(fid.split("_")[1]) for fid in data["families"] if fid.startswith("fam_")]
    fam_id = f"fam_{(max(nums) + 1) if nums else 1:03d}"
    data["families"][fam_id] = {
        "parent_chat_id": parent_chat_id,
        "parent_name":    str(parent_name)[:50],
        "plan":           plan,
        "rangers":        {},
    }
    _save()
    return fam_id

def add_ranger(family_id: str, chat_id: int, profile: dict):
    """Tambah ranger ke keluarga. Raise ValueError jika chat_id sudah terdaftar."""
    chat_id = int(chat_id)
    if _find_chat_id(chat_id):
        raise ValueError(f"chat_id {chat_id} sudah terdaftar")

    data = _load()
    fam = data["families"].get(family_id)
    if not fam:
        raise ValueError(f"keluarga {family_id} tidak ditemukan")

    allowed = {"name", "ranger", "emoji", "level", "focus_minutes", "break_minutes", "sessions"}
    fam.setdefault("rangers", {})[str(chat_id)] = {
        k: v for k, v in profile.items() if k in allowed
    }
    _save()
