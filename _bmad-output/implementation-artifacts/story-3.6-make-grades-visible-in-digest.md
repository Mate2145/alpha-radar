# Story 3.6: Make Grades Visible In Digest Markdown

Status: review

## Acceptance Criteria

- Window and daily digests built with matching grading output include explicit grade metadata in the exported Markdown.
- The visible metadata includes grade, priority, confidence, summary, recommended action, and useful audit context.
- LLM-backed digests cannot silently paraphrase away all grade metadata.
- Existing digest section contract remains unchanged.

## Implementation Notes

- Scope is limited to rendering/prompt integration for existing file-based grading output.
- Do not change grading matching semantics.
- Do not add database persistence for grading metadata in this story.

## Test Expectations

- Add tests proving the LLM digest path includes explicit grade metadata in final Markdown.
- Keep existing fallback and exact-window tests passing.

## Dev Notes

- 2026-07-17: Created after exported Codex digest showed grading influence semantically but did not preserve explicit grade markers.
