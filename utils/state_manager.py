import json
import os

STATE_FILE = "session_states.json"

def load_all_states():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception:
            return {}
    return {}

def save_all_states(session_state):
    try:
        serializable = {}
        for chat_id, state in session_state.items():
            serializable[str(chat_id)] = {
                k: v for k, v in state.items()
                if isinstance(v, (str, int, float, bool, list, dict, type(None)))
            }
        with open(STATE_FILE, "w") as f:
            json.dump(serializable, f)
    except Exception as e:
        print(f"Error saving state: {e}")

def save_state(chat_id, state, session_state):
    session_state[chat_id] = state
    save_all_states(session_state)