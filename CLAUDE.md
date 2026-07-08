# Claude Instructions

This repository is `alpha-digest`, a Python-first crypto alpha digest backend.

Follow the same delivery standard as `AGENTS.md`.

## Working Principles

- Keep the system simple, clean, robust, and working.
- Protect architecture quality. Do not blur ingestion, processing, persistence, summarization, delivery, CLI, and UI responsibilities.
- Prefer boring, maintainable Python over speculative abstractions.
- Do not introduce frontend, agent, orchestration, queue, or service complexity unless the current BMAD story explicitly asks for it.
- Keep external services behind small adapters that can be tested without live credentials.

## BMAD Feature Process

- Every feature starts as a BMAD epic and story.
- Do not implement a feature until the story scope and acceptance criteria are clear.
- Implement the story directly and keep changes scoped.
- After implementation, run the orchestration/review process.
- Reviews must check acceptance criteria, architecture, code quality, test coverage, edge cases, and documentation.
- If anything is red, fix it and rerun the relevant checks.
- The feature is done only when tests and reviews are green.

## Testing Requirements

- Use `pytest`.
- Maintain at least 80% coverage for `app`.
- Add tests for every feature and bug fix.
- Mock network calls and credentialed integrations by default.
- Prefer deterministic tests that run locally and in Docker.

## Product Quality

- Backend behavior should be reliable and observable.
- Configuration must be documented in `.env.example` and `README.md`.
- Any UI/UX work must be clean, responsive, and practical for real use.
- Stubs must be explicit and documented.

## Completion Checklist

- Story acceptance criteria satisfied.
- Tests pass.
- Coverage is at least 80%.
- Orchestration/review is complete and green.
- Documentation updated if commands, config, architecture, or user behavior changed.
- Final response includes changes, tests run, and any known limitations.

