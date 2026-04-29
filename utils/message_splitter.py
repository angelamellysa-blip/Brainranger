import re

def to_html(text):
    """Konversi **bold** ke <b>bold</b> untuk Telegram HTML mode."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return text

def strip_markdown(text):
    """Hapus semua marker markdown untuk TTS."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*(.+?)\*', r'\1', text)        # *italic*
    text = re.sub(r'\_(.+?)\_', r'\1', text)        # _italic_
    text = re.sub(r'\`(.+?)\`', r'\1', text)        # `code`
    text = re.sub(r'#{1,6}\s', '', text)             # # heading
    return text

def split_message(text, max_length=4000):
    if len(text) <= max_length:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            chunks.append(current_chunk.strip())
            current_chunk = line
        else:
            current_chunk += ("\n" if current_chunk else "") + line

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks