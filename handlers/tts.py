import os
import json
import base64
import tempfile
from google.cloud import texttospeech
from google.oauth2 import service_account

def get_tts_client():
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_BASE64")
    if creds_b64:
        creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        credentials = service_account.Credentials.from_service_account_info(
            creds_json,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return texttospeech.TextToSpeechClient(credentials=credentials)
    return texttospeech.TextToSpeechClient()

def generate_podcast(rangkuman_text, child_name, level):
    client = get_tts_client()

    intro = f"Hei {child_name}! Ini rangkuman materi hari ini. Yuk dengerin baik-baik!"
    full_text = f"{intro}\n\n{rangkuman_text}"

    synthesis_input = texttospeech.SynthesisInput(text=full_text)

    voice_map = {
        "SMP":        ("id-ID-Standard-B", 1.0),
        "SD Kelas 4": ("id-ID-Standard-A", 0.95),
        "SD Kelas 1": ("id-ID-Standard-A", 0.85),
    }

    voice_name, speed = voice_map.get(level, ("id-ID-Standard-A", 1.0))

    voice = texttospeech.VoiceSelectionParams(
        language_code="id-ID",
        name=voice_name,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speed,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".mp3", prefix=f"podcast_{child_name}_"
    )
    tmp.write(response.audio_content)
    tmp.close()

    return tmp.name