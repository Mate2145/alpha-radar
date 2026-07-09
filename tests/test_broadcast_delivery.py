import pytest

from app.delivery.broadcast import BroadcastDeliveryError, send_broadcast_message


def test_send_broadcast_message_sends_to_all_destinations() -> None:
    calls: list[tuple[str, str]] = []

    send_broadcast_message(
        "# Digest",
        senders={
            "telegram": lambda markdown: calls.append(("telegram", markdown)),
            "discord": lambda markdown: calls.append(("discord", markdown)),
        },
    )

    assert calls == [
        ("telegram", "# Digest"),
        ("discord", "# Digest"),
    ]


def test_send_broadcast_message_reports_partial_failures() -> None:
    calls: list[str] = []

    def fail(markdown: str) -> None:
        calls.append(markdown)
        raise RuntimeError("webhook rejected")

    with pytest.raises(BroadcastDeliveryError, match="discord: webhook rejected") as exc_info:
        send_broadcast_message(
            "# Digest",
            senders={
                "telegram": lambda markdown: calls.append(markdown),
                "discord": fail,
            },
        )

    assert calls == ["# Digest", "# Digest"]
    assert list(exc_info.value.failures) == ["discord"]
