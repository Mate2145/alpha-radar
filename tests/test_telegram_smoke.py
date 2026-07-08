from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.ingest import telegram_ingest
from app.ingest.telegram_ingest import (
    TelegramSmokeMessage,
    build_message_url,
    evaluate_telegram_signal_smoke,
    run_telegram_signal_smoke_test,
)


def test_evaluate_telegram_signal_smoke_finds_cashchat_robinhood_signal() -> None:
    messages = [
        TelegramSmokeMessage(
            channel="@alpha_one",
            content="Robinhood is pushing $cashchat today",
            created_at=datetime(2026, 7, 8, tzinfo=timezone.utc),
            url="https://t.me/alpha_one/10",
        ),
        TelegramSmokeMessage(
            channel="@alpha_two",
            content="Unrelated $SOL note",
            created_at=datetime(2026, 7, 8, tzinfo=timezone.utc),
        ),
    ]

    result = evaluate_telegram_signal_smoke(messages, "$cashchat", inspected_channels=2)

    assert result.found is True
    assert result.inspected_channels == 2
    assert result.inspected_messages == 2
    assert len(result.matches) == 1
    assert result.matches[0].channel == "@alpha_one"


def test_evaluate_telegram_signal_smoke_reports_no_match_with_counts() -> None:
    messages = [
        TelegramSmokeMessage(
            channel="@alpha_one",
            content="Robinhood note without the expected ticker",
            created_at=datetime(2026, 7, 8, tzinfo=timezone.utc),
        )
    ]

    result = evaluate_telegram_signal_smoke(messages, "$cashchat", inspected_channels=2)

    assert result.found is False
    assert result.inspected_channels == 2
    assert result.inspected_messages == 1
    assert result.matches == []


def test_run_telegram_signal_smoke_test_requires_two_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=["@only_one"],
            telegram_api_id=123,
            telegram_api_hash="hash",
        ),
    )

    with pytest.raises(RuntimeError, match="exactly two channels"):
        run_telegram_signal_smoke_test()


def test_run_telegram_signal_smoke_test_requires_telegram_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=["@one", "@two"],
            telegram_api_id=None,
            telegram_api_hash=None,
        ),
    )

    with pytest.raises(RuntimeError, match="TELEGRAM_API_ID and TELEGRAM_API_HASH"):
        run_telegram_signal_smoke_test()


def test_build_message_url_handles_public_and_private_channels() -> None:
    assert build_message_url("@public_channel", 42) == "https://t.me/public_channel/42"
    assert build_message_url("-100123", 42) is None

