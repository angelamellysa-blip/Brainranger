import base64
import anthropic
import os
from prompts.smp import SMP_PROMPT
from prompts.sd4 import SD4_PROMPT
from prompts.sd1 import SD1_PROMPT

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

PROMPTS = {
    "SMP": SMP_PROMPT,
    "SD Kelas 4": SD4_PROMPT,
    "SD Kelas 1": SD1_PROMPT,
}

def get_system_prompt(level):
    return PROMPTS.get(level, SMP_PROMPT)

async def process_photos(photo_bytes_list, ranger):
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
        max_tokens=4096,
        system=get_system_prompt(ranger["level"]),
        messages=[{"role": "user", "content": content}]
    )

    return parse_response(response.content[0].text)

def parse_response(text):
    sections = {
        "rangkuman": "",
        "soal": [],
        "kunci": [],
        "pembahasan": [],
    }

    current = None
    buffer = []

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
                buffer = line.split(".", 1)
                if len(buffer) > 1:
                    sections[current].append(buffer[1].strip())
            elif line and sections[current]:
                sections[current][-1] += " " + line

    sections["rangkuman"] = sections["rangkuman"].strip()
    return sections