from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
import typer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import cli
from app.db.database import Base
from app.db.models import WindowSummary


class FakeSession:
    def __init__(self, summary: SimpleNamespace | None = None) -> None:
        self.summary = summary

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def scalar(self, statement) -> SimpleNamespace | None:
        _ = statement
        return self.summary


class FakeLLMClient:
    configured = True
    model_name = "codex-cli:default"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "OK" in system_prompt
        assert "provider health check" in user_prompt
        return "OK"


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as session:
        yield session


def test_init_db_command(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: calls.append(True))
    cli.init_db_command()
    assert calls == [True]
    assert "Database initialized" in capsys.readouterr().out


def test_ingest_rss_command(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(cli, "ingest_rss", lambda session: 5)
    cli.ingest_rss_command()
    assert "Ingested 5 new RSS messages" in capsys.readouterr().out


def test_ingest_all_command(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(cli, "ingest_rss", lambda session: 3)
    monkeypatch.setattr(cli, "ingest_telegram", lambda session: 2)
    monkeypatch.setattr(cli, "ingest_discord", lambda session: 1)
    cli.ingest_all_command()
    output = capsys.readouterr().out
    assert "rss=3" in output
    assert "telegram=2" in output
    assert "discord=1" in output


def test_build_digest_command_success(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="digest", model="codex")
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(cli, "apply_cross_source_bonus", lambda session, d: None)
    monkeypatch.setattr(cli, "build_digest", lambda session, d: summary)
    cli.build_digest_command("2026-07-08")
    assert "Built digest for 2026-07-08 using codex" in capsys.readouterr().out


def test_build_digest_command_reports_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(session, d):
        raise RuntimeError("LLM failed")

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(cli, "apply_cross_source_bonus", lambda session, d: None)
    monkeypatch.setattr(cli, "build_digest", fail)
    with pytest.raises(typer.BadParameter, match="LLM failed"):
        cli.build_digest_command("2026-07-08")


def test_resolve_digest_window_from_explicit_bounds() -> None:
    window_start, window_end = cli.resolve_digest_window(
        None,
        "2026-07-08T06:00:00",
        "2026-07-08T12:00:00",
    )

    assert window_start == datetime(2026, 7, 8, 6)
    assert window_end == datetime(2026, 7, 8, 12)


def test_resolve_digest_window_from_since_hours_uses_current_time() -> None:
    window_start, window_end = cli.resolve_digest_window(
        6,
        None,
        None,
        now=datetime(2026, 7, 8, 12, 30, 45, 123456),
    )

    assert window_start == datetime(2026, 7, 8, 6, 30, 45)
    assert window_end == datetime(2026, 7, 8, 12, 30, 45)


def test_resolve_digest_window_rejects_mixed_modes() -> None:
    with pytest.raises(typer.BadParameter, match="either --since-hours"):
        cli.resolve_digest_window(6, "2026-07-08T06:00:00", "2026-07-08T12:00:00")


def test_parse_window_datetime_rejects_timezone_offsets() -> None:
    with pytest.raises(typer.BadParameter, match="must not include a timezone offset"):
        cli.parse_window_datetime("2026-07-08T06:00:00+02:00")


def test_build_window_digest_command_success(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="digest",
        model="fallback-rule-based",
    )
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        cli,
        "apply_cross_source_bonus_for_window",
        lambda session, start, end: None,
    )
    monkeypatch.setattr(cli, "build_window_digest", lambda session, start, end: summary)

    cli.build_window_digest_command(None, "2026-07-08T06:00:00", "2026-07-08T12:00:00")

    output = capsys.readouterr().out
    assert "Built window digest 2026-07-08T06:00:00 to 2026-07-08T12:00:00" in output


def test_grade_signals_command_success(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    result = SimpleNamespace(
        input_path="data/signal-grading/input/window.json",
        output_path="data/signal-grading/output/window.json",
        latest_output_path="data/signal-grading/output/latest.json",
    )
    calls = {}
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())

    def fake_run_signal_grading(session, start, end, **kwargs):
        calls["start"] = start
        calls["end"] = end
        calls.update(kwargs)
        return result

    monkeypatch.setattr(cli, "run_signal_grading", fake_run_signal_grading)
    cli.grade_signals_command(None, "2026-07-08T06:00:00", "2026-07-08T12:00:00")

    output = capsys.readouterr().out
    assert calls["start"] == datetime(2026, 7, 8, 6)
    assert calls["end"] == datetime(2026, 7, 8, 12)
    assert calls["pairing_max_distance"] == 120
    assert "Graded signals" in output
    assert "data/signal-grading/input/window.json" in output
    assert "data/signal-grading/output/window.json" in output


def test_grade_signals_command_reports_grading_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())

    def fail(session, start, end, **kwargs):
        _ = session, start, end, kwargs
        raise cli.GradingValidationError("invalid grading output")

    monkeypatch.setattr(cli, "run_signal_grading", fail)

    with pytest.raises(typer.BadParameter, match="invalid grading output"):
        cli.grade_signals_command(None, "2026-07-08T06:00:00", "2026-07-08T12:00:00")


