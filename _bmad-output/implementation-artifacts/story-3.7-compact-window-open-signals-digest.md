---
baseline_commit: 70fe39ec06e1eaef072e8bfedff7b74e3b33a4ad
---

# Story 3.7: Compact Window Open Signals Digest

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a crypto alpha operator,
I want time-window digests to render as a short open-signals sheet,
so that I can scan the most actionable graded signals quickly without reading a long report.

## Acceptance Criteria

1. Given a window digest is built, when the Markdown is rendered, then the window digest uses only these sections in this order: `Open Signals` and `Raw High-Score Messages`.
2. Given a daily digest is built, when the Markdown is rendered, then the existing longer daily digest contract remains unchanged.
3. Given matching validated schema `1.1` grading output exists for the window, when the window digest is rendered, then `Open Signals` shows at most 8 graded signals sorted by priority, grade, confidence descending, then signal key.
4. Given a graded signal is rendered in `Open Signals`, when it has recommendation, grade, priority, confidence, summary, labels, and risk flags, then the bullet includes direction emoji, action label, grade metadata, concise summary, mapped labels, and risk flags.
5. Given labels are present, when they are rendered, then label emojis are mapped as: `new` -> `🆕`, `repeated` -> `🔁`, `heating up` -> `🔥`, `cooling down` -> `🧊`, and `cross-source` -> `🔗`.
6. Given risk flags are present, when they are rendered, then they appear inline after `⚠️` as short comma-separated text.
7. Given a graded signal has `recommended_action=review` or grade `A`/`B` with high or medium priority, when it is rendered, then it uses `🟢 LONG/WATCH`.
8. Given a graded signal has `recommended_action=watch` or grade `C`, when it is rendered, then it uses `🟡 WATCH`.
9. Given a graded signal has `recommended_action=ignore`, grade `D`, grade `ignore`, or clearly negative fallback sentiment, when it is rendered, then it uses `🔴 SELL/IGNORE`.
10. Given no matching grading output exists, when a window digest is rendered, then the compact format still renders without failing and uses existing deterministic position extraction as fallback for `Open Signals`.
11. Given raw high-score messages are rendered in a window digest, when there are more than the display cap, then only the top 5-8 messages are shown as one-line bullets in the format `- @Source: short message`.
12. Given a configured LLM provider is used for window digests, when the digest is generated, then the final Markdown still satisfies the compact window contract and cannot reintroduce the removed long sections.
13. Given tests run locally, when this story is complete, then focused digest tests and full coverage pass with no network or Codex CLI calls.

## Tasks / Subtasks

- [x] Split daily and window rendering contracts (AC: 1, 2, 12)
  - [x] Keep `REQUIRED_DIGEST_HEADINGS` and `render_digest()` behavior for daily digests unless a narrower helper split is needed.
  - [x] Add a window-specific rendering path from `build_window_digest()` rather than changing `build_digest()` output.
  - [x] Add a window-specific contract validator for exactly `## Open Signals` and `## Raw High-Score Messages`.

- [x] Implement compact `Open Signals` rendering (AC: 3-10)
  - [x] Reuse validated grading output loaded by `load_matching_grading_output()`.
  - [x] Reuse existing `grade_sort_key()` ordering, but cap rendered window signals at 8.
  - [x] Add a compact renderer for graded signals with this shape:
    `- 🟢 $INJ — LONG/WATCH — Grade B / high / 0.82 — Robinhood spot listing claim. Flags: 🆕, ⚠️ single-source, listing-catalyst.`
  - [x] Use emoji label mapping exactly as listed in the acceptance criteria.
  - [x] Keep risk flags plain and comma-separated after `⚠️`.
  - [x] Add action/color mapping from `recommended_action`, grade, and priority as described in acceptance criteria.
  - [x] When grading is absent, fall back to deterministic position extraction and render no more than 8 concise open-signal bullets.

- [x] Compress raw high-score message output for window digests only (AC: 1, 11)
  - [x] Add a compact raw-message renderer that uses source handle/name plus a short content snippet.
  - [x] Cap compact raw messages to 5-8 messages; prefer 8 unless tests or message length show it is still noisy.
  - [x] Do not include score, external ID, or full URL in compact raw output.
  - [x] Preserve the longer raw audit output for daily digests and any existing non-window fallback helpers.

- [x] Preserve exact-window grading behavior and logging (AC: 3, 10, 13)
  - [x] Do not change grading file paths or exact window matching.
  - [x] Keep current logging that says whether graded output was used.
  - [x] Do not make window digest generation require `grade-signals` success.

