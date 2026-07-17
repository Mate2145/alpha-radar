---
baseline_commit: d60f617726c9998e1960c6d0ec125ec148f5604c
---

# Story 3.3: Detect Repeated Signals Across Sources

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a crypto alpha operator,
I want repeated token or project signals across multiple sources to be detected,
so that cross-source confirmation stands out in the digest.

## Acceptance Criteria

1. Given the same token or project appears in multiple messages inside a digest window, when repeated signal detection runs, then the system groups those mentions into a repeated signal candidate.
2. Given repeated mentions come from distinct sources, when the repeated signal is scored, then the system records the distinct source count and can rank the signal above equivalent single-source mentions.
3. Given duplicate or near-identical content is ingested more than once, when repeated signal detection runs, then duplicate content does not falsely inflate source spread or mention strength.
4. Given a repeated signal is detected, when digest context is prepared, then the system preserves representative evidence from source messages for auditability.

## Tasks / Subtasks

- [x] Add standalone repeated signal processing module (AC: 1, 2, 3, 4)
  - [x] Create `app/processing/repeated_signals.py`.
  - [x] Define a typed immutable result shape such as `RepeatedSignal`.
  - [x] Support `ticker` and `contract_address` signals only.
  - [x] Reuse existing normalization and audit conventions from `app/processing/signal_memory.py` where practical.
  - [x] Do not add DB tables, migrations, CLI commands, Codex calls, network integrations, schedulers, services, queues, or new dependencies.

- [x] Implement window-scoped repeated signal detection (AC: 1, 2)
  - [x] Query messages in `[window_start, window_end)` using SQLAlchemy and `selectinload(Message.source)` / `selectinload(Message.entities)`.
  - [x] Group by normalized `(signal_type, signal_key)`.
  - [x] Count mention strength by distinct non-duplicate message, not entity row count.
  - [x] Count source spread by distinct `source_id` after duplicate suppression.
  - [x] Include deterministic fields: `signal_type`, `signal_key`, `aliases`, `chain`, `window_start`, `window_end`, `mention_count`, `source_count`, `source_identifiers`, `source_message_ids`, `evidence`, `score`, and `labels`.
  - [x] Return only repeated candidates by default: at least two counted mentions or at least two distinct sources inside the window.

- [x] Suppress duplicate or near-identical content inflation (AC: 3)
  - [x] Treat exact duplicate `content_hash` values as one counted message for a signal.
  - [x] Add a small deterministic near-duplicate key based on normalized message content: lowercase, collapse whitespace, strip URLs, and strip repeated punctuation.
  - [x] Use the near-duplicate key only to avoid inflated counts; keep at least one representative audit message ID.
  - [x] Do not add fuzzy matching libraries or embedding/LLM similarity.

- [x] Preserve representative evidence for auditability (AC: 4)
  - [x] Use existing `db:{message.id}` audit IDs.
  - [x] Include concise evidence snippets from representative messages, capped to a small length such as 220 characters.
  - [x] Keep evidence ordering deterministic, preferably by score descending, then created_at descending, then id descending.
  - [x] Keep raw source traceability: source identifiers and message IDs must be enough to inspect the originating rows.

- [x] Add ranking logic (AC: 2)
  - [x] Implement a transparent deterministic score that favors cross-source spread before same-source repetition.
  - [x] Suggested formula: `score = source_count * 10 + mention_count`, with optional bounded source-quality contribution if already available on `Source.quality_score`.
  - [x] Sort output by `score desc`, `source_count desc`, `mention_count desc`, `signal_key asc`.
  - [x] Add labels compatible with downstream digest/grading usage: include `repeated` for `mention_count >= 2` and `cross-source` for `source_count >= 2`.

- [x] Add focused offline tests (AC: 1, 2, 3, 4)
  - [x] Test grouping same ticker across multiple messages.
  - [x] Test grouping same contract address, including EVM lowercase normalization and Solana casing preservation.
  - [x] Test distinct source counting and cross-source ranking.
  - [x] Test duplicate entity rows in one message do not inflate mention counts.
  - [x] Test exact duplicate `content_hash` does not inflate mention/source counts.
  - [x] Test near-identical content does not inflate mention/source counts.
  - [x] Test `db:{message.id}` IDs, source identifiers, aliases, labels, and evidence snippets.
  - [x] Test non-repeated single-source/single-message signals are omitted by default.

