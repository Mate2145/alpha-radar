"""Split a long Markdown digest into Telegram-compatible chunks."""

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def split_by_headings(markdown: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split *markdown* into chunks that fit within Telegram's message limit.

    Splitting is attempted at Markdown heading boundaries, then paragraph
    boundaries, then as a last resort at character boundaries so the result
    is always <= *max_length*.
    """
    if len(markdown) <= max_length:
        return [markdown]

    title, body = _extract_title(markdown)
    sections = _split_into_sections(body)
    chunks = _combine_sections(sections, max_length)

    result: list[str] = []
    for chunk in chunks:
        if not result and title:
            candidate = f"{title}\n\n{chunk}"
        else:
            candidate = chunk
        if len(candidate) > max_length:
            result.extend(_split_chunk(candidate, max_length))
        else:
            result.append(candidate)
    return result


def split_digest(markdown: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    return split_by_headings(markdown, max_length)


def _extract_title(markdown: str) -> tuple[str, str]:
    """Return (title, body) where title is the leading h1 if present."""
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        body = "\n".join(lines[1:]).strip("\n")
        return lines[0], body
    return "", markdown


def _split_into_sections(body: str) -> list[str]:
    """Split body on h2 headings (## ...) preserving each heading with its section."""
    lines = body.splitlines()
    sections: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current:
                sections.append("\n".join(current).strip("\n"))
                current = []
        current.append(line)
    if current:
        sections.append("\n".join(current).strip("\n"))
    return [section for section in sections if section]


def _combine_sections(sections: list[str], max_length: int) -> list[str]:
    """Group sections into chunks that stay under *max_length*."""
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for section in sections:
        section_length = len(section) + (2 if current else 0)  # separators
        if current and current_length + section_length > max_length:
            chunks.append("\n\n".join(current))
            current = [section]
            current_length = len(section)
        else:
            current.append(section)
            current_length += section_length
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_chunk(chunk: str, max_length: int) -> list[str]:
    """Fallback splitting for a chunk that is still too long."""
    paragraphs = [p.strip() for p in chunk.split("\n\n") if p.strip()]
    result: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in paragraphs:
        paragraph_length = len(paragraph) + (2 if current else 0)
        if current and current_length + paragraph_length > max_length:
            result.append("\n\n".join(current))
            current = [paragraph]
            current_length = len(paragraph)
        else:
            current.append(paragraph)
            current_length += paragraph_length
    if current:
        result.append("\n\n".join(current))

    final_result: list[str] = []
    for item in result:
        if len(item) > max_length:
            final_result.extend(_split_hard(item, max_length))
        else:
            final_result.append(item)
    return final_result


def _split_hard(text: str, max_length: int) -> list[str]:
    """Last-resort character-boundary split."""
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + max_length])
        start += max_length
    return chunks
