import hashlib


def normalize_content(content: str) -> str:
    return " ".join(content.casefold().split())


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_content(content).encode("utf-8")).hexdigest()

