from app.processing.deduplicate import content_hash, normalize_content


def test_normalize_content() -> None:
    assert normalize_content("  Hello   WORLD ") == "hello world"


def test_content_hash_ignores_case_and_spacing() -> None:
    assert content_hash("Hello world") == content_hash(" hello   WORLD ")

