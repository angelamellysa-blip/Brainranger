"""
doc_extractor.py — Extract teks dari PDF dan DOCX untuk BrainRanger.

Digunakan sebagai alternatif input selain foto buku.
PDF scanned (tidak ada teks) akan dideteksi dan dikembalikan sebagai string kosong.
"""

import io

MAX_PAGES = 10      # Maksimal halaman PDF yang diproses
MAX_WORDS = 6000    # Maksimal kata (potong kalau lebih)

# ── PDF ──────────────────────────────────────────────────
def extract_pdf(file_bytes: bytes) -> str:
    """
    Ekstrak teks dari PDF.
    Return string teks, atau "" jika PDF scanned/tidak ada teks.
    """
    try:
        import fitz  # pymupdf
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            pages_to_read = min(len(doc), MAX_PAGES)
            texts = []
            for i in range(pages_to_read):
                text = doc[i].get_text("text").strip()
                if text:
                    texts.append(f"[Halaman {i + 1}]\n{text}")
        return "\n\n".join(texts)
    except Exception as e:
        print(f"extract_pdf error: {e}")
        return ""


def is_scanned_pdf(text: str) -> bool:
    """
    Return True jika PDF tidak punya teks yang cukup (kemungkinan scanned).
    Threshold: < 100 karakter non-whitespace.
    """
    return len(text.replace(" ", "").replace("\n", "")) < 100


# ── DOCX ─────────────────────────────────────────────────
def extract_docx(file_bytes: bytes) -> str:
    """
    Ekstrak teks dari DOCX: paragraf biasa + tabel.
    Gunakan python-docx public API — lebih stabil dari raw XML traversal.
    """
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Paragraf
        for p in doc.paragraphs:
            if p.text.strip():
                parts.append(p.text.strip())

        # Tabel
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        return "\n".join(parts)
    except Exception as e:
        print(f"extract_docx error: {e}")
        return ""


# ── Truncate ─────────────────────────────────────────────
def truncate_content(text: str, max_words: int = MAX_WORDS) -> tuple[str, bool]:
    """
    Potong teks jika melebihi max_words.
    Return: (teks_hasil, was_truncated)
    """
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]), True


# ── Main entry point ──────────────────────────────────────
def extract_document(file_bytes: bytes, mime_type: str) -> dict:
    """
    Entry point utama. Deteksi tipe file, ekstrak teks, truncate jika perlu.

    Return dict:
    {
        "text": str,          # teks hasil ekstrak (sudah di-truncate jika perlu)
        "word_count": int,    # jumlah kata SEBELUM truncate
        "success": bool,      # True jika ada teks
        "scanned": bool,      # True jika PDF scanned (tidak ada teks)
        "truncated": bool,    # True jika dipotong karena terlalu panjang
        "error": str | None,  # pesan error jika ada
    }
    """
    text = ""
    scanned = False
    error = None

    try:
        if mime_type == "application/pdf":
            text = extract_pdf(file_bytes)
            if is_scanned_pdf(text):
                scanned = True
                text = ""
        elif mime_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ):
            text = extract_docx(file_bytes)
        else:
            error = f"Tipe file tidak didukung: {mime_type}"
    except Exception as e:
        error = str(e)
        print(f"extract_document error: {e}")

    text = text.strip()
    word_count = len(text.split()) if text else 0
    text, truncated = truncate_content(text) if text else ("", False)

    return {
        "text":       text,
        "word_count": word_count,
        "success":    bool(text),
        "scanned":    scanned,
        "truncated":  truncated,
        "error":      error,
    }
