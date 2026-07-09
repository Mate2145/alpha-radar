from collections.abc import Callable

from app.delivery.discord_send import send_discord_message
from app.delivery.telegram_send import send_telegram_message

DeliverySender = Callable[[str], None]


class BroadcastDeliveryError(RuntimeError):
    def __init__(self, failures: dict[str, Exception]) -> None:
        self.failures = failures
        detail = ", ".join(f"{name}: {error}" for name, error in failures.items())
        super().__init__(f"Broadcast delivery failed for {detail}")


def send_broadcast_message(
    markdown: str,
    senders: dict[str, DeliverySender] | None = None,
) -> None:
    active_senders = senders if senders is not None else {
        "telegram": send_telegram_message,
        "discord": send_discord_message,
    }
    failures: dict[str, Exception] = {}

    for name, sender in active_senders.items():
        try:
            sender(markdown)
        except Exception as exc:  # noqa: BLE001
            failures[name] = exc

    if failures:
        raise BroadcastDeliveryError(failures)
