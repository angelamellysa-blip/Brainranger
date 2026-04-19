import base64
import os
import anthropic
from prompts.smp import SMP_PROMPT
from prompts.sd4 import SD4_PROMPT
from prompts.sd1 import SD1_PROMPT
from config import BRAINRANGER_AI_ANT_KEY

client = anthropic.Anthropic(api_key=BRAINRANGER_AI_ANT_KEY)

PROMPTS = {
    "SMP": SMP_PROMPT,
    "SD Kelas 4": SD4_PROMPT,
    "SD Kelas 1": SD1_PROMPT,
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

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=8096,
        system=get_system_prompt(ranger["level"]),
        messages=[{"role": "user", "content": content}]
    )

    # DEBUG: lihat raw response dari Claude
    raw = response.content[0].text
    print(f"DEBUG RAW RESPONSE:\n{raw[:500]}")


    return parse_response(response.content[0].text)

def evaluate_answer(soal, jawaban_anak, kunci_jawaban, level):
    prompt = f"""Kamu adalah guru {level} Indonesia yang sedang mengoreksi jawaban siswa.

Soal: {soal}
Kunci jawaban: {kunci_jawaban}
Jawaban siswa: {jawaban_anak}

Apakah jawaban siswa BENAR secara makna dan konsep?
Jawab hanya dengan satu kata: BENAR atau SALAH

Pertimbangkan:
- Jawaban dianggap BENAR jika maknanya sama meskipun berbeda kata
- Jawaban dianggap BENAR jika konsepnya tepat meskipun tidak persis sama dengan kunci
- Jawaban dianggap SALAH jika konsep atau faktanya keliru
"""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=10,
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.content[0].text.strip().upper()
    return "BENAR" in result

def parse_response(text):
    sections = {
        "rangkuman": "",
        "soal": [],
        "kunci": [],
        "pembahasan": [],
    }

    current = None

    for line in text.split("\n"):
        line = line.strip()
        if line == "===RANGKUMAN===":
            current = "rangkuman"
        elif line == "===SOAL===":
            current = "soal"
        elif line == "===KUNCI===":
            current = "kunci"
        elif line == "===PEMBAHASAN===":
            current = "pembahasan"
        elif current == "rangkuman":
            sections["rangkuman"] += line + "\n"
        elif current in ("soal", "kunci", "pembahasan"):
            if line and line[0].isdigit() and "." in line:
                parts = line.split(".", 1)
                if len(parts) > 1:
                    sections[current].append(parts[1].strip())
            elif line and sections[current]:
                sections[current][-1] += " " + line

    sections["rangkuman"] = sections["rangkuman"].strip()
    return sections