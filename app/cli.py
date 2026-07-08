import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.migrations import init_db
from app.db.models import DailySummary, WindowSummary
from app.delivery.telegram_send import send_telegram_message
from app.ingest.discord_ingest import ingest_discord
from app.ingest.rss_ingest import ingest_rss
from app.ingest.telegram_ingest import ingest_telegram, run_telegram_signal_smoke_test
from app.processing.score_messages import apply_cross_source_bonus, apply_cross_source_bonus_for_window
from app.summarization.digest_builder import build_digest, build_window_digest
from app.summarization.llm_client import LLMClient
from app.utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = typer.Typer(help="Alpha Digest CLI")


def parse_summary_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Date must be in YYYY-MM-DD format.") from exc


def parse_window_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("Datetime must be in ISO format, e.g. YYYY-MM-DDTHH:MM:SS.") from exc
    if parsed.tzinfo is not None:
        raise typer.BadParameter("Datetime must not include a timezone offset; use naive UTC.")
    return parsed


def resolve_digest_window(
    since_hours: int | None,
    window_start_value: str | None,
    window_end_value: str | None,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    if since_hours is not None:
        if window_start_value or window_end_value:
            raise typer.BadParameter("Use either --since-hours or both --from/--to, not both.")
        if since_hours <= 0:
            raise typer.BadParameter("--since-hours must be greater than zero.")
        window_end = (now or datetime.utcnow()).replace(microsecond=0)
        return window_end - timedelta(hours=since_hours), window_end

    if not window_start_value or not window_end_value:
        raise typer.BadParameter("Use --since-hours or provide both --from and --to.")

    window_start = parse_window_datetime(window_start_value)
    window_end = parse_window_datetime(window_end_value)
    if window_start >= window_end:
        raise typer.BadParameter("--from must be before --to.")
    return window_start, window_end


def resolve_optional_window_bounds(
    window_start_value: str | None,
    window_end_value: str | None,
) -> tuple[datetime, datetime] | None:
    if not window_start_value and not window_end_value:
        return None
    if not window_start_value or not window_end_value:
        raise typer.BadParameter("Provide both --from and --to, or neither for the latest window.")

    window_start = parse_window_datetime(window_start_value)
    window_end = parse_window_datetime(window_end_value)
    if window_start >= window_end:
        raise typer.BadParameter("--from must be before --to.")
    return window_start, window_end


def load_window_summary(
    session: Session,
    window_bounds: tuple[datetime, datetime] | None,
) -> WindowSummary:
    if window_bounds is None:
        summary = session.scalar(
            select(WindowSummary).order_by(
                WindowSummary.created_at.desc(),
                WindowSummary.id.desc(),
            )
        )
        if not summary:
            raise typer.BadParameter("Window digest has not been built.")
        return summary

    window_start, window_end = window_bounds
    summary = session.scalar(
        select(WindowSummary).where(
            WindowSummary.window_start == window_start,
            WindowSummary.window_end == window_end,
        )
    )
    if not summary:
        raise typer.BadParameter("Window digest has not been built for this exact window.")
    return summary


def default_window_digest_path(summary: WindowSummary, latest: bool) -> Path:
    if latest:
        return Path("data") / "window-digest-latest.md"
    start = summary.window_start.strftime("%Y%m%dT%H%M%S")
    end = summary.window_end.strftime("%Y%m%dT%H%M%S")
    return Path("data") / f"window-digest-{start}-{end}.md"


@app.command("init-db")
def init_db_command() -> None:
    logger.info("Initializing database at %s", get_settings().database_url)
    init_db()
    typer.echo("Database initialized.")
    logger.info("Database initialized.")


@app.command("ingest-rss")
def ingest_rss_command() -> None:
    init_db()
    logger.info("Starting RSS ingestion")
    with SessionLocal() as session:
        count = ingest_rss(session)
    typer.echo(f"Ingested {count} new RSS messages.")
    logger.info("RSS ingestion complete: %d new messages", count)


@app.command("ingest-all")
def ingest_all_command() -> None:
    init_db()
    logger.info("Starting full ingestion")
    with SessionLocal() as session:
        rss_count = ingest_rss(session)
        telegram_count = ingest_telegram(session)
        discord_count = ingest_discord(session)
    typer.echo(
        f"Ingested rss={rss_count}, telegram={telegram_count}, discord={discord_count} messages."
    )
    logger.info(
        "Full ingestion complete: rss=%d, telegram=%d, discord=%d",
        rss_count,
        telegram_count,
        discord_count,
    )


@app.command("build-digest")
def build_digest_command(
    summary_date_value: str = typer.Option(
        ..., "--date", help="Digest date in YYYY-MM-DD format"
    ),
) -> None:
    summary_date = parse_summary_date(summary_date_value)
    init_db()
    logger.info("Building digest for %s", summary_date.isoformat())
    with SessionLocal() as session:
        apply_cross_source_bonus(session, summary_date)
        try:
            summary = build_digest(session, summary_date)
        except RuntimeError as exc:
            logger.error("Failed to build digest for %s: %s", summary_date.isoformat(), exc)
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Built digest for {summary.summary_date.isoformat()} using {summary.model}.")
    logger.info("Digest built for %s using model %s", summary.summary_date.isoformat(), summary.model)


@app.command("build-window-digest")
def build_window_digest_command(
    since_hours: int | None = typer.Option(
        None, "--since-hours", help="Build a digest for the last N hours."
    ),
    window_start_value: str | None = typer.Option(
        None, "--from", help="Window start as ISO datetime, e.g. 2026-07-08T06:00:00."
    ),
    window_end_value: str | None = typer.Option(
        None, "--to", help="Window end as ISO datetime, e.g. 2026-07-08T12:00:00."
    ),
) -> None:
    window_start, window_end = resolve_digest_window(
        since_hours,
        window_start_value,
        window_end_value,
    )
    init_db()
    logger.info("Building window digest from %s to %s", window_start.isoformat(), window_end.isoformat())
    with SessionLocal() as session:
        apply_cross_source_bonus_for_window(session, window_start, window_end)
        try:
            summary = build_window_digest(session, window_start, window_end)
        except RuntimeError as exc:
            logger.error("Failed to build window digest: %s", exc)
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        "Built window digest "
        f"{summary.window_start.isoformat()} to {summary.window_end.isoformat()} "
        f"using {summary.model}."
    )
    logger.info(
        "Window digest built from %s to %s using model %s",
        summary.window_start.isoformat(),
        summary.window_end.isoformat(),
        summary.model,
    )


