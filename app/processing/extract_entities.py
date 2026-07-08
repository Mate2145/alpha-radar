import re
from dataclasses import dataclass

POSITION_POSITIVE_SENTIMENT_CUES = {
    "accumulate",
    "accumulating",
    "bought",
    "buy",
    "buying",
    "bullish",
    "bullish on",
    "great",
    "good",
    "hold",
    "holding",
    "long",
    "longing",
    "moon",
    "positive",
    "pump",
    "rally",
    "strong",
    "support",
    "supporting",
    "upside",
}
POSITION_NEGATIVE_SENTIMENT_CUES = {
    "bad",
    "bearish",
    "bearish on",
    "crash",
    "down",
    "downside",
    "dump",
    "dumping",
    "fade",
    "fading",
    "negative",
    "rejection",
    "rejected",
    "resistance",
    "sell",
    "selling",
    "short",
    "shorting",
    "weak",
    "weakness",
}
AMBIGUOUS_POSITION_MARKERS = {
    "allegedly",
    "apparently",
    "fake",
    "joking",
    "maybe",
    "rumor",
    "rumour",
    "sarcasm",
    "sarcastic",
    "unconfirmed",
}

CRYPTO_KEYWORDS = {
    "airdrop",
    "points",
    "launch",
    "exploit",
    "hack",
    "listing",
    "mainnet",
    "testnet",
    "funding",
    "partnership",
}

URL_RE = re.compile(r"https?://[^\s<>)\"']+")
TICKER_RE = re.compile(r"(?<!\w)\$([A-Z][A-Z0-9]{1,9})(?!\w)")


def extract_urls(content: str) -> list[str]:
    return sorted(set(URL_RE.findall(content)))


def extract_tickers(content: str) -> list[str]:
    return sorted({f"${match}" for match in TICKER_RE.findall(content)})


def extract_keywords(content: str) -> list[str]:
    lowered = content.casefold()
    return sorted(
        {keyword for keyword in CRYPTO_KEYWORDS if re.search(rf"\b{keyword}\b", lowered)}
    )


def extract_entities(content: str) -> list[tuple[str, str]]:
    entities: list[tuple[str, str]] = []
    entities.extend(("url", url) for url in extract_urls(content))
    entities.extend(("ticker", ticker) for ticker in extract_tickers(content))
    entities.extend(("keyword", keyword) for keyword in extract_keywords(content))
    return entities


@dataclass(frozen=True)
class PositionSignal:
    token: str
    direction: str
    source_message_id: str
    confidence: float
    evidence_text: str


def extract_position_signals(
    content: str,
    source_message_id: str,
) -> list[PositionSignal]:
    signals: list[PositionSignal] = []
    direction = classify_sentiment_direction(content)
    if direction is None:
        return signals

    ticker_matches = list(TICKER_RE.finditer(content))
    if not ticker_matches:
        return signals

    evidence = sentiment_evidence(content)
    if is_ambiguous_position_evidence(evidence):
        return signals

    for ticker_match in ticker_matches:
        signals.append(
            PositionSignal(
                token=f"${ticker_match.group(1)}",
                direction=direction,
                source_message_id=source_message_id,
                confidence=0.75,
                evidence_text=evidence,
            )
        )
    return dedupe_position_signals(signals)


def classify_sentiment_direction(content: str) -> str | None:
    lowered = content.casefold()
    positive = has_sentiment_cue(lowered, POSITION_POSITIVE_SENTIMENT_CUES)
    negative = has_sentiment_cue(lowered, POSITION_NEGATIVE_SENTIMENT_CUES)
    if positive and negative:
        return None
    if positive:
        return "buy"
    if negative:
        return "sell"
    return None


def has_sentiment_cue(lowered_content: str, cues: set[str]) -> bool:
    return any(
        re.search(rf"\b{re.escape(cue)}\b", lowered_content)
        for cue in cues
    )


def is_ambiguous_position_evidence(evidence: str) -> bool:
    lowered = evidence.casefold()
    return any(
        re.search(rf"\b{re.escape(marker)}\b", lowered)
        for marker in AMBIGUOUS_POSITION_MARKERS
    )


def sentiment_evidence(content: str) -> str:
    return " ".join(content.split())[:220]


def dedupe_position_signals(signals: list[PositionSignal]) -> list[PositionSignal]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[PositionSignal] = []
    for signal in signals:
        key = (signal.token, signal.direction, signal.source_message_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique
