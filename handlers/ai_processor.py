import base64
import os
import anthropic
from prompts.smp import SMP_PROMPT
from prompts.sd4 import SD4_PROMPT
from prompts.sd1 import SD1_PROMPT
from config import BRAINRANGER_AI_ANT_KEY
from utils.usage import add_tokens

client = anthropic.Anthropic(api_key=BRAINRANGER_AI_ANT_KEY)

PROMPTS = {
    "SMP": SMP_PROMPT,
    "SD Kelas 4": SD4_PROMPT,
    "SD Kelas 1": SD1_PROMPT,
}

# Max tokens per level — cukup untuk semua soal tanpa terpotong
MAX_TOKENS = {
    "SMP": 6000,
    "SD Kelas 4": 5000,
    "SD Kelas 1": 4000,
}

def get_system_prompt(level):
    return PROMPTS.get(level, SMP_PROMPT)

def process_photos(photo_bytes_list, ranger):
    content = []

    for photo_bytes in photo_bytes_list:
        image_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": image_b64,
            }
        })

    content.append({
        "type": "text",
        "text": (
            f"Ada {len(photo_bytes_list)} halaman buku di atas. "
            f"Proses semua halaman sebagai satu materi berkesinambungan."
        )
    })

    max_tokens = MAX_TOKENS.get(ranger["level"], 6000)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=get_system_prompt(ranger["level"]),
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text
    add_tokens(ranger.get("family_id"), "sonnet",
               response.usage.input_tokens, response.usage.output_tokens)
    print(f"process_photos tokens used: {response.usage.output_tokens}/{max_tokens}")
    return parse_response(raw)

def process_text_content(text: str, ranger: dict) -> dict:
    """
    Proses materi dari teks (PDF/DOCX) — alternatif process_photos().
    Input  : plain text hasil ekstrak dokumen
    Output : dict sama persis dengan process_photos()
    """
    max_tokens = MAX_TOKENS.get(ranger["level"], 6000)

    content = [
        {
            "type": "text",
            "text": (
                f"Berikut adalah materi pelajaran dalam bentuk teks "
                f"yang diekstrak dari dokumen (PDF/DOCX):\n\n"
                f"{text}\n\n"
                f"Proses materi di atas sesuai instruksi."
            )
        }
    ]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=get_system_prompt(ranger["level"]),
        messages=[{"role": "user", "content": content}]
    )

    raw = response.content[0].text
    add_tokens(ranger.get("family_id"), "sonnet",
               response.usage.input_tokens, response.usage.output_tokens)
    print(f"process_text_content tokens used: {response.usage.output_tokens}/{max_tokens}")
    return parse_response(raw)


def evaluate_answer(soal, jawaban_anak, kunci_jawaban, level, family_id=None):
    """
    Returns: (verdict, catatan)
    verdict : "BENAR" | "SEBAGIAN" | "SALAH"
    catatan : string penjelasan singkat (hanya untuk SEBAGIAN)
    """
    prompt = f"""Nilai jawaban siswa {level}.
Soal: {soal}
Kunci: {kunci_jawaban}
Jawaban: {jawaban_anak}

BENAR = makna/konsep sama meski kata beda, format beda tapi benar, inti tepat
SEBAGIAN = konsep utama benar tapi kurang lengkap atau ada bagian salah
SALAH = konsep keliru atau tidak nyambung

Balas HANYA salah satu:
BENAR
SEBAGIAN | [max 8 kata yang kurang]
SALAH"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=30,
        messages=[{"role": "user", "content": prompt}]
    )

    add_tokens(family_id, "haiku",
               response.usage.input_tokens, response.usage.output_tokens)
    raw = response.content[0].text.strip().upper()

    if raw.startswith("BENAR"):
        return ("BENAR", "")
    elif raw.startswith("SEBAGIAN"):
        parts = raw.split("|", 1)
        catatan = parts[1].strip().capitalize() if len(parts) > 1 else ""
        return ("SEBAGIAN", catatan)
    else:
        return ("SALAH", "")

def parse_response(text):
    sections = {
        "topik": "",
        "rangkuman": "",
        "soal": [],
        "kunci": [],
        "pembahasan": [],
    }

    current = None

    for line in text.split("\n"):
        line = line.strip()
        if line == "===TOPIK===":
            current = "topik"
        elif line == "===RANGKUMAN===":
            current = "rangkuman"
        elif line == "===SOAL===":
            current = "soal"
        elif line == "===KUNCI===":
            current = "kunci"
        elif line == "===PEMBAHASAN===":
            current = "pembahasan"
        elif current == "topik":
            if line and not line.startswith("Identifikasi") and not line.startswith("Format") and not line.startswith("Contoh") and "|" not in line:
                sections["topik"] = line
        elif current == "rangkuman":
            sections["rangkuman"] += line + "\n"
        elif current in ("soal", "kunci", "pembahasan"):
            if line and line[0].isdigit() and "." in line:
                parts = line.split(".", 1)
                if len(parts) > 1:
                    sections[current].append(parts[1].strip())
            elif line and sections[current]:
                sections[current][-1] += "\n" + line

    sections["rangkuman"] = sections["rangkuman"].strip()
    sections["topik"] = sections["topik"].strip()
    return sections
