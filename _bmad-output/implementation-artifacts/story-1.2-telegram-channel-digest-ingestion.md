# Story 1.2: Ingest Configured Telegram Channels Into Daily Digest

Status: implemented

## Story

As a crypto alpha operator,
I want configured Telegram channel messages to be ingested into the normal digest database,
so that the final daily summary sent to my own Telegram channel includes Telegram-sourced alpha.

## Acceptance Criteria

1. Given Telegram API credentials and source channels are configured, when I run `alpha ingest-all`, then the system reads recent Telegram messages from the configured channels and persists new messages into the existing `messages` table with source metadata, score, entities, URL when available, and content hash.
2. Given Telegram messages were ingested for the target day, when I run `alpha build-digest --date YYYY-MM-DD`, then the digest includes Telegram messages in the same summarization path as RSS messages.
3. Given a digest has been built, when I run `alpha send-digest --date YYYY-MM-DD`, then the existing Telegram delivery command sends that final summary to my configured destination chat.
4. Given Telegram credentials or source channels are missing, when I run `alpha ingest-all`, then the Telegram ingestion step returns zero without corrupting RSS ingestion or existing data.
5. Given Telegram ingestion is run multiple times, when a message was already stored, then duplicate content is not inserted again.

## Tasks / Subtasks

- [x] Implement normal Telegram ingestion. (AC: 1, 4, 5)
  - [x] Reuse the existing Telethon history loader where possible.
  - [x] Add a configurable ingestion lookback window, defaulting to 24 hours.
  - [x] Upsert one `Source` row per Telegram channel.
  - [x] Persist messages, content hashes, scores, extracted entities, URL, and external IDs.
  - [x] Skip duplicates using existing content hash uniqueness.
  - [x] Return zero when Telegram source channels or API credentials are not configured.
- [x] Ensure digest pipeline includes Telegram data. (AC: 2)
  - [x] Keep ingested Telegram messages compatible with `build_digest`.
  - [x] Preserve RSS behavior in `ingest-all`.
- [x] Preserve existing delivery flow. (AC: 3)
  - [x] No new send command unless required; use existing `send-digest`.
  - [x] Document the end-to-end command sequence.
- [x] Add tests. (AC: 1, 2, 4, 5)
  - [x] Unit test Telegram ingestion persists messages and entities from mocked loader output.
  - [x] Unit test missing config returns zero.
  - [x] Unit test duplicate ingestion returns no additional rows.
  - [x] Unit/integration test digest builder sees ingested Telegram messages.

## Dev Notes

- Current Telegram smoke code lives in [app/ingest/telegram_ingest.py](app/ingest/telegram_ingest.py).
- `ingest_telegram(session)` is still the normal pipeline stub and should become the implementation entry point.
- Existing digest loading uses `Message.created_at.date() == summary_date`, so Telegram message timestamps must be normalized consistently.
- Existing content hash dedupe is global by normalized content, not per source.
- Keep tests mocked; do not require live Telegram network access.

### Project Structure Notes

- Stay inside `app/ingest`, `app/processing`, `app/db`, `app/summarization`, `app/cli.py`, README, env example, and tests as needed.
- Do not add queues, schedulers, services, frontend UI, or orchestration for this story.

### References

- [epics.md](_bmad-output/planning-artifacts/epics.md)
- [story-1.1-telegram-cashchat-smoke-test.md](_bmad-output/implementation-artifacts/story-1.1-telegram-cashchat-smoke-test.md)
- [telegram_ingest.py](app/ingest/telegram_ingest.py)
- [digest_builder.py](app/summarization/digest_builder.py)
- [models.py](app/db/models.py)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `pytest -q`: 20 passed, 8 warnings
- `pytest --cov=app --cov-report=term-missing`: 20 passed, total coverage 60%
- `python -m app.main --help`: CLI lists existing commands

### Completion Notes List

- Replaced the normal Telegram ingestion stub with a Telethon-backed ingestion path.
- Added `TELEGRAM_INGEST_LOOKBACK_HOURS` configuration with a 24-hour default.
- Telegram ingestion now no-ops with count `0` when channels or API credentials are missing.
- Ingested Telegram messages are persisted into the existing `sources`, `messages`, and `extracted_entities` tables.
- Duplicate content is skipped through the existing `content_hash` uniqueness constraint.
- The existing digest builder now includes persisted Telegram messages without a separate summarization path.
- End-to-end delivery remains `alpha send-digest --date YYYY-MM-DD`.
- Repo coverage remains below the 80% project target because broad pre-existing modules are untested.

### File List

- `.env.example`
- `README.md`
- `app/config.py`
- `app/ingest/telegram_ingest.py`
- `_bmad-output/planning-artifacts/epics.md`
- `_bmad-output/implementation-artifacts/story-1.2-telegram-channel-digest-ingestion.md`
- `tests/test_telegram_ingestion.py`
