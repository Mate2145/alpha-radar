---
baseline_commit: d60f617726c9998e1960c6d0ec125ec148f5604c
---

# Story 3.4: Render Codex-Graded Signal Context in Digests

Status: review

## Story

As a crypto alpha operator,
I want digest sections to show validated Codex-graded signal context concisely,
so that I can scan why a signal matters without reading raw messages first.

## Acceptance Criteria

1. Given a digest is built for a window with matching validated schema `1.1` grading output, when the digest is rendered, then token or project entries can include Codex grade, priority, confidence, concise summary, recommended action, and labels such as `new`, `repeated`, `cross-source`, `heating up`, or `cooling down` when those labels are present in the grading output.
2. Given a graded signal has memory context, when it appears in the digest, then the rendered context includes first-seen or latest-seen information where useful and does not overwhelm the existing operator-readable format.
3. Given a graded signal includes repeated or cross-source context, when it is rendered in fallback mode, then the repeated-signal section shows source spread, source count, or source message references in concise language; when a configured LLM is used, the validated graded context is supplied in the prompt and the LLM output must satisfy the digest section contract.
4. Given the existing daily and window digest commands are used, when matching grading output is available, then the enriched digest output remains compatible with both command paths.
5. Given no matching schema `1.1` grading output is available, when a digest is built, then digest generation falls back to the existing deterministic/operator-readable output without failing.
6. Given raw audit output is enabled, when enriched digest context is rendered in fallback mode, then source messages remain available for manual verification; when a configured LLM is used, raw audit rendering is governed by the prompt and required digest section contract.
7. Given tests run locally, when grading-output digest rendering is exercised, then file loading, exact-window matching, fallback behavior, and Markdown rendering are verified without calling Codex CLI or networked integrations.

## Tasks / Subtasks

- [x] Load validated grading output for digest windows (AC: 1, 4, 5, 7)
  - [x] Reuse the Story 3.1 grading output contract and validators where practical.
  - [x] Only consume schema `1.1` grading output for enriched rendering.
  - [x] Treat legacy schema `1.0` output as unavailable enrichment and fall back without failing.
  - [x] Prefer exact-window output when the digest window is known.
  - [x] Use `data/signal-grading/output/latest.json` only when its `window.start` and `window.end` match the digest window.
  - [x] Treat absent, stale, invalid, or non-matching grading output as a non-fatal fallback condition.

- [x] Add digest rendering support for graded signal context (AC: 1, 2, 3, 6)
  - [x] Render concise grade metadata in fallback mode and pass the same validated context to configured LLM mode: grade, priority, confidence, summary, recommended action, labels, and risk flags when present.
  - [x] Render memory metadata already present in the grading contract: first/latest seen, mention count, source count, and source message IDs.
  - [x] Keep the existing operator-readable section structure intact unless a small adjustment is needed for clarity.
  - [x] Preserve raw high-score/source message auditability.

- [x] Wire grading context into daily and window digest paths (AC: 4, 5)
  - [x] Keep `build-window-digest` as the primary exact-window integration path.
  - [x] Keep `build-digest --date` compatible, using the daily window semantics already established by the digest builder.
  - [x] Do not make digest generation depend on a successful `grade-signals` run.

- [x] Add focused offline tests (AC: 1-7)
  - [x] Test exact-window grading output is rendered.
  - [x] Test stale or non-matching `latest.json` is ignored.
  - [x] Test invalid grading output falls back without breaking digest generation.
  - [x] Test missing grading output falls back without breaking digest generation.
  - [x] Test graded metadata is concise and does not remove raw audit output.
  - [x] Test both daily and window digest command paths remain compatible.

- [x] Run validation when implementation starts (AC: 7)
  - [x] Run targeted digest/grading rendering tests.
  - [x] Run `pytest --cov=app --cov-report=term-missing`.
  - [x] Coverage must remain at or above 80%.
  - [x] Update Dev Agent Record, File List, Change Log, and status after implementation and review.

## Dev Notes

### Epic 3 Dependency Direction

- Story 3.1 is the foundation for Epic 3. This story renders the output of the Codex grading layer; it should not create a separate digest-first signal quality path.
- Story 3.2 signal memory should feed the grading input contract with first-seen/latest-seen, mention count, source count, source message IDs, and labels.
- Story 3.3 repeated-signal detection should feed the grading input contract with repeated/cross-source labels, source spread, score, evidence, and audit message IDs.
- Story 3.4 consumes validated schema `1.1` grading output first. Direct rendering of `SignalMemory` or `RepeatedSignal` should only be an explicit fallback if implementation chooses to support that path.
- The grading input JSON is the frozen source-of-evidence. The grading output JSON is the source-of-judgment plus exact echoed evidence for later digest rendering.

### Scope Boundaries

- This story is digest integration only.
- Do not add new ingestion behavior, database tables, migrations, schedulers, queues, services, frontend surfaces, or new dependencies.
- Do not run Codex CLI from digest commands.
- Do not invoke real Codex CLI in tests.
- Do not persist grading output to the database.
- Do not implement trusted-source YAML or source-quality inspection here unless a later story revision explicitly changes scope.
- Do not remove existing raw audit output.

### Current Codebase Facts

- Story 3.1 added the file-based grading flow under `data/signal-grading/`.
- Grading output schema `1.1` includes `window`, `grades`, grade metadata, aliases, chain, labels, first/latest seen, mention count, source count, VIP source count, source message IDs, summary, reasoning, risk flags, and recommended action.
- In schema `1.1`, Codex may omit input candidates, but every emitted grade must map to an input signal and exactly echo evidence fields from that signal. Extra output grades are invalid.
- Story 3.2 added `app/processing/signal_memory.py`.
- Story 3.3 added `app/processing/repeated_signals.py`.
- Digest rendering lives in `app/summarization/digest_builder.py`.
- CLI digest commands live in `app/cli.py`.
- Existing digest tests live in `tests/test_digest_builder.py` and CLI command tests in `tests/test_cli_commands.py`.