- [x] Run validation and update this story record (AC: 1, 2, 3, 4)
  - [x] Run `.venv/bin/pytest tests/test_repeated_signals.py`.
  - [x] Run `.venv/bin/pytest --cov=app --cov-report=term-missing`.
  - [x] Coverage must remain at or above 80%.
  - [x] Update Dev Agent Record, File List, Change Log, and move status to `review` only after tests pass.

## Dev Notes

### Epic 3 Dependency Direction

- Story 3.1 is the foundation for Epic 3. Repeated-signal detection exists primarily to enrich the Story 3.1 Codex grading input contract, not to create an independent digest-rendering path.
- Story 3.4 should render repeated/cross-source context through validated grading output when available. It should not treat `RepeatedSignal` as the primary digest presentation contract unless the grading output is absent and a deliberate fallback is implemented.
- The deterministic repeated-signal module remains useful as the local, testable source of repeated/cross-source labels, source spread, score, evidence, and audit message IDs that grading candidates can consume.

### Scope Boundaries

- This story creates a standalone repeated-signal detection layer only.
- Do not render repeated signals into digest Markdown; Story 3.4 owns digest presentation from validated grading output.
- Do not add a CLI inspection command; Story 3.5 owns local inspection commands.
- Do not modify Codex grading invocation unless a very small reuse point is needed and tests prove no regression.
- Do not use `keyword` entities as project identities. Current keyword extraction is topic-oriented and too broad for repeated token/project grouping.
- Do not add fuzzy matching, ML ranking, embeddings, LLM calls, external APIs, new config, or new dependencies.
- Preserve existing daily digest, window digest, export, send, broadcast, and `grade-signals` behavior.

### Current Codebase Facts

- DB models live in `app/db/models.py`.
- `EntityType` currently includes `ticker`, `url`, `keyword`, and `contract_address`.
- `Message` has `id`, `source_id`, `external_id`, `content`, `url`, `created_at`, `content_hash`, `score`, `source`, and `entities`.
- `Source` has `id`, `name`, `type`, `identifier`, `enabled`, and `quality_score`.
- `ExtractedEntity` stores `message_id`, `entity_type`, and `value`.
- Story 3.2 added `app/processing/signal_memory.py` with:
  - `SignalMemory`
  - `build_signal_memory_for_window(session, window_start, window_end)`
  - `signal_keys_for_message(message)`
  - `normalize_ticker(value)`
  - `normalize_contract(value)`
  - `chain_for_signal(signal_type, signal_key)`
  - `db_message_id(message)`
- Story 3.1 added `app/processing/signal_grading.py` with established conventions:
  - signal types are `ticker` and `contract_address`
  - chains are `evm`, `solana`, or `unknown`
  - audit IDs use `db:{message.id}`
  - raw message ordering commonly uses `score desc, created_at desc, id desc`
- Tests use pytest, in-memory SQLite, direct function calls, and no live network integrations.

### Implementation Guidance

- Preferred public API:
  - `build_repeated_signals(session, window_start: datetime, window_end: datetime, *, include_singletons: bool = False) -> list[RepeatedSignal]`
  - `detect_repeated_signals(messages: list[Message], window_start: datetime, window_end: datetime, *, include_singletons: bool = False) -> list[RepeatedSignal]`
- The SQL loader should be small and boring:
  - `select(Message)`
  - eager-load `source` and `entities`
  - filter `Message.created_at >= window_start` and `Message.created_at < window_end`
  - order by `Message.score.desc(), Message.created_at.desc(), Message.id.desc()`
- Reuse `signal_keys_for_message` from `signal_memory.py` to avoid a second normalization vocabulary.
- Count one message at most once per signal even if the message has duplicate entity rows.
- Duplicate suppression should happen per signal. Two messages with the same content but different signals should not suppress unrelated signals.
- For exact duplicates, prefer `content_hash`.
- For near duplicates, a reasonable helper is:
  - lowercase content
  - remove URLs with a regex
  - replace non-word runs with a single space
  - collapse whitespace
  - trim
- Evidence snippets should be plain text with collapsed whitespace and capped length. Do not include full raw messages.
- Aliases should carry observed entity values that differ from the normalized `signal_key`, sorted deterministically.
- For contract addresses, normalize EVM addresses to lowercase and preserve Solana casing, matching Story 3.2.
- Labels in this story should be local and deterministic: `repeated`, `cross-source`. Leave `new`, `heating up`, and `cooling down` to memory/grading/digest stories unless reuse is trivial and does not broaden scope.

### Project Structure Notes

