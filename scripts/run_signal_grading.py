#!/usr/bin/env python3
import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.migrations import init_db
from app.db.models import ExtractedEntity, Message
from app.processing.signal_grading import (
    GradingValidationError,
    build_grading_input,
    run_signal_grading,
    validate_grading_input,
    write_json,
    window_filename,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the file-based signal grading pipeline.")
    window = parser.add_mutually_exclusive_group(required=True)
    window.add_argument("--since-hours", type=int, help="Grade signals from the last N hours.")
    window.add_argument("--from-to", nargs=2, metavar=("FROM", "TO"), help="ISO datetime window.")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write and validate grading input only; do not invoke the grading runner.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("data") / "signal-grading",
        help="Base directory for input/output/invalid/logs.",
    )
    return parser.parse_args()


def parse_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.since_hours is not None:
        if args.since_hours <= 0:
            raise ValueError("--since-hours must be greater than zero")
        window_end = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
        return window_end - timedelta(hours=args.since_hours), window_end

    window_start = datetime.fromisoformat(args.from_to[0])
    window_end = datetime.fromisoformat(args.from_to[1])
    if window_start >= window_end:
        raise ValueError("--from-to FROM must be before TO")
    return window_start, window_end


def configure_logging(base_dir: Path, window_start: datetime, window_end: datetime) -> Path:
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / window_filename(window_start, window_end).replace(".json", ".log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_path


def count_window_messages(session, window_start: datetime, window_end: datetime) -> tuple[int, int]:
    message_count = session.scalar(
        select(func.count(Message.id)).where(
            Message.created_at >= window_start,
            Message.created_at < window_end,
        )
    )
    entity_count = session.scalar(
        select(func.count(ExtractedEntity.id))
        .join(Message, ExtractedEntity.message_id == Message.id)
        .where(
            Message.created_at >= window_start,
            Message.created_at < window_end,
        )
    )
    return int(message_count or 0), int(entity_count or 0)


def database_message_stats(session) -> dict[str, object]:
    total_messages = session.scalar(select(func.count(Message.id)))
    total_entities = session.scalar(select(func.count(ExtractedEntity.id)))
    earliest_message = session.scalar(select(func.min(Message.created_at)))
    latest_message = session.scalar(select(func.max(Message.created_at)))
    return {
        "total_messages": int(total_messages or 0),
        "total_entities": int(total_entities or 0),
        "earliest_message": earliest_message,
        "latest_message": latest_message,
    }


def write_prepare_only_input(session, window_start: datetime, window_end: datetime, base_dir: Path) -> Path:
    settings = get_settings()
    payload = build_grading_input(
        session,
        window_start,
        window_end,
        pairing_max_distance=settings.signal_pairing_max_distance,
    )
    validate_grading_input(payload)

    input_dir = base_dir / "input"
    input_path = input_dir / window_filename(window_start, window_end)
    latest_path = input_dir / "latest.json"
    write_json(input_path, payload)
    write_json(latest_path, payload)
    return input_path


def main() -> int:
    try:
        args = parse_args()
        window_start, window_end = parse_window(args)
    except ValueError as exc:
        print(f"Invalid arguments: {exc}", file=sys.stderr)
        return 2

    log_path = configure_logging(args.base_dir, window_start, window_end)
    logger = logging.getLogger("signal-grading-script")
    settings = get_settings()

    logger.info("Signal grading script started")
    logger.info("Window start: %s", window_start.isoformat())
    logger.info("Window end: %s", window_end.isoformat())
    logger.info("Database URL: %s", settings.database_url)
    logger.info("Base dir: %s", args.base_dir)
    logger.info("Prepare only: %s", args.prepare_only)
    logger.info("Pairing max distance: %d", settings.signal_pairing_max_distance)

    try:
        init_db()
        with SessionLocal() as session:
            stats = database_message_stats(session)
            logger.info("Database total message count: %d", stats["total_messages"])
            logger.info("Database total extracted entity count: %d", stats["total_entities"])
            logger.info("Database earliest message: %s", stats["earliest_message"])
            logger.info("Database latest message: %s", stats["latest_message"])
            message_count, entity_count = count_window_messages(session, window_start, window_end)
            logger.info("Window message count: %d", message_count)
            logger.info("Window extracted entity count: %d", entity_count)

            if args.prepare_only:
                input_path = write_prepare_only_input(session, window_start, window_end, args.base_dir)
                logger.info("Prepared grading input: %s", input_path)
                print(f"Prepared input: {input_path}")
                print(f"Log: {log_path}")
                return 0

            result = run_signal_grading(
                session,
                window_start,
                window_end,
                base_dir=args.base_dir,
                pairing_max_distance=settings.signal_pairing_max_distance,
            )
            logger.info("Input path: %s", result.input_path)
            logger.info("Output path: %s", result.output_path)
            logger.info("Latest output path: %s", result.latest_output_path)
            print(f"Input: {result.input_path}")
            print(f"Output: {result.output_path}")
            print(f"Latest: {result.latest_output_path}")
            print(f"Log: {log_path}")
            return 0
    except (GradingValidationError, RuntimeError, OSError) as exc:
        logger.exception("Signal grading failed: %s", exc)
        print(f"Signal grading failed: {exc}", file=sys.stderr)
        print(f"Log: {log_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
