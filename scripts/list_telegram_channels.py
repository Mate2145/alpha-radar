import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in .env")

    async with TelegramClient(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        print("Readable Telegram channels/groups:")
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            is_channel = getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False)
            if not is_channel:
                continue

            username = getattr(entity, "username", None)
            channel_id = getattr(entity, "id", None)
            identifier = f"@{username}" if username else f"-100{channel_id}"
            print(f"{dialog.name} | {identifier} | id=-100{channel_id}")


if __name__ == "__main__":
    asyncio.run(main())
