# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
pip install -r requirements.txt
python main.py
```

Deployment target is Railway.app (configured in `railway.json`). The start command is `python main.py`. No test suite exists.

## Required Environment Variables

Defined in `config.py` and loaded from `.env`:
- `TELEGRAM_BOT_TOKEN` — Telegram bot token
- `PARENT_CHAT_ID` — Superadmin's Telegram chat ID (bot owner; also seeds the first family's parent)
- `RANGER_BIRU_CHAT_ID`, `RANGER_KUNING_CHAT_ID`, `RANGER_PUTIH_CHAT_ID` — chat IDs used only to seed the first family into `families.json`
- `BRAINRANGER_AI_ANT_KEY` — Anthropic API key
- `GOOGLE_CREDENTIALS_BASE64` — base64-encoded Google Cloud service account JSON (for TTS and Sheets)
- `SPREADSHEET_ID` — Google Sheets spreadsheet ID for session logging (optional; logging skipped if not set)

## Architecture

BrainRanger is a Telegram bot for 3 Indonesian students ("Rangers") managed by a parent. Each day follows a 2-session Pomodoro workflow:

**Session 1 (Learn):** Student sends photos of textbook pages → `ai_processor.py` calls Claude with base64-encoded images → AI returns a structured response with `RANGKUMAN` (summary), `SOAL` (questions), `KUNCI` (answer keys), `PEMBAHASAN` (explanations) → `tts.py` converts the summary to an MP3 podcast via Google Cloud TTS → bot sends summary + audio.

**Session 2 (Test):** Bot sends the 10 questions one by one. Student types answers. `evaluate_answer()` in `ai_processor.py` calls Claude to semantically evaluate each answer (not exact-match). Points are tracked and the parent receives a status notification at the end.

### Key files

| File | Role |
|---|---|
| `main.py` | Bot entry point; registers all handlers and daily reminder scheduler |
| `config.py` | Env vars + re-exports family helpers from `utils/families.py` |
| `utils/families.py` | Multi-tenant family registry (`families.json`): `get_ranger()`, `is_parent()`, `is_superadmin()`, `get_parent_of()`, `add_family()`, `add_ranger()`. One chat_id may belong to only one family; parents may only access their own family's data |
| `handlers/pomodoro.py` | Full session state machine: `/mulai`, `/selesai`, `/lanjut`, `/skip`, photo collection, answer handling |
| `handlers/ai_processor.py` | Claude API calls for image processing and answer evaluation; parses Claude's structured output |
| `handlers/tts.py` | Google Cloud TTS podcast generation; voice varies by education level |
| `prompts/smp.py`, `sd4.py`, `sd1.py` | Education-level-specific system prompts for Claude; define the exact output format Claude must follow |
| `utils/state_manager.py` | Loads/saves `session_states.json` to persist per-chat session state across restarts |
| `utils/message_splitter.py` | Splits long AI responses into ≤4000-char chunks for Telegram |

### State flow

Session state per chat is stored as a dict in `session_states.json` and accessed via `state_manager.py`. Key state fields: `active`, `waiting_for_photos`, `photos`, `questions`, `answers`, `pembahasan`, `current_question_index`, `points`, `session_number`.

### Families & Ranger profiles

The bot is multi-tenant: families (one parent + their rangers) live in `families.json` (in `DATA_DIR`), managed by `utils/families.py`. The first family is auto-seeded from env vars on first run:
- Kirana — Ranger Biru, SMP (junior high), 25-min focus
- Kanaya — Ranger Kuning, SD Kelas 4, 20-min focus
- Kiandra — Ranger Putih, SD Kelas 1, 15-min focus

The superadmin (env `PARENT_CHAT_ID`) owns operational commands (`/restart`, `/testreminder`) and sees all families in `/squad`; regular parents only see their own family. Parent notifications (session done, skip, exam recap) go to `get_parent_of(chat_id)`.

All in-app text and AI prompts are in Indonesian.
