# Story 3.5: Log Graded Window Digest Context

Status: review

## Acceptance Criteria

- Window digest builds log whether matching graded signal output was found for the requested window.
- Logs include the requested window, matched grading file path, and grade count when enrichment is used.
- Logs make the miss case observable without failing the digest build.
- Tests cover matched and missing grading output behavior.

## Implementation Notes

- Scope is limited to observability around the existing Story 3.4 graded-context integration.
- Do not change matching semantics; grading window must still exactly match digest window.
- Do not persist grading state in the database.

## Test Expectations

- Add or update pytest coverage for matching and missing grading output.
- Run the relevant test file before completion.

## Dev Notes

- 2026-07-17: Created as a narrow follow-up after operator confusion about whether `build-window-digest` used graded signals.
