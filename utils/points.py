import json
import os
from datetime import date, timedelta

POINTS_FILE = "points_history.json"

_cache: dict | None = None  # in-memory cache, None = belum di-load

def _load():
    global _cache
    if _cache is not None:
        return _cache
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r") as f:
                _cache = json.load(f)
                return _cache
        except Exception:
            pass
    _cache = {}
    return _cache

def _save(data):
    global _cache
    _cache = data  # update cache sebelum tulis disk
    try:
        with open(POINTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Error saving points: {e}")

def add_points(chat_id, points):
    today = str(date.today())
    data = _load()
    key = str(chat_id)
    if key not in data:
        data[key] = {}
    if "daily" not in data[key]:
        data[key]["daily"] = {}
    data[key]["daily"][today] = data[key]["daily"].get(today, 0) + points
    _save(data)

def update_streak(chat_id):
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    data = _load()
    key = str(chat_id)
    if key not in data:
        data[key] = {}
    user = data[key]
    last_active = user.get("last_active", "")

    if last_active == today:
        return user.get("streak", 1), user.get("longest_streak", 1)

    current = user.get("streak", 0) + 1 if last_active == yesterday else 1
    longest = max(current, user.get("longest_streak", 0))
    user["last_active"] = today
    user["streak"] = current
    user["longest_streak"] = longest
    _save(data)
    return current, longest

def get_streak(chat_id):
    data = _load()
    user = data.get(str(chat_id), {})
    return user.get("streak", 0), user.get("longest_streak", 0)

def get_today_points(chat_id):
    today = str(date.today())
    data = _load()
    user = data.get(str(chat_id), {})
    daily = user.get("daily", user)  # backwards compat
    return daily.get(today, 0)

def get_total_points(chat_id):
    data = _load()
    user = data.get(str(chat_id), {})
    daily = user.get("daily", user)
    return sum(v for v in daily.values() if isinstance(v, (int, float)))

def get_rank(total_points):
    if total_points >= 1000: return ("👑", "Ranger Legendaris")
    if total_points >= 601:  return ("💎", "Ranger Elite")
    if total_points >= 301:  return ("🔥", "Ranger Tangguh")
    if total_points >= 101:  return ("⚡", "Ranger Aktif")
    return ("🌱", "Ranger Cadet")

def get_all_today():
    today = str(date.today())
    data = _load()
    result = {}
    for k, v in data.items():
        try:
            daily = v.get("daily", v) if isinstance(v, dict) else {}
            result[int(k)] = daily.get(today, 0)
        except Exception:
            pass
    return result
