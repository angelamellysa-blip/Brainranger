import re
import anthropic
import cairosvg
from config import BRAINRANGER_AI_ANT_KEY

client = anthropic.Anthropic(api_key=BRAINRANGER_AI_ANT_KEY)

# Keywords yang butuh ilustrasi
ILLUSTRATION_KEYWORDS = [
    # bangun datar
    "segitiga", "persegi panjang", "persegi", "lingkaran",
    "trapesium", "jajar genjang", "belah ketupat", "layang-layang",
    # bangun ruang
    "kubus", "balok", "tabung", "kerucut", "limas", "bola", "prisma",
    # grafik & statistik
    "grafik", "diagram batang", "diagram lingkaran", "histogram",
    "koordinat", "fungsi", "parabola", "garis lurus",
    # kata kunci soal bergambar
    "bangun", "perhatikan gambar", "sketsa", "ilustrasi",
]

SVG_SYSTEM_PROMPT = """Kamu adalah generator ilustrasi SVG untuk soal matematika sekolah Indonesia.

ATURAN OUTPUT:
- HANYA output kode SVG murni, TIDAK ada teks penjelasan apapun
- Mulai langsung dengan <svg dan akhiri dengan </svg>
- Ukuran wajib: width="300" height="250"
- Background: fill="#f8f9fa"
- Font: Arial atau sans-serif

ATURAN GAMBAR:
- Gaya teknis seperti di buku pelajaran, bersih dan jelas
- Warna cerah tapi tidak mencolok (pakai #AED6F1, #A9DFBF, #FAD7A0, dll)
- Label titik (A, B, C) dan ukuran wajib dicantumkan jika ada di soal
- Bangun ruang: gunakan proyeksi isometrik
- Garis tersembunyi: stroke-dasharray="4"
- Sumbu koordinat: sertakan label x dan y
- Semua teks menggunakan font-size minimal 11
"""

def needs_illustration(question: str) -> bool:
    q_lower = question.lower()
    return any(kw in q_lower for kw in ILLUSTRATION_KEYWORDS)

def generate_svg(question: str, level: str) -> str | None:
    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            system=SVG_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Buat ilustrasi SVG untuk soal berikut (level {level}):\n\n{question}"
            }]
        )
        raw = response.content[0].text.strip()

        # Ekstrak hanya bagian SVG
        match = re.search(r'<svg[\s\S]*?</svg>', raw, re.DOTALL)
        if match:
            return match.group(0)

        print(f"SVG tidak ditemukan dalam response: {raw[:200]}")
        return None

    except Exception as e:
        print(f"SVG generation error: {e}")
        return None

def svg_to_png(svg_content: str) -> bytes | None:
    try:
        png_bytes = cairosvg.svg2png(
            bytestring=svg_content.encode("utf-8"),
            output_width=600,
            output_height=500,
        )
        return png_bytes
    except Exception as e:
        print(f"SVG to PNG error: {e}")
        return None
