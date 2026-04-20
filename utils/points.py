import json
import os
from datetime import date

POINTS_FILE = "points_history.json"

def _load():
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save(data):
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
    data[key][today] = data[key].get(today, 0) + points
    _save(data)

def get_today_points(chat_id):
    today = str(date.today())
    data = _load()
    return data.get(str(chat_id), {}).get(today, 0)

def get_total_points(chat_id):
    data = _load()
    return sum(data.get(str(chat_id), {}).values())

def get_all_today():
    today = str(date.today())
    data = _load()
    return {int(k): v.get(today, 0) for k, v in data.items()}
