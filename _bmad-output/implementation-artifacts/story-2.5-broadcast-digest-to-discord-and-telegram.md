# Story 2.5: Broadcast Digests to Discord and Telegram

Status: implemented

## Story

As a crypto alpha operator,
I want one CLI action to send a built digest to both Discord and Telegram,
so that the same operator update reaches both channels without manual copy/paste.

## Acceptance Criteria

1. Given `DISCORD_WEBHOOK_URL` is configured, when Discord delivery is requested, then the app posts the digest Markdown to that webhook using Discord's JSON webhook API.
2. Given Telegram delivery is already configured, when broadcast delivery is requested, then the app sends the same digest content through both Telegram and Discord adapters.
3. Given one destination succeeds and another fails, when broadcast delivery runs, then the command reports which destination failed and exits as an error instead of hiding partial failure.
4. Given existing Telegram-only send commands are used without broadcast options, when they run, then their existing Telegram behavior and output remain unchanged.
5. Given daily or window digests are sent with broadcast enabled, when the command runs, then the selected digest content is sent once to each configured destination.

## Tasks / Subtasks

- [x] Implement Discord webhook delivery (AC: 1)
  - [x] Add `DISCORD_WEBHOOK_URL` to settings and `.env.example`.
  - [x] Replace the Discord delivery stub with an HTTP webhook adapter.
  - [x] Split long digest content into Discord-compatible message chunks.
- [x] Implement broadcast delivery (AC: 2, 3)
  - [x] Add a delivery helper that sends to Telegram and Discord.
  - [x] Preserve partial-failure details in raised errors.
- [x] Wire broadcast delivery into CLI send commands (AC: 4, 5)
  - [x] Add a `--broadcast` option to daily and window send commands.
  - [x] Preserve existing Telegram-only default behavior and messages.
- [x] Add focused automated tests (AC: 1, 2, 3, 4, 5)
  - [x] Discord success, missing config, API failure, and long-message splitting.
  - [x] Broadcast success and partial failure reporting.
  - [x] Daily/window CLI broadcast path and Telegram-only regression coverage.

## Dev Notes

- Keep the implementation inside `app/delivery` and the CLI boundary; no queue, scheduler, frontend, or orchestration service is needed. [Source: `AGENTS.md`]
- Telegram delivery already exists in `app/delivery/telegram_send.py` and should be reused, not duplicated.
- `app/delivery/split_digest.py` supports configurable maximum lengths and can be reused for Discord's 2000-character content limit.
- Existing daily and window send commands currently call `send_telegram_message(summary.content)` directly and must remain backward compatible unless `--broadcast` is explicitly passed.
- Networked tests must mock HTTP calls and delivery adapters. [Source: `AGENTS.md`]

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_discord_send.py tests/test_broadcast_delivery.py tests/test_cli_commands.py tests/test_telegram_send.py -q`: 47 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 109 passed, total coverage 88%.
- BMAD code-review pass: found one helper edge case (`senders={}` falling back to real adapters); fixed and reran tests.
- `.venv/bin/pytest tests/test_broadcast_delivery.py -q && .venv/bin/pytest --cov=app --cov-report=term-missing`: 2 passed, then 109 passed, total coverage 88%.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 109 passed, total coverage 88% after README documentation update.
- GPT-5.4 medium review found README Discord delivery stub references, missing window `--discord-only` examples, stringly typed destination routing, and missing command-level broadcast partial-failure tests.
- `.venv/bin/pytest tests/test_cli_commands.py tests/test_discord_send.py tests/test_broadcast_delivery.py -q`: 49 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 115 passed, total coverage 88%.

### Completion Notes List

- Added a production Discord webhook sender using `DISCORD_WEBHOOK_URL`, JSON `content`, 30-second timeout, API error extraction, and 2000-character chunking.
- Added `send_broadcast_message` with per-destination error collection so Telegram and Discord are both attempted and partial failures are reported.
- Added `--broadcast` to `send-digest` and `send-window-digest`; existing Telegram-only defaults and messages remain unchanged.
- Added focused unit tests for Discord delivery, broadcaster behavior, and daily/window CLI broadcast wiring.
- Replaced stale README Discord delivery stub references with current webhook delivery documentation.
- Added command-level broadcast partial-failure coverage for daily and window send commands.
- Replaced string destination routing with a `SendDestination` enum and explicit unknown-destination errors.

### File List

- `_bmad-output/implementation-artifacts/story-2.5-broadcast-digest-to-discord-and-telegram.md`
- `.env.example`
- `README.md`
- `app/config.py`
- `app/delivery/discord_send.py`
- `app/delivery/broadcast.py`
- `app/cli.py`
- `tests/test_discord_send.py`
- `tests/test_broadcast_delivery.py`
- `tests/test_cli_commands.py`
