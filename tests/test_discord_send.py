from unittest.mock import MagicMock

import httpx
import pytest

from app.delivery.discord_send import DISCORD_MAX_CONTENT_LENGTH, send_discord_message


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


def test_send_discord_message_success(monkeypatch, caplog):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(204)

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/token")

    from app.config import get_settings

    get_settings.cache_clear()

    with caplog.at_level("INFO", logger="app.delivery.discord_send"):
        send_discord_message("hello world")

    assert calls == [
        (
            "https://discord.com/api/webhooks/123/token",
            {"json": {"content": "hello world"}, "timeout": 30},
        )
    ]
    assert "Discord message sent successfully" in caplog.text


def test_send_discord_message_missing_config(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "")

    from app.config import get_settings

    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL must be configured"):
        send_discord_message("hello")


def test_send_discord_message_reports_webhook_error(monkeypatch, caplog):
    def fake_post(url, **kwargs):
        return FakeResponse(400, {"message": "Cannot send an empty message"}, text="bad request")

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/token")

    from app.config import get_settings

    get_settings.cache_clear()

    with caplog.at_level("ERROR", logger="app.delivery.discord_send"):
        with pytest.raises(RuntimeError, match="Discord webhook error 400") as exc_info:
            send_discord_message("hello world")

    assert "Cannot send an empty message" in str(exc_info.value)
    assert "Cannot send an empty message" in caplog.text


def test_send_long_discord_message_in_multiple_chunks(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(204)

    monkeypatch.setattr("httpx.post", fake_post)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/123/token")

    from app.config import get_settings

    get_settings.cache_clear()

    sections = "\n\n".join(f"## Section {i}\n\n" + "x" * 700 for i in range(8))
    send_discord_message(f"# Crypto Alpha Digest\n\n{sections}")

    assert len(calls) >= 2
    assert all(
        len(call[1]["json"]["content"]) <= DISCORD_MAX_CONTENT_LENGTH for call in calls
    )