- [x] Add focused tests (AC: 1-13)
  - [x] Test window digest headings are exactly `Open Signals` and `Raw High-Score Messages`.
  - [x] Test daily digest/fallback long contract still includes existing formal sections.
  - [x] Test graded compact signal output includes direction emoji, action label, grade, priority, confidence, summary, label emojis, and risk flags.
  - [x] Test only top 8 graded signals render.
  - [x] Test raw high-score messages are compact one-line bullets and capped.
  - [x] Test no removed long sections appear in window digest output.
  - [x] Test missing grading output still produces compact window output.
  - [x] Test configured LLM window path cannot return the old long section contract.

- [x] Run validation (AC: 13)
  - [x] Run `.venv/bin/pytest tests/test_digest_builder.py`.
  - [x] Run `.venv/bin/pytest tests/test_cli_commands.py` if CLI behavior is touched.
  - [x] Run `.venv/bin/pytest --cov=app --cov-report=term-missing`.
  - [x] Confirm coverage remains at or above 80%.

## Dev Notes

### Current State

- `build_digest()` and `build_window_digest()` both live in `app/summarization/digest_builder.py`.
- `build_digest()` currently loads daily messages, optionally loads matching daily-window grading output, and calls `render_digest()`.
- `build_window_digest()` currently loads window messages, optionally loads exact-window grading output, and also calls `render_digest()`.
- `render_digest()` currently supports both fallback and configured LLM rendering with the long formal digest contract.
- `REQUIRED_DIGEST_HEADINGS` currently requires the long section order:
  `Executive Summary`, `Top Narratives`, `Most Mentioned Tokens / Projects`, `Repeated Signals Across Sources`, `Open Positions`, `Links Worth Reviewing`, `Raw High-Score Messages`.
- Story 3.6 added deterministic injection of visible grading metadata into `Repeated Signals Across Sources` for LLM-backed long digests.
- Current window output is too verbose for the operator workflow. The new compact contract is window-only.

### Required Design Direction

- Add a window-specific renderer instead of shrinking the shared daily renderer.
- Daily digest remains the formal long report.
- Window digest becomes the short operator sheet:

```markdown
# Crypto Alpha Digest - {window}

## Open Signals

- 🟢 $INJ — LONG/WATCH — Grade B / high / 0.82 — Robinhood spot listing claim. Flags: 🆕, ⚠️ single-source, listing-catalyst.

## Raw High-Score Messages

- @ProfitsPlays: $INJ live on Robinhood spot
```

### Emoji and Direction Rules

- Label emojis:
  - `new` -> `🆕`
  - `repeated` -> `🔁`
  - `heating up` -> `🔥`
  - `cooling down` -> `🧊`
  - `cross-source` -> `🔗`
- Risk flags render after `⚠️` as plain comma-separated text.
- Direction/action:
  - `🟢 LONG/WATCH` for `recommended_action=review`, or grade `A`/`B` with high/medium priority.
  - `🟡 WATCH` for `recommended_action=watch`, or grade `C`.
  - `🔴 SELL/IGNORE` for `recommended_action=ignore`, grade `D`, grade `ignore`, or clearly negative fallback sentiment.

### Scope Boundaries

- Do not change ingestion, scoring, grading, or database schema.
- Do not add services, queues, schedulers, agents, frontend work, or new dependencies.
- Do not alter exact-window grading file matching.
- Do not remove raw high-score messages yet; compress them for window digests only.
- Do not change daily digest sections in this story.
- Do not invoke Codex CLI in tests.

### Implementation Guardrails

- Prefer small pure helper functions in `app/summarization/digest_builder.py`:
  - `render_window_digest(...)`
  - `validate_window_digest_contract(...)`
  - `compact_open_signals(...)`
  - `render_compact_graded_signal(...)`
  - `compact_raw_message_section(...)`
- Reuse existing helpers where sensible:
  - `load_matching_grading_output()`
  - `grade_sort_key()`
  - `collect_position_signals()`
  - `message_locator()` only if needed for fallback, not for compact raw lines.
- Keep deterministic output ordering. The top 8 limit must apply after sorting.
- Keep text short enough for Telegram/Discord scanning. One bullet should be one line in normal cases.
- Since this story explicitly requires emoji, Unicode output is acceptable in renderer and tests despite the repo's default ASCII preference.

### Testing Requirements

