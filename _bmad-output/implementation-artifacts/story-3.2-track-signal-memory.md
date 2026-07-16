---
baseline_commit: d60f617726c9998e1960c6d0ec125ec148f5604c
---

# Story 3.2: Track Signal Memory Across Ingested Messages

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a crypto alpha operator,
I want the system to remember when tokens or projects were first and last seen,
so that I can tell whether a signal is new, repeated, or stale.

## Acceptance Criteria

1. Given ingested messages contain token or project entities, when signal memory is calculated, then the system records or derives first-seen time, latest-seen time, total mention count, and source spread for each signal.
2. Given a signal appears in multiple historical messages, when memory is inspected, then the system reports the earliest and latest observed message timestamps and includes enough source/message identifiers to audit the calculation.
3. Given no prior messages exist for a token or project, when it appears in the current digest window, then the signal can be classified as newly seen.
4. Given signal memory tests run locally, when test data is provided without live integrations, then first-seen, latest-seen, mention count, and source spread behavior can be verified deterministically.

## Tasks / Subtasks

- [x] Add signal memory processing module (AC: 1, 2, 3)
  - [x] Create `app/processing/signal_memory.py`.
  - [x] Define a typed immutable result shape such as `SignalMemory`.
  - [x] Reuse existing `Message`, `Source`, `ExtractedEntity`, and `EntityType` models.
  - [x] Support ticker and contract-address signals only for this story.
  - [x] Do not add a persistence table, migration, external service, scheduler, or CLI command.

- [x] Implement historical memory derivation (AC: 1, 2)
  - [x] Query stored messages and entities from SQLite using SQLAlchemy.
  - [x] Derive `signal_type`, `signal_key`, `aliases`, `chain`, `first_seen`, `latest_seen`, `mention_count`, `source_count`, and `source_message_ids`.
  - [x] Count mentions by distinct message per signal, not by duplicate entity rows.
  - [x] Count source spread by distinct `source_id`.
  - [x] Use stable audit IDs in the existing `db:{message.id}` format.

- [x] Implement window-aware classification helpers (AC: 2, 3)
  - [x] Add a helper to build memory for signals in a current window while including prior history before `window_start`.
  - [x] Classify current-window signals with labels that are deterministic and local: `new` when no prior matching signal exists, `repeated` when current-window mention count is at least two, and `cross-source` when current-window source count is at least two.
  - [x] Keep `heating up` and `cooling down` out of scope unless the implementation can reuse existing previous-window logic without broadening the story.

- [x] Add focused unit tests (AC: 1, 2, 3, 4)
  - [x] Test first-seen/latest-seen across historical messages.
  - [x] Test mention count dedupes duplicate entity rows in one message.
  - [x] Test source spread counts distinct sources.
  - [x] Test `db:{message.id}` audit identifiers.
  - [x] Test current-window `new`, `repeated`, and `cross-source` labels without live integrations.
  - [x] Test ticker and contract-address memory, including EVM/Solana chain classification through existing helpers.

- [x] Run validation and update this story record (AC: 4)
  - [x] Run targeted new tests.
  - [x] Run `pytest --cov=app --cov-report=term-missing`.
  - [x] Update Dev Agent Record, File List, Change Log, and set Status to `review` only after tests pass.

## Dev Notes

### Scope Boundaries

- This story creates the deterministic memory calculation layer only.
- Do not add CLI inspection; Story 3.5 owns local inspection commands.
- Do not render digest labels; Story 3.4 owns digest rendering.
- Do not add source-quality YAML or trusted-source tiers.
- Do not call Telegram, Discord, RSS, OpenAI, OpenRouter, Codex CLI, or any networked integration.
- Do not run `codex` CLI commands in this repository.
- Do not add new dependencies.

### Current Codebase Facts

- DB models live in `app/db/models.py`.
- `EntityType` currently includes `ticker`, `url`, `keyword`, and `contract_address`.
- `Message` has `id`, `source_id`, `content`, `created_at`, `content_hash`, `score`, `source`, and `entities`.
- `ExtractedEntity` stores `message_id`, `entity_type`, and `value`.
- `Source` has `id`, `name`, `type`, `identifier`, and `quality_score`.
- Entity extraction lives in `app/processing/extract_entities.py`; contract-address chain detection already exists indirectly through `app/processing/signal_grading.py::chain_for_contract`.
- Story 3.1 introduced `app/processing/signal_grading.py` with useful conventions: `db:{message.id}` audit IDs, ticker and contract-address signal types, `evm`/`solana`/`unknown` chains, and local deterministic candidate building.
- Tests use `pytest`, in-memory SQLite, SQLAlchemy sessions, and direct function calls.