### Implementation Guidance

- Keep the loader small and explicit. It should read candidate grading output files, validate them with the Story 3.1 output validator if possible, and compare window start/end before use.
- Do not consume legacy schema `1.0` output for enriched rendering. Treat it the same as absent or invalid enrichment.
- Avoid broad coupling from digest rendering back into grading invocation. The dependency should be file/contract based.
- In fallback mode, prefer concise Markdown such as:
  - `- $ABC - Grade A / high priority / 0.86 confidence: repeated cross-source signal. Action: review.`
  - Include first/latest seen or source count only when available and useful.
- In configured LLM mode, pass the same validated graded context into the prompt and validate that the returned Markdown preserves the required digest section structure.
- Preserve deterministic output ordering. A reasonable default is priority/grade order from grading output, then confidence descending, then signal key.
- Keep fallback behavior boring: if grading context cannot be loaded, render the current digest format.

### Testing Requirements

- Tests must be offline and deterministic.
- Mock or use temporary grading output files; do not call Codex CLI.
- Cover exact-window matching, stale latest output, invalid JSON/schema, missing files, and successful rendering.
- Cover legacy schema `1.0` output falling back without enriched rendering.
- Run full coverage before moving the story out of implementation/review.

### References

- [Epic planning artifact](../planning-artifacts/epics.md)
- [Story 3.1 artifact](story-3.1-codex-cli-signal-grading-pipeline.md)
- [Story 3.2 artifact](story-3.2-track-signal-memory.md)
- [Story 3.3 artifact](story-3.3-detect-repeated-signals-across-sources.md)
- [Epic 3 grading decisions](../../docs/epic-3-grading-decisions.md)
- [Digest builder](../../app/summarization/digest_builder.py)
- [CLI commands](../../app/cli.py)
- [Signal grading module](../../app/processing/signal_grading.py)
- [Signal memory module](../../app/processing/signal_memory.py)
- [Repeated signals module](../../app/processing/repeated_signals.py)

## Questions / Clarifications Saved For Later

- Should exact-window grading output be located by filename first, by `latest.json` window match first, or by both with exact-window filename taking precedence?
- Should invalid grading output be silently ignored in digest builds, or should debug/log output mention that enrichment was skipped?
- Should direct deterministic `SignalMemory`/`RepeatedSignal` rendering be supported as a fallback, or should fallback mean the pre-3.4 digest format only?
- Resolved for grading schema: Story 3.4 should consume only validated schema `1.1` output. Legacy schema `1.0` output is not eligible for enriched rendering.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- 2026-07-16: Started implementation from explicit user request for Story 3.4.
- 2026-07-16: Red test run confirmed missing digest grading loader API with `ImportError`.
- 2026-07-16: Targeted validation passed with `.venv/bin/python -m pytest tests/test_digest_builder.py tests/test_cli_commands.py -q`.
- 2026-07-16: Full validation passed with `.venv/bin/python -m pytest --cov=app --cov-report=term-missing` at 91% coverage.
- 2026-07-16: Addressed post-implementation review gaps by adding configured-LLM prompt capture coverage and explicit daily/window CLI compatibility coverage.

### Completion Notes List

- Created Story 3.4 as a grading-output digest integration story.
- Scoped implementation to consume validated Story 3.1 grading output with graceful fallback.
- Documented that Story 3.2 and Story 3.3 feed the grading input contract before digest rendering.
- Documented schema `1.1` as the required digest-enrichment contract and legacy schema `1.0` as fallback-only.
- Implemented exact-window schema `1.1` grading output loading for digest windows with non-fatal fallback for missing, stale, invalid, or legacy outputs.
- Rendered concise graded signal context in the existing repeated-signal section, including grade, priority, confidence, summary, action, labels, seen metadata, source metadata, message IDs, and risk flags.
- Wired grading context into daily and window digest builders without requiring `grade-signals` to run successfully.
- Added offline digest tests for exact-window fallback rendering, stale latest fallback, invalid and legacy fallback, schema `1.1` grade-validation fallback, missing output fallback, raw audit preservation, and daily/window compatibility.
- Added configured-LLM prompt coverage to verify validated grading context is passed to AI rendering with grade, summary, action, labels, first/latest seen, source metadata, and risk flags, plus explicit CLI command compatibility tests for daily and window digest command paths.
- Clarified that deterministic repeated-signal and raw audit rendering is fallback-mode behavior; configured LLM mode receives graded context through the prompt and is validated against the digest section contract.

### File List

- `_bmad-output/implementation-artifacts/story-3.4-render-codex-graded-signal-context-in-digests.md`
- `app/summarization/digest_builder.py`
- `tests/test_cli_commands.py`
- `tests/test_digest_builder.py`

## Change Log

- 2026-07-16: Created draft Story 3.4 artifact as a documentation-only planning update. Implementation deferred.
- 2026-07-16: Recorded grading contract decisions for schema `1.1`, exact echoed evidence, rejected extra grades, allowed omissions, and legacy `1.0` fallback behavior.
- 2026-07-16: Implemented Story 3.4 digest grading-output enrichment and moved story to review.
- 2026-07-16: Synced implementation, tests, and story artifact after review feedback.
- 2026-07-16: Addressed follow-up findings for real CLI builder coverage, schema `1.1` validation fallback, configured-LLM prompt assertions, cooling-down labels, and fallback-vs-LLM documentation wording.
