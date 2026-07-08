# Story 2.2: Format the Digest for Operator Readability

Status: done

## Story

As a crypto alpha operator,
I want the digest sections to be concise and consistent,
so that I can scan the output quickly and decide what deserves follow-up.

## Acceptance Criteria

1. Given a digest is built for a time window, when the Markdown is generated, then it uses this section structure: `Executive Summary`, `Top Narratives`, `Most Mentioned Tokens / Projects`, `Repeated Signals Across Sources`, `Open Positions`, `Links Worth Reviewing`, and `Raw High-Score Messages`.
2. Given `Top Narratives` are generated, when the digest is rendered, then each narrative is a brief one-sentence summary.
3. Given raw messages are still needed for audit, when the digest is rendered, then `Raw High-Score Messages` remains present for now.
4. Given a future silent/raw-debug mode is introduced, when raw messages are hidden from the user-facing digest, then the system still provides an audit path for selected source messages.

## Tasks / Subtasks

- [x] Update digest prompt contract for the operator-readable section structure (AC: 1, 2, 3)
  - [x] Remove `Potential Opportunities` and `Risks / Warnings` from the requested output structure.
  - [x] Add `Open Positions` in the required order.
  - [x] Tell the LLM that `Top Narratives` must be brief one-sentence bullets.
- [x] Update fallback digest rendering to match the Story 2.2 structure (AC: 1, 2, 3)
  - [x] Preserve the title and `Executive Summary`.
  - [x] Render `Top Narratives` as one-sentence bullets from available keyword signals.
  - [x] Keep `Raw High-Score Messages` visible as the current audit path.
  - [x] Keep `Open Positions` present even before Story 2.3 directional extraction exists.
- [x] Add focused tests for the digest format contract (AC: 1, 2, 3, 4)
  - [x] Assert fallback window/digest Markdown headings match the required order.
  - [x] Assert old sections are absent.
  - [x] Assert top narrative bullets are short single sentences.
  - [x] Assert raw high-score audit messages remain available.

## Dev Notes

- Story 2.2 is CLI/backend only; no UI changes are required. [Source: `_bmad-output/planning-artifacts/epics.md`]
- Keep the existing SQLite-first MVP and module boundaries. Digest formatting belongs in `app/summarization`; CLI and persistence should not need new services or orchestration. [Source: `AGENTS.md`]
- Story 2.1 introduced `WindowSummary`, `build_window_digest(session, window_start, window_end)`, and `load_messages_for_window(...)`. Story 2.2 should build on that without replacing the daily digest path. [Source: `_bmad-output/implementation-artifacts/story-2.1-time-window-digests.md`]
- Position direction extraction is Story 2.3. For Story 2.2, `Open Positions` must exist in the digest format, but it can report that no directional positions were classified yet. [Source: `_bmad-output/planning-artifacts/epics.md`]
- Raw high-score messages must remain visible for MVP auditability until a later raw-debug/silent mode provides another audit path. [Source: `_bmad-output/planning-artifacts/epics.md`]

### Project Structure Notes

- Expected code touch points: `app/summarization/prompts.py`, `app/summarization/digest_builder.py`.
- Expected test touch point: a summarization-focused pytest module under `tests/`.
- Avoid storage schema changes for this story.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 2 and Story 2.2 requirements.
- `_bmad-output/implementation-artifacts/story-2.1-time-window-digests.md` - prior story context.
- `AGENTS.md` - repository architecture and testing standards.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_digest_builder.py -q`: 3 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 60 passed, total coverage 85%.
- GPT-5.4 medium `code-review` subagent: 4 findings; all addressed.
- `.venv/bin/pytest tests/test_digest_builder.py -q`: 7 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 64 passed, total coverage 86%.

### Completion Notes List

- Created Story 2.2 from the Epic 2 requirements and implemented the digest-format scope only.
- Updated the LLM prompt to request the exact operator-readable sections, including `Open Positions`, and to make `Top Narratives` brief one-sentence bullets.
- Updated fallback digest rendering to use the same section order, keep raw high-score audit messages visible, and preserve an explicit `Open Positions` section until Story 2.3 adds directional position extraction.
- Added post-generation validation for configured LLM output so invalid section order or multi-sentence `Top Narratives` are rejected instead of stored.
- Added stable raw-message locators using URL, external ID, or message ID where available.
- Added a raw-hidden fallback mode that hides raw body text while preserving audit references for selected messages.
- Addressed all GPT-5.4 medium review findings and reran full coverage successfully.

### File List

- `_bmad-output/implementation-artifacts/story-2.2-operator-readable-digest-format.md`
- `app/summarization/prompts.py`
- `app/summarization/digest_builder.py`
- `tests/test_digest_builder.py`