def test_grade_signals_command_reports_codex_runtime_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession())

    def fail(session, start, end, **kwargs):
        _ = session, start, end, kwargs
        raise RuntimeError("Signal grading requires LLM_PROVIDER=codex_cli")

    monkeypatch.setattr(cli, "run_signal_grading", fail)

    with pytest.raises(typer.BadParameter, match="LLM_PROVIDER=codex_cli"):
        cli.grade_signals_command(None, "2026-07-08T06:00:00", "2026-07-08T12:00:00")


def test_resolve_optional_window_bounds_accepts_latest_mode() -> None:
    assert cli.resolve_optional_window_bounds(None, None) is None


def test_resolve_optional_window_bounds_rejects_partial_bounds() -> None:
    with pytest.raises(typer.BadParameter, match="Provide both --from and --to"):
        cli.resolve_optional_window_bounds("2026-07-08T06:00:00", None)


def test_default_window_digest_path_latest() -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
    )

    assert cli.default_window_digest_path(summary, latest=True).as_posix() == (
        "data/window-digest-latest.md"
    )


def test_default_window_digest_path_explicit_window() -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
    )

    assert cli.default_window_digest_path(summary, latest=False).as_posix() == (
        "data/window-digest-20260708T060000-20260708T120000.md"
    )


def test_load_window_summary_latest_selects_newest_window(db_session: Session) -> None:
    older = WindowSummary(
        window_start=datetime(2026, 7, 8, 0),
        window_end=datetime(2026, 7, 8, 6),
        content="# Older",
        model="fallback",
        created_at=datetime(2026, 7, 8, 6, 1),
    )
    newer = WindowSummary(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Newer",
        model="fallback",
        created_at=datetime(2026, 7, 8, 12, 1),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    summary = cli.load_window_summary(db_session, None)

    assert summary.content == "# Newer"


def test_load_window_summary_explicit_selects_matching_window(db_session: Session) -> None:
    first = WindowSummary(
        window_start=datetime(2026, 7, 8, 0),
        window_end=datetime(2026, 7, 8, 6),
        content="# First",
        model="fallback",
    )
    second = WindowSummary(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Second",
        model="fallback",
    )
    db_session.add_all([first, second])
    db_session.commit()

    summary = cli.load_window_summary(
        db_session,
        (datetime(2026, 7, 8, 0), datetime(2026, 7, 8, 6)),
    )

    assert summary.content == "# First"


def test_send_digest_command_success(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="# Digest")
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", lambda content: calls.append(content))
    cli.send_digest_command("2026-07-08")
    assert calls == ["# Digest"]
    assert "Sent digest for 2026-07-08 to Telegram" in capsys.readouterr().out


def test_send_digest_command_broadcasts(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="# Digest")
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_broadcast_message", lambda content: calls.append(content))
    cli.send_digest_command("2026-07-08", broadcast=True)
    assert calls == ["# Digest"]
    assert "Sent digest for 2026-07-08 to Telegram and Discord" in capsys.readouterr().out


def test_send_digest_command_reports_broadcast_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="# Digest")

    def fail(content: str) -> None:
        _ = content
        raise RuntimeError("Broadcast delivery failed for discord: webhook rejected")

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_broadcast_message", fail)

    with pytest.raises(typer.BadParameter, match="discord: webhook rejected"):
        cli.send_digest_command("2026-07-08", broadcast=True)


