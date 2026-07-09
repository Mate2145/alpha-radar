# Story 2.6: Send Digests to Discord Only

Status: implemented

## Story

As a crypto alpha operator,
I want a Discord-only CLI send option,
so that I can post a digest to Discord without also sending it to Telegram.

## Acceptance Criteria

1. Given a daily digest has been built, when I run `send-digest --date YYYY-MM-DD --discord-only`, then the command sends the digest content through the Discord delivery adapter only.
2. Given a window digest has been built, when I run `send-window-digest --discord-only`, then the command sends the selected window digest content through the Discord delivery adapter only.
3. Given `--broadcast` and `--discord-only` are both provided, when either send command runs, then the command fails clearly instead of sending duplicate or ambiguous deliveries.
4. Given no Discord-only flag is provided, when existing send commands run, then Telegram-only default behavior remains unchanged.
5. Given `--broadcast` is provided, when existing broadcast send commands run, then Telegram plus Discord behavior remains unchanged.

## Tasks / Subtasks

- [x] Wire Discord-only delivery into CLI send commands (AC: 1, 2)
  - [x] Add `--discord-only` to `send-digest`.
  - [x] Add `--discord-only` to `send-window-digest`.
  - [x] Reuse the existing Discord delivery adapter.
- [x] Add option validation (AC: 3)
  - [x] Reject simultaneous `--broadcast` and `--discord-only`.
- [x] Preserve existing behavior (AC: 4, 5)
  - [x] Keep default Telegram-only behavior unchanged.
  - [x] Keep broadcast behavior unchanged.
- [x] Add focused tests (AC: 1, 2, 3, 4, 5)
  - [x] Daily Discord-only sends only via Discord adapter.
  - [x] Window Discord-only sends only via Discord adapter.
  - [x] Conflicting flags fail clearly.

## Dev Notes

- This is a CLI/delivery boundary change only. Do not add services, queues, scheduling, UI, or new integration layers.
- `app/delivery/discord_send.py` is the Discord adapter from Story 2.5 and should be reused directly.
- Existing `--broadcast` behavior should continue to use `send_broadcast_message`.
- Network calls must remain mocked in tests.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_cli_commands.py -q`: 41 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 113 passed, total coverage 88%.
- GPT-5.4 medium review found README examples omitted `send-window-digest --discord-only` and destination routing should avoid silent fallback.
- `.venv/bin/pytest tests/test_cli_commands.py tests/test_discord_send.py tests/test_broadcast_delivery.py -q`: 49 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 115 passed, total coverage 88%.

### Completion Notes List

- Added `--discord-only` to `send-digest` and `send-window-digest`.
- Added destination resolution so default Telegram, Discord-only, and broadcast behavior are explicit.
- Added clear validation for conflicting `--broadcast` and `--discord-only` flags.
- Updated README command examples and delivery note.
- Added `send-window-digest --discord-only` to README command examples.
- Replaced string destination routing with a `SendDestination` enum and explicit unknown-destination errors.

### File List

- `_bmad-output/implementation-artifacts/story-2.6-discord-only-digest-send.md`
- `README.md`
- `app/cli.py`
- `tests/test_cli_commands.py`
