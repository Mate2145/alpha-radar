---
baseline_commit: 1a93b7045a34165ae3dd01ee861aab58b1cfa41b
---

# Story 3.1: Codex CLI Signal Grading Pipeline

Status: review

## Story

As a crypto alpha operator,
I want a separate CLI command that prepares signal grading input files, asks Codex CLI for structured JSON grades, and validates the result,
so that I can iterate on AI-assisted signal grading without destabilizing digest generation.

## Acceptance Criteria

1. Given a time window is requested with `--since-hours` or explicit `--from/--to`, when `alpha grade-signals` runs, then it resolves the same window semantics as `build-window-digest` and creates audit files under `data/signal-grading/input/`.
2. Given ingested messages exist in the grading window, when grading input is generated, then the input JSON contains `schema_version`, `task`, `window`, `signals`, and up to 80 `raw_messages` with stable `db:{message.id}` IDs.
3. Given candidate signals are prepared, when the input JSON is written, then signal candidates include ticker-based signals and contract-address signals where extracted, with aliases, chain, labels, first/latest seen, mention count, source count, VIP source count, and source message IDs where available.
4. Given the input JSON has been written, when validation runs before Codex invocation, then invalid input fails the command before calling Codex and reports a clear validation error.
5. Given valid input exists, when Codex CLI grading is invoked, then the prompt instructs Codex to read the input file path and write output JSON to the requested output file path.
6. Given Codex writes valid grading JSON, when output validation passes, then the command writes `data/signal-grading/output/<window>.json`, updates `data/signal-grading/output/latest.json`, and reports the output path.
7. Given Codex writes invalid grading JSON or the output file is missing, when output validation runs, then the command fails with a non-zero Typer error, preserves the previous valid `output/latest.json`, and saves or moves the bad output under `data/signal-grading/invalid/`.
8. Given grading fails, when digest commands are run separately, then existing `build-digest`, `build-window-digest`, export, and send flows remain unchanged and do not depend on grading output.
9. Given tests run locally, when Codex behavior is exercised, then subprocess/Codex calls are mocked and no real `codex` command or networked integration is required.

## Tasks / Subtasks

- [x] Add signal grading domain module (AC: 1, 2, 3, 4, 6, 7)
  - [x] Create a focused module such as `app/processing/signal_grading.py` or `app/grading/signal_grading.py`.
  - [x] Reuse existing SQLAlchemy `Message`, `Source`, and `ExtractedEntity` data; do not add a grade persistence table in this story.
  - [x] Select raw messages from the requested window, capped at 80 messages, using deterministic ordering. Prefer `score desc, created_at desc, id desc` unless implementation discovers a better existing pattern.
  - [x] Build signal candidates from extracted ticker entities and contract address entities where present.
  - [x] Use `db:{message.id}` for all source message IDs.
  - [x] Limit candidates to 30 initially.
  - [x] Truncate raw message content before writing JSON, using 1000 characters as the initial cap.

- [x] Add contract address extraction support needed by grading input (AC: 3)
  - [x] Extend `EntityType` with `contract_address`.
  - [x] Add EVM address extraction: `0x` plus 40 hex characters.
  - [x] Add Solana address extraction using conservative base58-like matching for roughly 32-44 characters, excluding ambiguous characters.
  - [x] Keep keywords as context only; do not make keywords primary signal candidates for grading.
  - [x] Add tests for EVM, Solana, duplicate contract dedupe, and non-address false positives.

- [x] Implement ticker/contract pairing for candidate construction (AC: 3)
  - [x] If a ticker and contract address occur near each other in the same message, use the contract address as the primary signal key and the ticker as an alias.
  - [x] Default pairing distance is 120 characters.
  - [x] Add a settings value such as `signal_pairing_max_distance: int = 120` sourced from `SIGNAL_PAIRING_MAX_DISTANCE`.
  - [x] If pairing is ambiguous or too distant, keep ticker and contract as separate signal candidates.

- [x] Add file-based grading IO (AC: 1, 2, 4, 6, 7)
  - [x] Write input files to `data/signal-grading/input/<window>.json` and `data/signal-grading/input/latest.json`.
  - [x] Write valid output files to `data/signal-grading/output/<window>.json` and `data/signal-grading/output/latest.json`.
  - [x] Save invalid output to `data/signal-grading/invalid/<window>.invalid.json`.
  - [x] Use a stable window filename format: `YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json`.
  - [x] Create directories as needed.

- [x] Implement input and output schema validation (AC: 4, 6, 7)
  - [x] Use stdlib validation or an existing direct dependency; do not add `jsonschema` unless there is a concrete reason.
  - [x] Input schema must require: `schema_version`, `task`, `window.start`, `window.end`, `signals`, and `raw_messages`.
  - [x] Output schema must require: `schema_version`, `window.start`, `window.end`, and `grades`.
  - [x] Each grade must validate `signal_type`, `signal_key`, `aliases`, `chain`, `source_message_ids`, `grade`, `confidence`, `priority`, `summary`, `reasoning`, `risk_flags`, and `recommended_action`.
  - [x] Enforce allowed values from `docs/epic-3-grading-decisions.md`.
  - [x] Enforce `confidence` between `0.0` and `1.0`.