def test_send_digest_command_sends_discord_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="# Digest")
    telegram_calls = []
    discord_calls = []
    broadcast_calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", lambda content: telegram_calls.append(content))
    monkeypatch.setattr(cli, "send_discord_message", lambda content: discord_calls.append(content))
    monkeypatch.setattr(cli, "send_broadcast_message", lambda content: broadcast_calls.append(content))

    cli.send_digest_command("2026-07-08", discord_only=True)

    assert telegram_calls == []
    assert discord_calls == ["# Digest"]
    assert broadcast_calls == []
    assert "Sent digest for 2026-07-08 to Discord" in capsys.readouterr().out


def test_send_digest_command_rejects_conflicting_destinations() -> None:
    with pytest.raises(typer.BadParameter, match="either --broadcast or --discord-only"):
        cli.send_digest_command("2026-07-08", broadcast=True, discord_only=True)


def test_send_digest_command_requires_existing_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))
    with pytest.raises(typer.BadParameter, match="Digest has not been built"):
        cli.send_digest_command("2026-07-08")


def test_send_digest_command_reports_delivery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = SimpleNamespace(summary_date=date(2026, 7, 8), content="# Digest")

    def fail(content: str) -> None:
        raise RuntimeError("chat not found")

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", fail)
    with pytest.raises(typer.BadParameter, match="chat not found"):
        cli.send_digest_command("2026-07-08")


def test_send_window_digest_command_sends_latest(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Window Digest",
    )
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", lambda content: calls.append(content))

    cli.send_window_digest_command(None, None)

    assert calls == ["# Window Digest"]
    assert "Sent window digest 2026-07-08T06:00:00 to 2026-07-08T12:00:00" in (
        capsys.readouterr().out
    )


def test_send_window_digest_command_broadcasts(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Window Digest",
    )
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_broadcast_message", lambda content: calls.append(content))

    cli.send_window_digest_command(None, None, broadcast=True)

    assert calls == ["# Window Digest"]
    assert "to Telegram and Discord" in capsys.readouterr().out


def test_send_window_digest_command_reports_broadcast_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Window Digest",
    )

    def fail(content: str) -> None:
        _ = content
        raise RuntimeError("Broadcast delivery failed for telegram: chat not found")

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_broadcast_message", fail)

    with pytest.raises(typer.BadParameter, match="telegram: chat not found"):
        cli.send_window_digest_command(None, None, broadcast=True)


def test_send_window_digest_command_sends_discord_only(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Window Digest",
    )
    telegram_calls = []
    discord_calls = []
    broadcast_calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", lambda content: telegram_calls.append(content))
    monkeypatch.setattr(cli, "send_discord_message", lambda content: discord_calls.append(content))
    monkeypatch.setattr(cli, "send_broadcast_message", lambda content: broadcast_calls.append(content))

    cli.send_window_digest_command(None, None, discord_only=True)

    assert telegram_calls == []
    assert discord_calls == ["# Window Digest"]
    assert broadcast_calls == []
    assert "to Discord" in capsys.readouterr().out


def test_send_window_digest_command_rejects_conflicting_destinations() -> None:
    with pytest.raises(typer.BadParameter, match="either --broadcast or --discord-only"):
        cli.send_window_digest_command(None, None, broadcast=True, discord_only=True)


def test_send_window_digest_command_sends_explicit_window(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Explicit Window Digest",
    )
    calls = []
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", lambda content: calls.append(content))

    cli.send_window_digest_command("2026-07-08T06:00:00", "2026-07-08T12:00:00")

    assert calls == ["# Explicit Window Digest"]


def test_send_window_digest_command_requires_existing_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))

    with pytest.raises(typer.BadParameter, match="Window digest has not been built"):
        cli.send_window_digest_command(None, None)