- New module: `app/processing/repeated_signals.py`.
- New tests: `tests/test_repeated_signals.py`.
- Existing files should not need updates except possibly `app/processing/__init__.py` if the project already exports processing helpers there. Currently it is empty, so avoid changing it unless there is a concrete import need.
- Do not update README or `.env.example`; this story adds no operator command or configuration.

### Testing Requirements

- Tests must be deterministic and offline.
- Use the same in-memory SQLite pattern as `tests/test_signal_memory.py` and `tests/test_signal_grading.py`.
- Run targeted tests first, then full coverage:
  - `.venv/bin/pytest tests/test_repeated_signals.py`
  - `.venv/bin/pytest --cov=app --cov-report=term-missing`
- The full suite must remain green and coverage must stay at or above 80%.

### Previous Story Intelligence

- Story 3.2 is done and established the local signal memory layer. Reuse its normalization helpers rather than recreating ticker/contract key logic.
- Story 3.2 explicitly kept digest rendering, CLI inspection, and new persistence out of scope; keep the same boundary for this story.
- Story 3.1 is done and established the grading input contract. Future integration work should make 3.3 repeated/cross-source outputs feed that contract before they appear in digests.
- Recent review fixes in Story 3.1 tightened ambiguity handling and schema validation. Keep this story deterministic and explicit; avoid loose "best effort" grouping that cannot be tested.

### Git Intelligence

- Recent commits:
  - `d60f617 Sanitize local runtime paths`
  - `770f3e0 Story3.1:Improve signal and codex loop`
  - `92d341a V0.1.1`
  - `b474479 V0.1 Telegram message + sender`
- Current branch is `main` aligned with `origin/main` at baseline `d60f617`.
- Story 3.2 files are currently uncommitted in the working tree. Do not revert or overwrite them.

### References

- [Epic planning artifact](../planning-artifacts/epics.md)
- [Story 3.1 artifact](story-3.1-codex-cli-signal-grading-pipeline.md)
- [Story 3.2 artifact](story-3.2-track-signal-memory.md)
- [Signal memory module](../../app/processing/signal_memory.py)
- [Signal grading module](../../app/processing/signal_grading.py)
- [DB models](../../app/db/models.py)
- [Entity extraction](../../app/processing/extract_entities.py)
- [Signal memory tests](../../tests/test_signal_memory.py)
- [Signal grading tests](../../tests/test_signal_grading.py)

## Questions / Clarifications Saved For Later

- Should Story 3.4 consume `RepeatedSignal` directly in digest rendering, or should it first adapt repeated signals into the existing grading input shape?
- Should bounded `Source.quality_score` affect repeated-signal ranking in this story, or should source quality remain display/context only until digest rendering?
- Resolution direction as of 2026-07-16: Story 3.4 should consume validated Story 3.1 grading output first. Repeated-signal data should flow into grading candidates before digest rendering, with any direct `RepeatedSignal` rendering treated only as an explicit fallback.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_repeated_signals.py` - 9 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing` - 151 passed, 91% total coverage.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Implemented standalone repeated-signal detection in `app/processing/repeated_signals.py` with immutable `RepeatedSignal` results, SQLAlchemy window loading, normalized ticker/contract grouping, duplicate suppression, deterministic scoring, labels, and audit evidence.
- Added focused offline tests for ticker and contract grouping, EVM/Solana normalization, cross-source ranking, duplicate entity rows, exact and near duplicate suppression, audit fields, evidence snippets, labels, and singleton omission.
- Validation passed with targeted repeated-signal tests and full coverage regression; total coverage is 91%, above the 80% requirement.
- Fixed code-review finding: direct `detect_repeated_signals()` calls now enforce the same `[window_start, window_end)` boundary as `build_repeated_signals()`, with regression coverage for before-window and exclusive end-boundary messages.

### File List

- `_bmad-output/implementation-artifacts/story-3.3-detect-repeated-signals-across-sources.md`
- `app/processing/repeated_signals.py`
- `tests/test_repeated_signals.py`

## Change Log

- 2026-07-16: Created Story 3.3 as a standalone repeated-signal detection story and set status to ready-for-dev.
- 2026-07-16: Implemented repeated-signal detection, added offline tests, validated full suite, and moved story to review.
- 2026-07-16: Addressed review finding for direct detection window filtering and reran targeted/full validation.
- 2026-07-16: Clarified Epic 3 dependency direction: Story 3.3 repeated-signal output feeds the Story 3.1 grading contract, and Story 3.4 should render repeated/cross-source context through validated grading output.
