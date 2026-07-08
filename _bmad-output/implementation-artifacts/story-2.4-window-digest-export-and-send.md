# Story 2.4: Export and Send Window Digests

Status: implemented

## Story

As a crypto alpha operator,
I want to export and send the latest or explicitly selected time-window digest from the CLI,
so that 2-hour, 6-hour, and 12-hour digest workflows can be completed without manual SQLite queries.

## Acceptance Criteria

1. Given at least one window digest has been built, when I run a CLI export command for window digests without explicit bounds, then the command exports the latest `WindowSummary` content to Markdown.
2. Given I provide explicit `--from` and `--to` bounds, when I run the window export command, then the command exports the matching `WindowSummary` and fails clearly if that exact window has not been built.
3. Given no window digest exists, when I run the latest-window export or send command, then the command fails with an actionable "window digest has not been built" error.
4. Given a window digest has been built, when I run a CLI send command for window digests without explicit bounds, then the command sends the latest `WindowSummary` content through the existing Telegram delivery adapter.
5. Given I provide explicit `--from` and `--to` bounds, when I run the window send command, then the command sends the matching `WindowSummary` and fails clearly if that exact window has not been built.
6. Given existing daily digest commands are used, when `export-digest --date` or `send-digest --date` runs, then their current daily summary behavior remains unchanged.

## Tasks / Subtasks

- [x] Add window-summary lookup helpers in the CLI boundary (AC: 1, 2, 3, 4, 5)
  - [x] Select latest `WindowSummary` by `created_at` or `id` when no explicit bounds are provided.
  - [x] Select exact `WindowSummary` by `window_start` and `window_end` when `--from` and `--to` are provided.
  - [x] Reuse existing `parse_window_datetime` semantics: ISO datetime, naive UTC, start before end.
  - [x] Return clear `typer.BadParameter` errors when no matching window summary exists.
- [x] Add a CLI export command for window digests (AC: 1, 2, 3)
  - [x] Default output path should be deterministic, e.g. `data/window-digest-latest.md` for latest or `data/window-digest-YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.md` for explicit windows.
  - [x] Support `--output` override.
  - [x] Write only the selected window summary content, not database metadata.
- [x] Add a CLI send command for window digests (AC: 4, 5)
  - [x] Use existing `send_telegram_message(summary.content)` delivery behavior.
  - [x] Preserve existing split-long-message support through the delivery adapter.
  - [x] Log and surface Telegram delivery failures the same way daily `send-digest` does.
- [x] Preserve daily command behavior (AC: 6)
  - [x] Do not change `export-digest --date` semantics.
  - [x] Do not change `send-digest --date` semantics.
- [x] Add focused tests (AC: 1, 2, 3, 4, 5, 6)
  - [x] Export latest window digest.
  - [x] Export explicit window digest.
  - [x] Export failure when no window digest exists.
  - [x] Send latest window digest.
  - [x] Send explicit window digest.
  - [x] Send/export failure when exact explicit window has not been built.
  - [x] Existing daily export/send command tests still pass.

## Dev Notes

- Keep this as CLI/backend work only. Do not add UI, services, queues, schedulers, or orchestration. [Source: `AGENTS.md`]
- `WindowSummary` already exists with `window_start`, `window_end`, `content`, `model`, and `created_at`; no schema change should be needed. [Source: `app/db/models.py`]
- Story 2.1 added `build-window-digest --since-hours` and explicit `--from/--to` build support. This story completes the operator workflow by adding equivalent export/send paths. [Source: `_bmad-output/implementation-artifacts/story-2.1-time-window-digests.md`]
- Daily commands currently use `DailySummary` only and must remain stable. [Source: `app/cli.py`]
- Telegram delivery already splits long Markdown via `send_telegram_message`; window send should reuse that adapter rather than duplicating HTTP logic. [Source: `app/delivery/telegram_send.py`, `app/delivery/split_digest.py`]
- Tests should mock `send_telegram_message`; do not send live Telegram messages in automated tests. [Source: `AGENTS.md`]

### Project Structure Notes

- Expected code touch point: `app/cli.py`.
- Expected test touch point: `tests/test_cli_commands.py`.
- No database migration expected.
- No changes expected in ingestion, processing, summarization, or delivery internals unless implementation reveals a small helper is needed.

### References

- `AGENTS.md` - project standards and test requirements.
- `app/cli.py` - current daily export/send and window build commands.
- `app/db/models.py` - `WindowSummary` model.
- `_bmad-output/implementation-artifacts/story-2.1-time-window-digests.md` - time-window digest creation context.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_cli_commands.py -q`: 31 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 95 passed, total coverage 87%.
- GPT-5.4 medium `code-review` subagent: 3 findings; all addressed.
- `.venv/bin/pytest tests/test_cli_commands.py -q`: 35 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 99 passed, total coverage 88%.

### Completion Notes List

- Added `export-window-digest` for latest or exact-window Markdown export.
- Added `send-window-digest` for latest or exact-window Telegram delivery through the existing adapter.
- Added CLI helpers for optional window bounds, exact/latest lookup, and deterministic default filenames.
- Preserved existing daily `export-digest` and `send-digest` behavior.
- Added real SQLite tests proving latest and exact-window lookup select the intended `WindowSummary`.
- Added exact-window missing-summary failure coverage for both export and send commands.
- Updated `export-window-digest --output` help text to document latest and explicit-window default paths.

### File List

- `_bmad-output/implementation-artifacts/story-2.4-window-digest-export-and-send.md`
- `app/cli.py`
- `tests/test_cli_commands.py`