### Implementation Guidance

- Prefer a small pure processing module under `app/processing`.
- Use `selectinload(Message.source)` and `selectinload(Message.entities)` when loading messages for memory calculation.
- Normalize ticker keys to uppercase `$TICKER`.
- Normalize EVM contract addresses to lowercase. Preserve Solana address casing.
- Ignore `keyword` entities for this story; the epic says token or project entities, but current project-name extraction is not reliable enough to treat keywords as project identities.
- Keep output deterministic by sorting memory records by `signal_type` and `signal_key`, and sorting message IDs by message time then ID.
- A reasonable public API:
  - `build_signal_memory(session, *, before: datetime | None = None) -> list[SignalMemory]`
  - `build_signal_memory_for_window(session, window_start: datetime, window_end: datetime) -> list[SignalMemory]`
  - `labels_for_window_memory(memory: SignalMemory) -> list[str]`
- `build_signal_memory_for_window` should return records for signals that appear in the current window, enriched with prior history before `window_start`.
- If a signal appears before the window and inside the window, `first_seen` should be the historical first seen, while current-window labels should be based on current-window counts/source spread.

### Project Structure Notes

- New module: `app/processing/signal_memory.py`.
- New tests: `tests/test_signal_memory.py`.
- Existing files should only be touched if needed for reuse or exports; avoid changes to CLI, digest rendering, database schema, or ingestion.

### Testing Requirements

- Run targeted tests for `tests/test_signal_memory.py`.
- Run full suite with coverage: `pytest --cov=app --cov-report=term-missing`.
- Coverage must remain at or above 80%.
- All tests must be offline and deterministic.

### Previous Story Intelligence

- Story 3.1 is currently in `review` and established the signal-grading input contract.
- Reuse the same audit identifier convention (`db:{message.id}`) and allowed signal types (`ticker`, `contract_address`) to avoid two incompatible signal vocabularies.
- Do not duplicate large parts of `signal_grading.py`; factor only if a small shared helper is clearly worth it. A small local chain classifier is acceptable if it keeps this story isolated.
- Existing grading tests show the preferred pattern for adding in-memory SQLite fixtures and helper `add_message` functions.

### References

- [Epic planning artifact](../planning-artifacts/epics.md)
- [Story 3.1 artifact](story-3.1-codex-cli-signal-grading-pipeline.md)
- [DB models](../../app/db/models.py)
- [Entity extraction](../../app/processing/extract_entities.py)
- [Signal grading patterns](../../app/processing/signal_grading.py)
- [Signal grading tests](../../tests/test_signal_grading.py)
- [Project config](../../app/config.py)

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_signal_memory.py`: passed, 5 tests.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: passed, 142 tests, 90% total coverage.
- Code-review follow-up: `.venv/bin/pytest tests/test_signal_memory.py`: passed, 5 tests.
- Code-review follow-up: `.venv/bin/pytest --cov=app --cov-report=term-missing`: passed, 142 tests, 90% total coverage.

### Completion Notes List

- Added a pure SQLite-derived signal memory module for ticker and contract-address signals.
- Implemented deterministic normalization, source/message aggregation, `db:{message.id}` audit IDs, and current-window labels.
- Kept the story scope module-only: no CLI, schema, ingestion, rendering, network, or dependency changes.
- Addressed code-review findings by deriving aliases, exposing contributing source IDs/identifiers, removing `__dict__` dataclass reconstruction, and renaming the per-message signal-key variable.

### File List

- `_bmad-output/implementation-artifacts/story-3.2-track-signal-memory.md`
- `app/processing/signal_memory.py`
- `tests/test_signal_memory.py`

### Change Log

- 2026-07-14: Created Story 3.2 artifact, implemented signal memory processing, added tests, and moved story to review after passing validation.
- 2026-07-14: Addressed code-review findings for explicit dataclass construction, alias derivation, and source auditability.
- 2026-07-16: Marked story done after review and full-suite validation passed.
