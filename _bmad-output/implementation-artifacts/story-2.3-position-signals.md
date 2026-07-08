# Story 2.3: Extract and Render Position Signals

Status: implemented

## Story

As a crypto alpha operator,
I want the digest to identify buy/open/accumulate and sell/close/reduce signals,
so that `Open Positions` shows directional token activity instead of generic opportunities.

## Acceptance Criteria

1. Given source messages contain position-like language such as bought, longed, opened, accumulated, sold, closed, or reduced, when entity/signal extraction runs, then the system classifies the signal direction as buy/open/accumulate or sell/close/reduce where confidence is sufficient.
2. Given a position signal is classified, when it is stored or passed to summarization, then it preserves token/project, direction, source message ID, confidence, and evidence text.
3. Given the digest renders `Open Positions`, when a buy/open/accumulate signal appears, then it is shown with a green dot marker.
4. Given the digest renders `Open Positions`, when a sell/close/reduce signal appears, then it is shown with a red dot marker.
5. Given a message is ambiguous or sarcastic, when the extractor cannot classify the position confidently, then it does not create a directional position signal and leaves the message available for normal summarization.

## Tasks / Subtasks

- [x] Add position-signal extraction in the processing boundary (AC: 1, 2, 5)
  - [x] Detect buy/open/accumulate verbs: bought, longed, opened, accumulated.
  - [x] Detect sell/close/reduce verbs: sold, closed, reduced.
  - [x] Require an extracted ticker/project near the action language before creating a signal.
  - [x] Preserve token/project, direction, source message ID, confidence, and evidence text.
  - [x] Avoid creating directional signals for ambiguous, sarcastic, or negated messages.
- [x] Pass extracted position signals into fallback digest rendering (AC: 2, 3, 4)
  - [x] Render buy/open/accumulate signals with a green dot marker.
  - [x] Render sell/close/reduce signals with a red dot marker.
  - [x] Keep the Story 2.2 operator-readable section order unchanged.
- [x] Add focused tests for extraction and rendering behavior (AC: 1, 2, 3, 4, 5)
  - [x] Cover buy/open/accumulate classification.
  - [x] Cover sell/close/reduce classification.
  - [x] Cover preserved source/evidence/confidence fields.
  - [x] Cover ambiguous or sarcastic non-classification.
  - [x] Cover `Open Positions` digest rendering markers.

## Dev Notes

- Keep implementation inside existing module boundaries: extraction logic belongs in `app/processing`, digest rendering in `app/summarization`. [Source: `AGENTS.md`]
- Avoid schema changes unless required. Story 2.3 allows signals to be stored or passed to summarization; using derived signal objects from already-loaded messages is sufficient for this MVP. [Source: `_bmad-output/planning-artifacts/epics.md`]
- Story 2.2 already established the `Open Positions` digest section and exact section order; Story 2.3 must preserve that contract. [Source: `_bmad-output/implementation-artifacts/story-2.2-operator-readable-digest-format.md`]
- Existing entity extraction finds tickers, URLs, and crypto keywords in `app/processing/extract_entities.py`; position extraction should reuse this style and stay deterministic/testable without network access. [Source: `app/processing/extract_entities.py`]
- Raw source auditability should remain available through message locators in the digest renderer. [Source: `_bmad-output/implementation-artifacts/story-2.2-operator-readable-digest-format.md`]

### Project Structure Notes

- Expected code touch points: `app/processing/extract_entities.py`, `app/summarization/digest_builder.py`.
- Expected tests: `tests/test_extract_entities.py`, `tests/test_digest_builder.py`.
- No UI, service, queue, or orchestration changes are needed.

### References

- `_bmad-output/planning-artifacts/epics.md` - Epic 2 and Story 2.3 requirements.
- `_bmad-output/implementation-artifacts/story-2.2-operator-readable-digest-format.md` - prior digest-format contract.
- `AGENTS.md` - project architecture and testing standards.

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- `.venv/bin/pytest tests/test_extract_entities.py tests/test_digest_builder.py -q`: 17 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 70 passed, total coverage 87%.
- GPT-5.4 medium `code-review` subagent: 3 findings; all addressed.
- `.venv/bin/pytest tests/test_extract_entities.py tests/test_digest_builder.py -q`: 31 passed.
- `.venv/bin/pytest --cov=app --cov-report=term-missing`: 84 passed, total coverage 87%.

### Completion Notes List

- Added deterministic position-signal extraction with conservative ticker proximity and ambiguity filtering.
- Rendered extracted signals in `Open Positions` with green dot and red dot markers while preserving source locators and evidence.
- Kept Story 2.2 section ordering intact and avoided storage schema changes.
- Adjusted ambiguity filtering to candidate evidence windows so unrelated phrases such as "not financial advice" do not suppress valid signals.
- Added full verb coverage for bought, longed, opened, accumulated, sold, closed, and reduced.
- Changed digest rendering to consume a precomputed map of extracted `PositionSignal` objects instead of extracting inside the renderer.

### File List

- `_bmad-output/implementation-artifacts/story-2.3-position-signals.md`
- `app/processing/extract_entities.py`
- `app/summarization/digest_builder.py`
- `tests/test_extract_entities.py`
- `tests/test_digest_builder.py`
