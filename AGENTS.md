# Agent Instructions

This repository is `alpha-digest`, a Python-first crypto alpha digest backend.

## Core Standards

- Prefer simple, clean, robust working software over clever abstractions.
- Keep architecture modular and easy to reason about.
- Preserve clear boundaries between ingestion, persistence, processing, summarization, delivery, CLI, and UI.
- Do not add agents, orchestration layers, queues, services, or frontend complexity unless a story explicitly requires it.
- Favor typed Python, explicit data flow, small functions, and straightforward SQLAlchemy usage.
- Use existing project patterns before introducing new ones.

## Architecture Expectations

- Each module should have one clear responsibility.
- Avoid circular imports and hidden side effects.
- Keep external integrations behind small adapter modules.
- Keep domain logic testable without network access.
- Store configuration in environment variables and `.env.example`.
- Prefer SQLite-compatible behavior unless a story explicitly migrates storage.
- Any UI/UX work must be clean, responsive, and user-centered. Do not ship rough placeholder UX as complete work.

## Testing Bar

- Use `pytest`.
- Maintain at least 80% test coverage for application code.
- Add or update tests for every feature, bug fix, and meaningful behavior change.
- Tests should cover happy paths, edge cases, and failure behavior where practical.
- Networked integrations should be mocked or isolated unless an explicit integration test is requested.
- A feature is not done until the relevant tests pass.

## Feature Workflow

- Never blindly start implementing a feature from a raw request.
- Before implementing any feature, first run the BMAD help flow (`bmad-help`) to confirm the right BMAD path.
- After BMAD help, create or confirm the BMAD epic/story for the feature before editing application code.
- Every feature must be represented as a BMAD epic and story before implementation starts.
- Stories should include acceptance criteria, implementation notes, and test expectations.
- Implement only the story scope. Avoid opportunistic refactors unless they are required to finish safely.
- After each feature implementation, run the orchestration/review flow.
- Reviews should include code quality, architecture, test coverage, edge cases, and acceptance criteria.
- If any review or test fails, fix the issue and rerun the relevant checks.
- A feature is complete only when implementation, tests, and reviews are green.

## Definition Of Done

- Acceptance criteria are satisfied.
- Tests pass locally or in the intended Docker environment.
- Coverage remains at or above 80%.
- Code is simple, clean, and maintainable.
- Documentation and `.env.example` are updated when behavior or configuration changes.
- Stubs are clearly marked and do not masquerade as production-ready integrations.
- The final response states what changed, what was tested, and any remaining limitations.

## Commands

- Do not run `codex` CLI commands in this repository. If a workflow needs a
  Codex-related command, provide the exact command for the user to run instead.

Preferred local setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest --cov=app --cov-report=term-missing
```

Docker path:

```bash
docker compose build
docker compose run --rm alpha-digest init-db
docker compose run --rm alpha-digest ingest-all
docker compose run --rm alpha-digest build-digest --date YYYY-MM-DD
docker compose run --rm alpha-digest send-digest --date YYYY-MM-DD
```
