# Story 2.7: Six-Hour Broadcast Digest Script

Status: implemented

## Story

As a crypto alpha operator,
I want a script that always broadcasts the latest 6-hour digest window,
so that scheduled runs can send a fresh rolling update to Telegram and Discord without manual CLI steps.

## Acceptance Criteria

1. Given the script is run from any working directory, when it starts, then it changes into the project root and loads the local virtualenv and `.env` file.
2. Given source integrations are configured, when the script runs, then it ingests current sources before building the digest.
3. Given the script runs, when it builds a digest, then it uses a rolling `--since-hours 6` window.
4. Given the 6-hour digest is built, when delivery runs, then the script broadcasts the latest window digest to both Telegram and Discord.
5. Given the script completes, when operators inspect local output, then the latest window digest Markdown has been exported for audit.

## Tasks / Subtasks

- [x] Add six-hour broadcast script (AC: 1, 2, 3, 4, 5)
  - [x] Load `.venv` and `.env` like the existing daily script.
  - [x] Run `ingest-all`.
  - [x] Run `build-window-digest --since-hours 6`.
  - [x] Run `export-window-digest`.
  - [x] Run `send-window-digest --broadcast`.
- [x] Document script usage (AC: 4, 5)
  - [x] Add README example for scheduled 6-hour broadcast.
- [x] Verify script syntax and existing tests (AC: 1, 2, 3, 4, 5)

## Dev Notes

- Keep this as a shell script under `scripts/`, matching `scripts/run_daily_digest.sh`.
- Do not add schedulers, services, workers, queues, or new orchestration.
- Use the existing CLI commands and delivery adapters.
- The script should broadcast the most recently built window digest by building the 6-hour window immediately before sending.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `bash -n scripts/run_6h_broadcast_digest.sh`: passed.
- `ls -l scripts/run_6h_broadcast_digest.sh`: executable bit present.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 115 passed, total coverage 88%.

### Completion Notes List

- Added `scripts/run_6h_broadcast_digest.sh` to ingest, build a rolling 6-hour window digest, export the latest window Markdown, and broadcast it to Telegram and Discord.
- Script mirrors the existing daily script setup: project-root `cd`, `.venv` activation, optional `.env` loading, and `LLM_PROVIDER` default to `codex_cli`.
- Documented the script in README for scheduled intraday broadcast usage.

### File List

- `_bmad-output/implementation-artifacts/story-2.7-six-hour-broadcast-script.md`
- `scripts/run_6h_broadcast_digest.sh`
- `README.md`
