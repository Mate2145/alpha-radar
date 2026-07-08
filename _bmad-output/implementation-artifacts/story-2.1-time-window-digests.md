# Story 2.1: Build Digests for Explicit Time Windows

Status: implemented

## Story

As a crypto alpha operator,
I want digest generation to accept an explicit time window or recent-hours value,
so that I can schedule useful updates every 2, 6, or 12 hours instead of only once per calendar day.

## Acceptance Criteria

1. Given messages exist inside a requested time window, when I run a time-window digest command, then the digest builder selects messages whose `created_at` falls within that exact window.
2. Given I request a recent-hours digest such as 2, 6, or 12 hours, when the command runs, then the system derives the correct window start and end timestamps and records them with the summary.
3. Given multiple digests are generated on the same calendar day, when each digest uses a different window, then the system stores them as separate summaries instead of overwriting a single daily row.
4. Given the existing daily digest command is still used, when it runs, then the current v1 daily behavior remains available until intentionally replaced.

## Implementation Notes

- Added `WindowSummary` as a separate table from `DailySummary` to avoid destabilizing the v1 daily flow.
- Added `build_window_digest(session, window_start, window_end)` and `load_messages_for_window(...)`.
- Added `alpha build-window-digest --since-hours N`.
- Added `alpha build-window-digest --from YYYY-MM-DDTHH:MM:SS --to YYYY-MM-DDTHH:MM:SS`.
- Window end is exclusive, matching common time-window query semantics.

## Test Expectations

- Explicit window selection includes `window_start` and excludes `window_end`.
- Separate windows on the same day create separate summary rows.
- CLI rejects mixed `--since-hours` and `--from/--to` modes.
- Existing daily digest tests continue passing.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_cli_commands.py tests/test_telegram_ingestion.py -q`: 23 passed.
- `.venv/bin/pytest tests/test_cli_commands.py tests/test_score_messages.py tests/test_telegram_ingestion.py -q`: 30 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 57 passed, total coverage 85%.
- GPT-5.4 medium `code-review` follow-up: no remaining findings.

### Completion Notes List

- Implemented Story 2.1 without changing the existing daily digest command.
- Preserved SQLite-first local operation.
- Added README usage for rolling and explicit time windows.
- Added window-specific cross-source scoring before window digest generation.
- Rejected timezone-offset datetimes for now to keep naive UTC window semantics explicit.
- Added tests for `--since-hours`, same-window update behavior, explicit window selection, and separate same-day window summaries.

### File List

- `README.md`
- `app/db/models.py`
- `app/cli.py`
- `app/summarization/digest_builder.py`
- `app/processing/score_messages.py`
- `tests/test_cli_commands.py`
- `tests/test_score_messages.py`
- `tests/test_telegram_ingestion.py`
