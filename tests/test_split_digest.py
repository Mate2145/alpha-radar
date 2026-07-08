from app.delivery.split_digest import split_by_headings, split_digest, TELEGRAM_MAX_MESSAGE_LENGTH


def _long_section_lines(prefix: str, count: int) -> str:
    return "\n".join(f"- {prefix} item {i}" for i in range(count))


def test_short_digest_unchanged() -> None:
    text = "# Title\n\n## Section\n\nSome content."
    assert split_digest(text) == [text]


def test_split_by_headings_alias_matches_story_api() -> None:
    text = "# Title\n\n## Section\n\nSome content."
    assert split_by_headings(text) == split_digest(text)


def test_split_by_headings_keeps_sections_under_limit() -> None:
    body = "\n\n".join(
        f"## Section {i}\n\n{_long_section_lines(f'section{i}', 50)}"
        for i in range(20)
    )
    text = f"# Crypto Alpha Digest - 2026-07-08\n\n{body}"

    chunks = split_digest(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH for chunk in chunks)


def test_split_preserves_title_only_on_first_chunk() -> None:
    body = "\n\n".join(
        f"## Section {i}\n\n{_long_section_lines(f'section{i}', 50)}"
        for i in range(20)
    )
    title = "# Crypto Alpha Digest - 2026-07-08"
    text = f"{title}\n\n{body}"

    chunks = split_digest(text)

    assert chunks[0].startswith(title)
    for chunk in chunks[1:]:
        assert not chunk.startswith("# Crypto Alpha Digest")


def test_split_single_long_section_at_paragraphs() -> None:
    paragraphs = [f"Paragraph {i}:\n" + "x" * 500 for i in range(20)]
    text = "# Title\n\n## Long Section\n\n" + "\n\n".join(paragraphs)

    chunks = split_digest(text)

    assert len(chunks) >= 3
    assert all(len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH for chunk in chunks)


def test_split_long_paragraph_hard_fallback() -> None:
    long_paragraph = "x" * TELEGRAM_MAX_MESSAGE_LENGTH * 3
    text = f"# Title\n\n## Section\n\n{long_paragraph}"

    chunks = split_digest(text)

    assert len(chunks) == 4  # title + 3 hard splits
    assert all(len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH for chunk in chunks)