@app.command("send-digest")
def send_digest_command(
    summary_date_value: str = typer.Option(
        ..., "--date", help="Digest date in YYYY-MM-DD format"
    ),
) -> None:
    summary_date = parse_summary_date(summary_date_value)
    init_db()
    logger.info("Sending digest for %s", summary_date.isoformat())
    with SessionLocal() as session:
        summary = session.scalar(select(DailySummary).where(DailySummary.summary_date == summary_date))
        if not summary:
            message = "Digest has not been built for this date."
            logger.error(message)
            raise typer.BadParameter(message)
        try:
            send_telegram_message(summary.content)
        except RuntimeError as exc:
            logger.error("Failed to send digest for %s: %s", summary_date.isoformat(), exc)
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Sent digest for {summary_date.isoformat()} to Telegram.")
    logger.info("Digest sent for %s", summary_date.isoformat())


@app.command("send-window-digest")
def send_window_digest_command(
    window_start_value: str | None = typer.Option(
        None, "--from", help="Window start as ISO datetime. Omit with --to for latest window."
    ),
    window_end_value: str | None = typer.Option(
        None, "--to", help="Window end as ISO datetime. Omit with --from for latest window."
    ),
) -> None:
    window_bounds = resolve_optional_window_bounds(window_start_value, window_end_value)
    init_db()
    logger.info("Sending window digest")
    with SessionLocal() as session:
        summary = load_window_summary(session, window_bounds)
        try:
            send_telegram_message(summary.content)
        except RuntimeError as exc:
            logger.error("Failed to send window digest: %s", exc)
            raise typer.BadParameter(str(exc)) from exc
    typer.echo(
        "Sent window digest "
        f"{summary.window_start.isoformat()} to {summary.window_end.isoformat()} "
        "to Telegram."
    )
    logger.info(
        "Window digest sent from %s to %s",
        summary.window_start.isoformat(),
        summary.window_end.isoformat(),
    )


