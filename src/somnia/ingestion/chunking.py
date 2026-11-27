"""Split text into overlapping chunks, preferring line boundaries."""


def chunk_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if max_chars <= overlap:
        raise ValueError("max_chars must exceed overlap")
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + overlap + 1, end)
            if newline != -1:
                end = newline
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]
