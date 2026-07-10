import pytest

from app.processing.extract_entities import (
    extract_contract_addresses,
    extract_entities,
    extract_keywords,
    extract_position_signals,
    extract_tickers,
    extract_urls,
)


def test_extract_urls() -> None:
    assert extract_urls("Read https://example.com/a and https://example.com/a") == [
        "https://example.com/a"
    ]


def test_extract_tickers() -> None:
    assert extract_tickers("Watching $ETH and $BTC, not eth") == ["$BTC", "$ETH"]


def test_extract_keywords() -> None:
    assert extract_keywords("New airdrop points campaign after mainnet launch") == [
        "airdrop",
        "launch",
        "mainnet",
        "points",
    ]


def test_extract_entities() -> None:
    assert ("ticker", "$SOL") in extract_entities("$SOL listing https://example.com")


def test_extract_evm_contract_address() -> None:
    address = "0x1234567890abcdef1234567890ABCDEF12345678"

    assert extract_contract_addresses(f"CA: {address}") == [address.lower()]
    assert ("contract_address", address.lower()) in extract_entities(f"$ABC CA {address}")


def test_extract_solana_contract_address() -> None:
    address = "So11111111111111111111111111111111111111112"

    assert extract_contract_addresses(f"SOL token {address}") == [address]


def test_extract_contract_addresses_dedupes_and_skips_false_positive() -> None:
    evm = "0x1234567890abcdef1234567890abcdef12345678"
    long_base58_id = "So11111111111111111111111111111111111111112"
    content = f"{evm} again {evm} unrelated id {long_base58_id} short abc123 and ambiguous O0Il"

    assert extract_contract_addresses(content) == [evm]


@pytest.mark.parametrize("phrase", ["bullish on", "positive on", "strong on", "supporting"])
def test_extract_position_signal_for_positive_language(phrase: str) -> None:
    signals = extract_position_signals(f"Wallet is {phrase} $SOL after launch", "msg-1")

    assert len(signals) == 1
    assert signals[0].token == "$SOL"
    assert signals[0].direction == "buy"
    assert signals[0].source_message_id == "msg-1"
    assert signals[0].confidence >= 0.7
    assert "$SOL" in signals[0].evidence_text


@pytest.mark.parametrize("phrase", ["bearish on", "negative on", "weak on", "dumping"])
def test_extract_position_signal_for_negative_language(phrase: str) -> None:
    signals = extract_position_signals(f"Trader is {phrase} $ETH today", "msg-2")

    assert len(signals) == 1
    assert signals[0].token == "$ETH"
    assert signals[0].direction == "sell"
    assert signals[0].source_message_id == "msg-2"
    assert "$ETH" in signals[0].evidence_text


def test_extract_position_signal_allows_far_ticker_in_same_message() -> None:
    content = "Trader is bullish on the setup. Much later the thread mentioned " + ("x " * 90) + "$BTC"

    signals = extract_position_signals(content, "msg-3")

    assert len(signals) == 1
    assert signals[0].token == "$BTC"
    assert signals[0].direction == "buy"


def test_extract_position_signal_can_pair_sentiment_with_any_coin_mention() -> None:
    signals = extract_position_signals("Bullish on $SOL while also mentioning $ETH", "msg-8")

    assert {signal.token for signal in signals} == {"$SOL", "$ETH"}


def test_extract_position_signal_skips_ambiguous_or_sarcastic_messages() -> None:
    assert extract_position_signals("Maybe bullish on $SOL, sarcasm obviously", "msg-4") == []


def test_extract_position_signal_skips_mixed_sentiment() -> None:
    assert extract_position_signals("Bullish but also bearish on $SOL", "msg-5") == []


def test_extract_position_signal_allows_unrelated_not_phrase() -> None:
    signals = extract_position_signals("Wallet is bullish on $SOL, not financial advice", "msg-7")

    assert len(signals) == 1
    assert signals[0].token == "$SOL"
    assert signals[0].direction == "buy"