@app.command("check-llm")
def check_llm_command() -> None:
    client = LLMClient()
    logger.info("Checking LLM provider: %s", client.model_name)
    if not client.configured:
        typer.echo("LLM provider is fallback-rule-based. No external provider check needed.")
        logger.info("LLM provider is fallback-rule-based.")
        return
    try:
        result = client.complete(
            "Reply with exactly: OK",
            "This is a provider health check. Reply with exactly: OK",
        )
    except RuntimeError as exc:
        logger.error("LLM provider check failed: %s", exc)
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"LLM provider OK: {client.model_name}")
    typer.echo(result.strip()[:200])
    logger.info("LLM provider OK: %s", client.model_name)


@app.command("export-digest")
def export_digest_command(
    summary_date_value: str = typer.Option(
        ..., "--date", help="Digest date in YYYY-MM-DD format"
    ),
    output_path: Path | None = typer.Option(
        None, "--output", help="Output Markdown path. Defaults to data/digest-YYYY-MM-DD.md"
    ),
) -> None:
    summary_date = parse_summary_date(summary_date_value)
    target = output_path or Path("data") / f"digest-{summary_date.isoformat()}.md"
    init_db()
    logger.info("Exporting digest for %s to %s", summary_date.isoformat(), target)
    with SessionLocal() as session:
        summary = session.scalar(select(DailySummary).where(DailySummary.summary_date == summary_date))
        if not summary:
            message = "Digest has not been built for this date."
            logger.error(message)
            raise typer.BadParameter(message)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(summary.content, encoding="utf-8")
    typer.echo(f"Exported digest to {target}")
    logger.info("Digest exported to %s", target)


@app.command("export-window-digest")
def export_window_digest_command(
    window_start_value: str | None = typer.Option(
        None, "--from", help="Window start as ISO datetime. Omit with --to for latest window."
    ),
    window_end_value: str | None = typer.Option(
        None, "--to", help="Window end as ISO datetime. Omit with --from for latest window."
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help=(
            "Output Markdown path. Defaults to data/window-digest-latest.md for latest "
            "or data/window-digest-YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.md for explicit windows."
        ),
    ),
) -> None:
    window_bounds = resolve_optional_window_bounds(window_start_value, window_end_value)
    init_db()
    logger.info("Exporting window digest")
    with SessionLocal() as session:
        summary = load_window_summary(session, window_bounds)
    target = output_path or default_window_digest_path(summary, latest=window_bounds is None)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(summary.content, encoding="utf-8")
    typer.echo(f"Exported window digest to {target}")
    logger.info("Window digest exported to %s", target)


@app.command("smoke-telegram-signal")
def smoke_telegram_signal_command(
    lookback_hours: int = typer.Option(24, "--lookback-hours", help="Lookback window in hours"),
    expected_signal: str = typer.Option("$cashchat", "--expected-signal", help="Ticker/signal to find"),
) -> None:
    logger.info(
        "Running Telegram signal smoke test: lookback_hours=%d expected_signal=%s",
        lookback_hours,
        expected_signal,
    )
    try:
        result = run_telegram_signal_smoke_test(
            lookback_hours=lookback_hours,
            expected_signal=expected_signal,
        )
    except RuntimeError as exc:
        logger.error("Telegram signal smoke test failed: %s", exc)
        raise typer.BadParameter(str(exc)) from exc
    status = "FOUND" if result.found else "NOT FOUND"
    typer.echo(
        f"{status} {result.expected_signal} "
        f"channels={result.inspected_channels} messages={result.inspected_messages}"
    )
    logger.info(
        "Telegram signal smoke test result: %s %s channels=%d messages=%d",
        status,
        result.expected_signal,
        result.inspected_channels,
        result.inspected_messages,
    )
    for match in result.matches[:5]:
        preview = " ".join(match.content.split())[:220]
        url = f" {match.url}" if match.url else ""
        typer.echo(f"- [{match.channel}] {match.created_at.isoformat()}: {preview}{url}")
