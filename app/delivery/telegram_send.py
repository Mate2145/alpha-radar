import logging

import httpx

from app.config import get_settings
from app.delivery.split_digest import split_digest

logger = logging.getLogger(__name__)


def send_telegram_message(markdown: str) -> None:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    logger.info(
        "Sending Telegram message to chat_id=%s (text length=%d)",
        settings.telegram_chat_id,
        len(markdown),
    )

    chunks = split_digest(markdown)
    if len(chunks) > 1:
        logger.info(
            "Split digest into %d chunks for delivery (max chunk length=%d)",
            len(chunks),
            max(len(chunk) for chunk in chunks),
        )

    for index, chunk in enumerate(chunks, start=1):
        _send_chunk(settings.telegram_bot_token, settings.telegram_chat_id, chunk, index, len(chunks))

    logger.info("Telegram message sent successfully (%d chunk(s))", len(chunks))


def _send_chunk(bot_token: str, chat_id: str, chunk: str, index: int, total: int) -> None:
    logger.info(
        "Sending chunk %d/%d to Telegram (length=%d)",
        index,
        total,
        len(chunk),
    )
    response = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        },
        timeout=30,
    )

    if response.status_code >= 400:
        detail = _extract_error_detail(response)
        logger.error(
            "Telegram API returned %s on chunk %d/%d: %s",
            response.status_code,
            index,
            total,
            detail,
        )
        raise RuntimeError(
            f"Telegram API error {response.status_code} on chunk {index}/{total}: {detail}"
        )


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return response.text or response.reason_phrase

    description = payload.get("description")
    if description:
        return description

    error = payload.get("error")
    if error:
        return str(error)

    return response.text or response.reason_phrase
