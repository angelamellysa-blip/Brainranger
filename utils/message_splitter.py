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