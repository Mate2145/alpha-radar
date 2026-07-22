# Story 1.1: Detect `$cashchat` From Two Telegram Channels Over Last 24 Hours

Status: implemented

## Story

As a crypto alpha operator,
I want to run a local smoke test against two Telegram channels for the last 24 hours,
so that I can verify the system can recover the known Robinhood-related `$cashchat` signal from real source messages.

## Acceptance Criteria

1. Given two Telegram channels are configured, when I run the smoke-test command for a 24-hour lookback, then the system loads messages from both channels and evaluates only messages inside the lookback window.
2. Given the loaded messages include Robinhood-related content mentioning `$cashchat`, when the smoke test evaluates the messages, then the result identifies `$cashchat` as a found signal and includes source/message context for manual verification.
3. Given Telegram credentials or channel configuration are missing, when I run the smoke-test command, then the system fails with a clear configuration error and does not report a false no-signal result.
4. Given no matching `$cashchat` signal is present in the 24-hour messages, when I run the smoke-test command, then the system reports that the expected signal was not found and includes inspected channel/message counts.

## Tasks / Subtasks

- [x] Define Telegram smoke-test configuration. (AC: 1, 3)
  - [x] Add environment variables for Telegram API/session credentials or confirm the existing credential path.
  - [x] Add channel list configuration for exactly two MVP channels.
  - [x] Update `.env.example` and README with the required local setup.
- [x] Implement Telegram message loading behind the existing ingestion boundary. (AC: 1, 3)
  - [x] Fetch messages from configured channels for a configurable lookback window, defaulting to 24 hours.
  - [x] Normalize fetched messages into the existing message/source model or a testable intermediate structure.
  - [x] Keep network access isolated so unit tests can mock it.
- [x] Implement the smoke-test evaluation path. (AC: 2, 4)
  - [x] Detect Robinhood-related messages using a simple explicit keyword match for MVP scope.
  - [x] Detect `$cashchat` using the existing ticker/entity extraction behavior where possible.
  - [x] Return a structured result with found status, inspected channel count, inspected message count, and matching context.
- [x] Add a CLI command for the smoke test. (AC: 1, 2, 3, 4)
  - [x] Provide a command with defaults for `--lookback-hours 24` and `--expected-signal $cashchat`.
  - [x] Print a concise human-readable result.
- [x] Add tests. (AC: 1, 2, 3, 4)
  - [x] Unit test successful detection from mocked two-channel messages.
  - [x] Unit test missing configuration failure.
  - [x] Unit test no-match behavior with counts.
  - [x] Unit test lookback filtering.

## Dev Notes

- Keep the implementation inside current boundaries: `app/ingest`, `app/processing`, `app/cli.py`, and tests under `tests/`.
- The current Telegram ingestion module is a stub: [app/ingest/telegram_ingest.py](app/ingest/telegram_ingest.py).
- Existing entity extraction already recognizes `$TICKER`-style values: [app/processing/extract_entities.py](app/processing/extract_entities.py).
- Do not introduce queues, schedulers, background workers, a UI, or orchestration services for this story.
- Live Telegram integration details need one explicit implementation choice before coding: Bot API, Telethon user session, or another approved library.

### Project Structure Notes

- This is a CLI/backend smoke test, not a full production ingestion pipeline.
- If a new dependency is required for Telegram history access, keep it minimal and document why the standard Bot API is or is not sufficient for reading recent channel history.
- SQLite compatibility must be preserved.

### References

- [AGENTS.md](AGENTS.md)
- [epics.md](_bmad-output/planning-artifacts/epics.md)
- [telegram_ingest.py](app/ingest/telegram_ingest.py)
- [extract_entities.py](app/processing/extract_entities.py)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `pytest -q`: 16 passed
- `pytest --cov=app --cov-report=term-missing`: 16 passed, total coverage 45%
- CLI missing-config smoke check returns a clean Typer error for invalid `TELEGRAM_SOURCE_CHANNELS`

### Completion Notes List

- Added Telethon-backed history loading for two configured Telegram channels.
- Added a pure smoke evaluator that detects Robinhood-related `$cashchat` mentions case-insensitively.
- Added `smoke-telegram-signal` CLI command with defaults for 24 hours and `$cashchat`.
- Added tests for match, no-match, missing config, and message URL behavior.
- Live Telegram execution still requires valid `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and two `TELEGRAM_SOURCE_CHANNELS` values.
- Repo coverage remains below the 80% project target because broad pre-existing modules are untested.

### File List

- `.env.example`
- `README.md`
- `app/cli.py`
- `app/config.py`
- `app/ingest/telegram_ingest.py`
- `pyproject.toml`
- `requirements.txt`
- `tests/test_telegram_smoke.py`
