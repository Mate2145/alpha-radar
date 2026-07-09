import logging

import httpx

from app.config import get_settings
from app.delivery.split_digest import split_digest

DISCORD_MAX_CONTENT_LENGTH = 2000

logger = logging.getLogger(__name__)


def send_discord_message(markdown: str) -> None:
    settings = get_settings()
    if not settings.discord_webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL must be configured")

    logger.info("Sending Discord webhook message (text length=%d)", len(markdown))
    chunks = split_digest(markdown, max_length=DISCORD_MAX_CONTENT_LENGTH)
    if len(chunks) > 1:
        logger.info(
            "Split digest into %d chunks for Discord delivery (max chunk length=%d)",
            len(chunks),
            max(len(chunk) for chunk in chunks),
        )

    for index, chunk in enumerate(chunks, start=1):
        _send_chunk(settings.discord_webhook_url, chunk, index, len(chunks))

    logger.info("Discord message sent successfully (%d chunk(s))", len(chunks))


def _send_chunk(webhook_url: str, chunk: str, index: int, total: int) -> None:
    logger.info(
        "Sending chunk %d/%d to Discord (length=%d)",
        index,
        total,
        len(chunk),
    )
    response = httpx.post(
        webhook_url,
        json={"content": chunk},
        timeout=30,
    )

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        logger.error(
            "Discord webhook returned %s on chunk %d/%d: %s",
            response.status_code,
            index,
            total,
            detail,
        )
        raise RuntimeError(
            f"Discord webhook error {response.status_code} on chunk {index}/{total}: {detail}"
        )


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return response.text or response.reason_phrase

    message = payload.get("message")
    if message:
        return str(message)

    error = payload.get("error")
    if error:
        return str(error)

    return response.text or response.reason_phrase