def test_send_window_digest_command_requires_exact_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))

    with pytest.raises(typer.BadParameter, match="this exact window"):
        cli.send_window_digest_command("2026-07-08T06:00:00", "2026-07-08T12:00:00")


def test_send_window_digest_command_reports_delivery_error(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Window Digest",
    )

    def fail(content: str) -> None:
        raise RuntimeError("chat not found")

    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))
    monkeypatch.setattr(cli, "send_telegram_message", fail)

    with pytest.raises(typer.BadParameter, match="chat not found"):
        cli.send_window_digest_command(None, None)


def test_check_llm_command_reports_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "LLMClient", FakeLLMClient)

    cli.check_llm_command()

    output = capsys.readouterr().out
    assert "LLM provider OK: codex-cli:default" in output
    assert "OK" in output


def test_check_llm_command_reports_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            raise RuntimeError("codex exec failed: not logged in")

    monkeypatch.setattr(cli, "LLMClient", FailingClient)

    with pytest.raises(typer.BadParameter, match="not logged in"):
        cli.check_llm_command()


def test_check_llm_command_fallback(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FallbackClient:
        configured = False
        model_name = "fallback-rule-based"

    monkeypatch.setattr(cli, "LLMClient", FallbackClient)
    cli.check_llm_command()
    assert "fallback-rule-based" in capsys.readouterr().out


def test_export_digest_command_writes_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    summary = SimpleNamespace(
        summary_date=date(2026, 7, 8),
        content="# Digest\n\nHello",
        model="codex-cli:default",
    )
    output = tmp_path / "digest.md"
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))

    cli.export_digest_command("2026-07-08", output)

    assert output.read_text(encoding="utf-8") == "# Digest\n\nHello"


def test_export_digest_command_requires_existing_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))

    with pytest.raises(typer.BadParameter, match="Digest has not been built"):
        cli.export_digest_command("2026-07-08", tmp_path / "digest.md")


def test_export_window_digest_command_writes_latest_markdown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Latest Window Digest",
    )
    output = tmp_path / "window.md"
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))

    cli.export_window_digest_command(None, None, output)

    assert output.read_text(encoding="utf-8") == "# Latest Window Digest"


def test_export_window_digest_command_writes_explicit_default_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    summary = SimpleNamespace(
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        content="# Explicit Window Digest",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(summary))

    cli.export_window_digest_command("2026-07-08T06:00:00", "2026-07-08T12:00:00", None)

    output = tmp_path / "data" / "window-digest-20260708T060000-20260708T120000.md"
    assert output.read_text(encoding="utf-8") == "# Explicit Window Digest"


def test_export_window_digest_command_requires_existing_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))

    with pytest.raises(typer.BadParameter, match="Window digest has not been built"):
        cli.export_window_digest_command(None, None, tmp_path / "window.md")


def test_export_window_digest_command_requires_exact_window(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(cli, "init_db", lambda: None)
    monkeypatch.setattr(cli, "SessionLocal", lambda: FakeSession(None))

    with pytest.raises(typer.BadParameter, match="this exact window"):
        cli.export_window_digest_command(
            "2026-07-08T06:00:00",
            "2026-07-08T12:00:00",
            tmp_path / "window.md",
        )


def test_smoke_telegram_signal_command_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    match = SimpleNamespace(
        channel="@foo",
        created_at=datetime.now(timezone.utc),
        content="$cashchat robinhood listing",
        url="https://t.me/foo/1",
    )
    result = SimpleNamespace(
        found=True,
        expected_signal="$cashchat",
        inspected_channels=2,
        inspected_messages=10,
        matches=[match],
    )
    monkeypatch.setattr(
        cli, "run_telegram_signal_smoke_test", lambda **kwargs: result
    )
    cli.smoke_telegram_signal_command()
    output = capsys.readouterr().out
    assert "FOUND $cashchat channels=2 messages=10" in output
    assert "@foo" in output


def test_smoke_telegram_signal_command_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(**kwargs):
        raise RuntimeError("missing credentials")

    monkeypatch.setattr(cli, "run_telegram_signal_smoke_test", fail)
    with pytest.raises(typer.BadParameter, match="missing credentials"):
        cli.smoke_telegram_signal_command()