- [x] Add Codex CLI grading invocation (AC: 5, 7, 9)
  - [x] Reuse the existing Codex CLI subprocess pattern in `app/summarization/llm_client.py` where practical.
  - [x] Prefer `gpt-5.4-mini` for grading runs when available via local Codex CLI, using `CODEX_MODEL` rather than hard-coding the model.
  - [x] Do not run real Codex in tests.
  - [x] The prompt must tell Codex to read the input JSON file and write valid grading JSON to the exact output path.
  - [x] Treat missing output file, empty output, non-zero Codex exit, timeout, and invalid JSON as clear command failures.
  - [x] Do not replace the last valid `output/latest.json` when validation fails.

- [x] Add CLI command (AC: 1, 5, 6, 7, 8)
  - [x] Add `alpha grade-signals`.
  - [x] Support `--since-hours`, `--from`, and `--to` with the same validation semantics as `build-window-digest`.
  - [x] Call `init_db()` and read from the configured database.
  - [x] Echo concise success output showing input and output file paths.
  - [x] Raise `typer.BadParameter` or a similarly consistent Typer error for validation and Codex failures.

- [x] Add tests and documentation (AC: 1-9)
  - [x] Add unit tests for contract extraction and pairing.
  - [x] Add unit tests for input generation and schema validation.
  - [x] Add unit tests for valid output acceptance and invalid output preservation behavior.
  - [x] Add CLI tests for successful `grade-signals`, invalid input/output, and Codex failure paths with mocked invocation.
  - [x] Update README with the `alpha grade-signals --since-hours 6` flow and file locations.
  - [x] Update `.env.example` if `SIGNAL_PAIRING_MAX_DISTANCE` or another new environment setting is added.

## Dev Notes

### Scope Boundaries

- This story creates the file-based grading loop only. Do not persist grades to DB yet.
- Do not add market cap, price, liquidity, or price-change lookup in this story.
- Do not add fuzzy dedupe.
- Do not add services, schedulers, queues, agents, orchestration layers, or frontend surfaces.
- Existing digest build/export/send commands must remain usable without grading.
- Do not run `codex` CLI commands manually from the agent workflow. Implementation tests must mock subprocess behavior.

### Current Codebase Facts

- CLI commands live in `app/cli.py` and use Typer. Existing window parsing helpers are `resolve_digest_window`, `parse_window_datetime`, and `resolve_optional_window_bounds`.
- Codex CLI support already exists in `app/summarization/llm_client.py` through `LLMClient._complete_codex_cli`, using `codex exec --ephemeral` and settings `CODEX_COMMAND`, `CODEX_MODEL`, and `CODEX_TIMEOUT_SECONDS`.
- Preferred grading model is `gpt-5.4-mini` when available. Keep this configurable through `CODEX_MODEL`; if the local Codex CLI rejects the configured model, surface the normal Codex failure clearly.
- DB models live in `app/db/models.py`. `Source` already has `quality_score`. `Message` has `source_id`, `external_id`, `content`, `url`, `created_at`, `content_hash`, and `score`. `ExtractedEntity` stores `entity_type` and `value`.
- Current entity extraction lives in `app/processing/extract_entities.py`. It currently extracts URLs, `$TICKER` values, and crypto keywords.
- Current cross-source scoring exists in `app/processing/score_messages.py`. Do not replace it in this story.
- Fallback digest rendering in `app/summarization/digest_builder.py` already has repeated entity helpers and message locator patterns. Reuse concepts where useful, but grading JSON should use `db:{message.id}` for machine references.
- Tests use `pytest`, in-memory SQLite sessions where needed, `monkeypatch`, and direct command function calls rather than shelling out.

### Grading Input Contract

Write input JSON like:

```json
{
  "schema_version": "1.0",
  "task": "grade_crypto_signals",
  "window": {
    "start": "2026-07-10T12:00:00",
    "end": "2026-07-10T18:00:00"
  },
  "signals": [
    {
      "signal_type": "contract_address",
      "signal_key": "0x1234567890abcdef1234567890abcdef12345678",
      "aliases": ["$ABC"],
      "chain": "evm",
      "labels": ["new", "repeated", "cross-source"],
      "first_seen": "2026-07-10T12:15:00",
      "latest_seen": "2026-07-10T17:45:00",
      "mention_count": 4,
      "source_count": 2,
      "vip_source_count": 0,
      "source_message_ids": ["db:123", "db:124"]
    }
  ],
  "raw_messages": [
    {
      "id": "db:123",
      "created_at": "2026-07-10T12:15:00",
      "source": "@alpha",
      "source_tier": "default",
      "score": 7.5,
      "content": "Buying $ABC CA: 0x123..."
    }
  ]
}
```

For this story, `vip_source_count` and `source_tier` may use neutral/default values if trusted source YAML is not implemented yet. If trusted source config is implemented in this story, keep it small and file-based as described in `docs/epic-3-grading-decisions.md`.

### Grading Output Contract

Valid Codex output JSON:

```json
{
  "schema_version": "1.0",
  "window": {
    "start": "2026-07-10T12:00:00",
    "end": "2026-07-10T18:00:00"
  },
  "grades": [
    {
      "signal_type": "contract_address",
      "signal_key": "0x1234567890abcdef1234567890abcdef12345678",
      "aliases": ["$ABC"],
      "chain": "evm",
      "source_message_ids": ["db:123"],
      "grade": "A",
      "confidence": 0.86,
      "priority": "high",
      "summary": "Repeated VIP-source mention with contract evidence.",
      "reasoning": ["Ticker and contract appeared close together."],
      "risk_flags": [],
      "recommended_action": "review"
    }
  ]
}
```

Allowed values:

- `signal_type`: `ticker`, `contract_address`
- `chain`: `evm`, `solana`, `unknown`
- `grade`: `A`, `B`, `C`, `D`, `ignore`
- `priority`: `high`, `medium`, `low`, `ignore`
- `recommended_action`: `review`, `watch`, `ignore`

### File Layout

Use:

```text
data/signal-grading/
  input/
    latest.json
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json
  output/
    latest.json
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json
  invalid/
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.invalid.json
```

### Project Structure Notes

- Prefer small modules under existing boundaries. `app/processing` is appropriate for entity extraction, candidate construction, and derived memory. A small `app/grading` package is also acceptable if it keeps Codex grading IO isolated.
- Keep external integration behavior behind a small adapter. Codex invocation should be mockable by tests.
- Avoid circular imports from `app/cli.py` into processing modules.
- Use typed Python and small functions.

### Testing Requirements

- Run `pytest --cov=app --cov-report=term-missing`.
- Coverage must remain at or above 80%.
- Network and Codex calls must be mocked.
- Add tests for:
  - window resolution for `grade-signals`;
  - generated input file paths and `latest.json`;
  - schema validation failures;
  - valid output updating `output/latest.json`;
  - invalid output going to `invalid/` while preserving prior latest output;
  - contract address extraction and ticker/contract pairing;
  - no regression to existing digest CLI behavior.

### References

- [Epic 3 decisions](../../docs/epic-3-grading-decisions.md)
- [Epic planning artifact](../planning-artifacts/epics.md)
- [CLI patterns](../../app/cli.py)
- [Codex CLI provider pattern](../../app/summarization/llm_client.py)
- [DB models](../../app/db/models.py)
- [Entity extraction](../../app/processing/extract_entities.py)
- [Scoring logic](../../app/processing/score_messages.py)
- [Digest builder](../../app/summarization/digest_builder.py)
- [Project config](../../app/config.py)
- [Dependency list](../../pyproject.toml)

## Questions / Clarifications Saved For Later

- Should raw messages be selected strictly by score, strictly by newest, or by a blended rank? This story recommends deterministic `score desc, created_at desc, id desc` for v1.
- Should trusted source YAML be implemented in this same story or split into the next story? This story allows neutral defaults if YAML would make scope too large.
- Should `grade-signals` expose a separate `--validate-output` helper command later? Not required for v1.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Story validation reviewed against `docs/epic-3-grading-decisions.md`, existing CLI/Codex patterns, and create-story checklist themes.
- No sprint status file exists at `_bmad-output/implementation-artifacts/sprint-status.yaml`; no sprint status update was possible.
- `.venv/bin/pytest tests/test_extract_entities.py tests/test_signal_grading.py`: passed after implementation.
- `.venv/bin/pytest tests/test_cli_commands.py -k grade_signals`: passed.
- `.venv/bin/pytest tests/test_extract_entities.py tests/test_signal_grading.py tests/test_cli_commands.py`: 73 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 128 passed, total coverage 89%.
- Post-review `.venv/bin/pytest tests/test_signal_grading.py`: 16 passed.
- Post-review `.venv/bin/pytest --cov=app --cov-report=term-missing`: 137 passed, total coverage 90%.

### Completion Notes List

- Added contract address entity extraction for EVM and Solana-style addresses.
- Added file-based signal grading input/output workflow under `data/signal-grading/`.
- Added schema validation for grading input and Codex grading output without adding new dependencies.
- Added `alpha grade-signals` with window semantics matching `build-window-digest`.
- Preserved digest flows as independent from grading output.
- Documented grading command, model preference, and `SIGNAL_PAIRING_MAX_DISTANCE`.
- Addressed gpt-5.4 review findings: enforced Codex-only provider for grading, removed stale window output before each Codex run, rejected empty runner output, tightened input/output schema validation, added previous-window labels, and prevented ambiguous one-ticker/two-contract alias pairing.

### File List

- `.env.example`
- `README.md`
- `_bmad-output/implementation-artifacts/story-3.1-codex-cli-signal-grading-pipeline.md`
- `app/cli.py`
- `app/config.py`
- `app/db/models.py`
- `app/processing/extract_entities.py`
- `app/processing/signal_grading.py`
- `tests/test_cli_commands.py`
- `tests/test_extract_entities.py`
- `tests/test_signal_grading.py`

## Change Log

- 2026-07-10: Implemented Codex CLI signal grading pipeline story and moved status to review.
