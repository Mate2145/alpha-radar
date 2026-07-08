from unittest.mock import MagicMock

import pytest
import httpx

from app.delivery.telegram_send import send_telegram_message


class FakeResponse:
    def __init__(self, status_code: int, json_payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_payload or {}
        self.text = text
        self.reason_phrase = "OK" if status_code < 400 else "Error"

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=MagicMock(),
                response=self,
            )


def test_send_telegram_message_success(monkeypatch, caplog):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    from app.config import get_settings

    get_settings.cache_clear()

    with caplog.at_level("INFO", logger="app.delivery.telegram_send"):
        send_telegram_message("hello world")

    assert len(calls) == 1
    assert "chat123" in calls[0][1]["json"]["chat_id"]
    assert "Sending Telegram message" in caplog.text
    assert "sent successfully" in caplog.text


def test_send_telegram_message_missing_config(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "")

    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"):
        send_telegram_message("hello")


def test_send_telegram_message_reports_api_error(monkeypatch, caplog):
    def fake_post(url, **kwargs):
        return FakeResponse(
            400,
            {
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: chat not found",
            },
            text='{"ok":false}',
        )

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    from app.config import get_settings

    get_settings.cache_clear()

    with caplog.at_level("ERROR", logger="app.delivery.telegram_send"):
        with pytest.raises(RuntimeError, match="Telegram API error 400") as exc_info:
            send_telegram_message("hello world")

    assert "Bad Request: chat not found" in str(exc_info.value)
    assert "Bad Request: chat not found" in caplog.text


def test_send_long_digest_in_multiple_chunks(monkeypatch, caplog):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")

    from app.config import get_settings

    get_settings.cache_clear()

    sections = "\n\n".join(f"## Section {i}\n\n" + "x" * 800 for i in range(8))
    long_digest = f"# Crypto Alpha Digest - 2026-07-08\n\n{sections}"

    with caplog.at_level("INFO", logger="app.delivery.telegram_send"):
        send_telegram_message(long_digest)

    assert len(calls) >= 2
    assert all(
        len(call[1]["json"]["text"]) <= 4096 for call in calls
    )
    assert "Split digest into" in caplog.text