- Tests must be offline and deterministic.
- Use temp grading JSON files and in-memory SQLite sessions as current digest tests do.
- Mock `LLMClient` for configured LLM paths; never call live Codex CLI.
- Existing tests in `tests/test_digest_builder.py` assert the current long fallback contract. Update or split tests so daily/long behavior remains covered and window compact behavior is covered.
- If `build_window_digest()` behavior changes but CLI signatures do not, CLI tests may only need updates where they assert section names or exported content.
- Run full coverage before marking implementation complete.

### Previous Story Intelligence

- Story 3.4 established grading output schema `1.1` as the digest-enrichment contract and treats absent/stale/invalid grading as non-fatal fallback.
- Story 3.5 added useful logs for grading lookup; preserve those logs.
- Story 3.6 made grade metadata visible in final Markdown because LLM output could paraphrase it away. This story should apply the same principle to compact window output: do not rely on LLM prose alone for grade visibility.
- Current tests already include `_grading_payload(...)` fixtures and exact-window grading output coverage in `tests/test_digest_builder.py`; extend those patterns instead of introducing new fixtures unnecessarily.

### Git Intelligence

- Recent commits show the repo has been evolving through story-scoped changes: `Story 3.3`, `Story3.1:Improve signal and codex loop`, and runtime-path sanitation.
- Keep this story similarly scoped to summarization rendering and tests.

### No External Research Required

- This story uses existing Python, SQLAlchemy, Typer CLI, pytest, and local Markdown rendering. No new library or external API knowledge is needed.

### References

- [Epic planning artifact](../planning-artifacts/epics.md)
- [Story 2.2 operator-readable digest format](story-2.2-operator-readable-digest-format.md)
- [Story 2.3 position signals](story-2.3-position-signals.md)
- [Story 3.4 graded signal digest context](story-3.4-render-codex-graded-signal-context-in-digests.md)
- [Story 3.5 grading context logging](story-3.5-log-graded-window-digest-context.md)
- [Story 3.6 visible grade metadata](story-3.6-make-grades-visible-in-digest.md)
- [Digest builder](../../app/summarization/digest_builder.py)
- [Digest tests](../../tests/test_digest_builder.py)
- [CLI commands](../../app/cli.py)

## Questions / Clarifications Saved For Later

- Should the compact raw-message cap be exactly 8, or should it be configurable later? This story recommends hard-coded 8 for now.
- Should compact window digest eventually remove `Raw High-Score Messages` entirely once there is a better audit/debug path? This remains future scope.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-07-17: `.venv/bin/pytest tests/test_digest_builder.py` passed, 36 tests.
- 2026-07-17: `.venv/bin/pytest tests/test_cli_commands.py` passed, 49 tests.
- 2026-07-17: `.venv/bin/pytest --cov=app --cov-report=term-missing` passed, 182 tests, 91% coverage.
- 2026-07-17: Subagent review found action precedence, configured-LLM invocation, and focused coverage gaps.
- 2026-07-17: `.venv/bin/pytest tests/test_digest_builder.py` passed after review fixes, 41 tests.
- 2026-07-17: `.venv/bin/pytest tests/test_cli_commands.py` passed after review fixes, 49 tests.
- 2026-07-17: `.venv/bin/pytest --cov=app --cov-report=term-missing` passed after review fixes, 187 tests, 91% coverage.

### Completion Notes List

- 2026-07-17: Created Story 3.7 from operator grill session about reducing window digest verbosity.
- Sprint status file was not present, so sprint tracking was not updated.
- 2026-07-17: Implemented window-only compact digest rendering with `Open Signals` and compact raw high-score sections while preserving the daily long digest contract.
- 2026-07-17: Added compact graded signal rendering with label emojis, risk flags, action mapping, sorted top-8 output, and deterministic position fallback when grading is absent.
- 2026-07-17: Added focused digest and CLI coverage for compact window output, missing grading fallback, raw-message caps, configured LLM contract protection, and daily contract preservation.
- 2026-07-17: Resolved review findings by making `recommended_action=review` render green ahead of grade-C fallback, invoking configured LLMs for window digests while falling back to deterministic compact output on contract violations, and expanding tests for cooling labels, multiple risk flags, A/B priority fallback, empty grading results, and unknown labels.

### File List

- `_bmad-output/implementation-artifacts/story-3.7-compact-window-open-signals-digest.md`
- `app/summarization/digest_builder.py`
- `tests/test_digest_builder.py`
- `tests/test_cli_commands.py`

## Change Log

- 2026-07-17: Created ready-for-dev story for compact window-only `Open Signals` digest format.
- 2026-07-17: Implemented compact window digest rendering and marked story ready for review.
- 2026-07-17: Addressed subagent review findings and reran focused/full validation.
