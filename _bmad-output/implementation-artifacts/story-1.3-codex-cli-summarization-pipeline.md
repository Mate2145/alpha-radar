# Story 1.3: Use Codex CLI for AI-Written Daily Digest Summaries

Status: implemented

## Story

As a crypto alpha operator,
I want the digest builder to use my local Codex CLI subscription session,
so that the final Telegram summary is AI-written without requiring OpenAI API billing.

## Acceptance Criteria

1. Given Codex CLI is installed and authenticated, when I set `LLM_PROVIDER=codex_cli` and run `alpha build-digest --date YYYY-MM-DD`, then the digest builder sends the selected daily messages to `codex exec` and stores the AI-written Markdown summary in `daily_summaries`.
2. Given Codex CLI is missing, not authenticated, times out, or returns no content, when I run the configured summarization pipeline, then the failure is reported clearly enough to fix login/configuration without silently sending a fallback summary.
3. Given I want to verify setup before a full digest run, when I run a local LLM check command, then the app validates the configured provider and prints a concise success or actionable failure.
4. Given a digest is built through Codex CLI, when I inspect the stored summary or exported Markdown, then the summary identifies the model/provider as `codex-cli:*` and remains compatible with the existing `send-digest` command.

## Tasks / Subtasks

- [x] Add provider verification command. (AC: 2, 3)
  - [x] Add CLI command to check the currently configured LLM provider.
  - [x] For `codex_cli`, run a tiny `codex exec` prompt through the same adapter.
  - [x] Print a clean success/failure message without stack traces.
- [x] Harden Codex CLI adapter behavior. (AC: 1, 2, 4)
  - [x] Keep the current `codex exec --ephemeral` path.
  - [x] Preserve stdin prompt passing for daily messages.
  - [x] Surface command failures, timeouts, missing command, and empty output clearly.
  - [x] Keep provider/model labeling as `codex-cli:<model-or-default>`.
- [x] Add digest export convenience. (AC: 4)
  - [x] Add a CLI command to export a stored daily digest to Markdown.
  - [x] Default output to `data/digest-YYYY-MM-DD.md`.
  - [x] Do not change `send-digest` behavior.
- [x] Update setup docs. (AC: 1, 2, 3)
  - [x] Document `codex login`.
  - [x] Document `.env` values for `LLM_PROVIDER=codex_cli`.
  - [x] Document check/build/export/send sequence.
- [x] Add tests. (AC: 2, 3, 4)
  - [x] Unit test provider check success/failure behavior with mocked adapter.
  - [x] Unit test Codex timeout/missing command/empty output handling.
  - [x] Unit test digest export writes expected Markdown.

## Dev Notes

- Existing Codex CLI adapter lives in [app/summarization/llm_client.py](/mnt/h/Dev/alpha-radar/app/summarization/llm_client.py).
- Existing digest build command already stores `DailySummary` rows.
- Existing send command reads `DailySummary.content`, so Codex summaries should flow to Telegram without delivery changes.
- Official Codex CLI auth path is `codex login`; `codex exec` reuses saved CLI authentication.
- Keep tests mocked; do not require live Codex login in automated tests.

### Project Structure Notes

- Keep changes inside `app/summarization`, `app/cli.py`, docs/env, and tests unless needed.
- Do not add a service, queue, web UI, or long-running worker for this story.

### References

- [epics.md](/mnt/h/Dev/alpha-radar/_bmad-output/planning-artifacts/epics.md)
- [llm_client.py](/mnt/h/Dev/alpha-radar/app/summarization/llm_client.py)
- [digest_builder.py](/mnt/h/Dev/alpha-radar/app/summarization/digest_builder.py)
- [cli.py](/mnt/h/Dev/alpha-radar/app/cli.py)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `pytest -q`: pending local environment with dev dependencies installed.

### Completion Notes List

- Added LLM provider health check command.
- Hardened Codex CLI adapter failure reporting.
- Added digest export command and documentation.

### File List

- `README.md`
- `.env.example`
- `app/cli.py`
- `app/config.py`
- `app/summarization/llm_client.py`
- `tests/test_cli_commands.py`
- `tests/test_llm_client.py`
