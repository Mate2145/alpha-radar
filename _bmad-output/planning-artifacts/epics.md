---
stepsCompleted:
  - bmad-help
  - lean-epic-created
  - epic-2-time-window-digest-created
inputDocuments:
  - AGENTS.md
  - README.md
---

# alpha-radar - Epic Breakdown

## Overview

This is a lean BMAD epic artifact for the first MVP smoke test. It is intentionally scoped to one vertical slice and does not replace a full PRD or architecture document.

## Requirements Inventory

### Functional Requirements

FR1: The system can ingest or otherwise load the last 24 hours of messages from two configured Telegram channels.

FR2: The system can filter the 24-hour message set for a known Robinhood-related signal context.

FR3: The system can extract and surface the `$cashchat` ticker/signal if it appears in the relevant Telegram messages.

FR4: The system can produce a smoke-test result showing whether the expected signal was found, with enough source context to verify the result manually.

FR5: The system can ingest configured Telegram channel messages into the normal digest database.

FR6: The system can include ingested Telegram messages in the same summarization path as RSS messages.

FR7: The system can send a built digest to the configured Telegram destination chat.

FR8: The system can use Codex CLI as an LLM provider for AI-written digest summaries.

FR9: The system can report Codex CLI setup failures clearly before or during digest generation.

FR10: The system can export a stored digest to Markdown for local inspection before sending.

FR11: The system can build digests for explicit time windows instead of only calendar days.

FR12: The digest output can follow a clearer operator-facing format with concise narratives, repeated signals, links, and temporary raw-message auditability.

FR13: The system can classify position-like signals from source messages, including bought/opened/accumulated and sold/closed/reduced token actions.

FR14: Position signals can be rendered in the digest with clear visual markers: green dot for buy/open/accumulate and red dot for sell/close/reduce.

FR15: Raw high-score messages remain available for audit during the MVP, but the design allows hiding or silencing them later.

### NonFunctional Requirements

NFR1: The smoke test must be runnable locally without requiring production scheduling.

NFR2: Networked Telegram access must be isolated behind the ingestion adapter boundary and must not leak credentials.

NFR3: Tests must mock Telegram/network behavior unless an explicit live integration run is requested.

NFR4: The implementation must preserve the existing SQLite-first MVP architecture.

NFR5: Time-window digest generation must remain runnable locally from the CLI and be schedulable at 2-hour, 6-hour, and 12-hour cadences.

NFR6: Position extraction must be testable without live network access and must preserve source-message traceability for every classified signal.

### Additional Requirements

- Use existing project boundaries: `app/ingest`, `app/processing`, `app/summarization`, `app/cli.py`, and `app/db`.
- Keep Telegram credentials in environment variables and document them in `.env.example` if new variables are required.
- Do not add queues, workers, orchestration services, or frontend surfaces for this smoke test.
- Keep the result inspectable from the CLI.
- Keep the first time-window implementation compatible with SQLite and the existing CLI-oriented operating model.
- Do not remove raw high-score message audit output until a replacement audit/debug path exists.

### UX Design Requirements

- None. This story is CLI/backend only.

### FR Coverage Map

- FR1 -> Story 1.1
- FR2 -> Story 1.1
- FR3 -> Story 1.1
- FR4 -> Story 1.1
- FR5 -> Story 1.2
- FR6 -> Story 1.2
- FR7 -> Story 1.2
- FR8 -> Story 1.3
- FR9 -> Story 1.3
- FR10 -> Story 1.3
- FR11 -> Story 2.1
- FR12 -> Story 2.2
- FR13 -> Story 2.3
- FR14 -> Story 2.3
- FR15 -> Story 2.2

## Epic List

1. Epic 1: Telegram Alpha Signal Smoke Test
2. Epic 2: Time-Window Digest Format and Position Signal Extraction

## Epic 1: Telegram Alpha Signal Smoke Test

Validate the first useful end-to-end alpha discovery slice: pull the last 24 hours of messages from two Telegram channels and confirm the system can surface the known Robinhood-related `$cashchat` signal.

### Story 1.1: Detect `$cashchat` From Two Telegram Channels Over Last 24 Hours

As a crypto alpha operator,
I want to run a local smoke test against two Telegram channels for the last 24 hours,
So that I can verify the system can recover the known Robinhood-related `$cashchat` signal from real source messages.

**Acceptance Criteria:**

**Given** two Telegram channels are configured for ingestion
**When** I run the smoke-test command for a 24-hour lookback
**Then** the system loads messages from both configured channels
**And** restricts evaluation to messages inside the 24-hour window.

**Given** the loaded messages include Robinhood-related content mentioning `$cashchat`
**When** the smoke test evaluates the messages
**Then** the result identifies `$cashchat` as a found signal
**And** includes enough message/source context to manually verify why it was found.

**Given** Telegram credentials or channel configuration are missing
**When** I run the smoke-test command
**Then** the system fails with a clear configuration error and does not masquerade as a successful no-signal result.

**Given** no matching `$cashchat` signal is present in the 24-hour messages
**When** I run the smoke-test command
**Then** the system reports that the expected signal was not found and includes basic counts for inspected channels/messages.

### Story 1.2: Ingest Configured Telegram Channels Into Daily Digest

As a crypto alpha operator,
I want configured Telegram channel messages to be ingested into the normal digest database,
So that the final daily summary sent to my own Telegram channel includes Telegram-sourced alpha.

**Acceptance Criteria:**

**Given** Telegram API credentials and source channels are configured
**When** I run `alpha ingest-all`
**Then** the system reads recent Telegram messages from the configured channels
**And** persists new messages into the existing `messages` table with source metadata, score, entities, URL when available, and content hash.

**Given** Telegram messages were ingested for the target day
**When** I run `alpha build-digest --date YYYY-MM-DD`
**Then** the digest includes Telegram messages in the same summarization path as RSS messages.

**Given** a digest has been built
**When** I run `alpha send-digest --date YYYY-MM-DD`
**Then** the existing Telegram delivery command sends that final summary to my configured destination chat.

**Given** Telegram credentials or source channels are missing
**When** I run `alpha ingest-all`
**Then** the Telegram ingestion step returns zero or fails clearly according to configuration mode without corrupting RSS ingestion or existing data.

**Given** Telegram ingestion is run multiple times
**When** a message was already stored
**Then** duplicate content is not inserted again.

### Story 1.3: Use Codex CLI for AI-Written Daily Digest Summaries

As a crypto alpha operator,
I want the digest builder to use my local Codex CLI subscription session,
So that the final Telegram summary is AI-written without requiring OpenAI API billing.

**Acceptance Criteria:**

**Given** Codex CLI is installed and authenticated
**When** I set `LLM_PROVIDER=codex_cli` and run `alpha build-digest --date YYYY-MM-DD`
**Then** the digest builder sends the selected daily messages to `codex exec`
**And** stores the AI-written Markdown summary in `daily_summaries`.

**Given** Codex CLI is missing, not authenticated, times out, or returns no content
**When** I run the configured summarization pipeline
**Then** the failure is reported clearly enough to fix login/configuration without silently sending a fallback summary.

**Given** I want to verify setup before a full digest run
**When** I run a local LLM check command
**Then** the app validates the configured provider and prints a concise success or actionable failure.

**Given** a digest is built through Codex CLI
**When** I inspect the stored summary or exported Markdown
**Then** the summary identifies the model/provider as `codex-cli:*` and remains compatible with the existing `send-digest` command.

## Epic 2: Time-Window Digest Format and Position Signal Extraction

Evolve the daily digest into a clearer operator-facing report that can run on 2-hour, 6-hour, 12-hour, or explicit time windows, while introducing position-signal extraction for bought/opened/accumulated and sold/closed/reduced token actions.

This epic is future scope. It must not destabilize the current v1 daily digest flow until the time-window path is implemented and tested end-to-end.

### Story 2.1: Build Digests for Explicit Time Windows

As a crypto alpha operator,
I want digest generation to accept an explicit time window or recent-hours value,
So that I can schedule useful updates every 2, 6, or 12 hours instead of only once per calendar day.

**Acceptance Criteria:**

**Given** messages exist inside a requested time window
**When** I run a time-window digest command
**Then** the digest builder selects messages whose `created_at` falls within that exact window.

**Given** I request a recent-hours digest such as 2, 6, or 12 hours
**When** the command runs
**Then** the system derives the correct window start and end timestamps and records them with the summary.

**Given** multiple digests are generated on the same calendar day
**When** each digest uses a different window
**Then** the system stores them as separate summaries instead of overwriting a single daily row.

**Given** the existing daily digest command is still used
**When** it runs
**Then** the current v1 daily behavior remains available until intentionally replaced.

### Story 2.2: Format the Digest for Operator Readability

As a crypto alpha operator,
I want the digest sections to be concise and consistent,
So that I can scan the output quickly and decide what deserves follow-up.

**Acceptance Criteria:**

**Given** a digest is built for a time window
**When** the Markdown is generated
**Then** it uses this section structure: `Executive Summary`, `Top Narratives`, `Most Mentioned Tokens / Projects`, `Repeated Signals Across Sources`, `Open Positions`, `Links Worth Reviewing`, and `Raw High-Score Messages`.

**Given** `Top Narratives` are generated
**When** the digest is rendered
**Then** each narrative is a brief one-sentence summary.

**Given** raw messages are still needed for audit
**When** the digest is rendered
**Then** `Raw High-Score Messages` remains present for now.

**Given** a future silent/raw-debug mode is introduced
**When** raw messages are hidden from the user-facing digest
**Then** the system still provides an audit path for selected source messages.

### Story 2.3: Extract and Render Position Signals

As a crypto alpha operator,
I want the digest to identify buy/open/accumulate and sell/close/reduce signals,
So that `Open Positions` shows directional token activity instead of generic opportunities.

**Acceptance Criteria:**

**Given** source messages contain position-like language such as bought, longed, opened, accumulated, sold, closed, or reduced
**When** entity/signal extraction runs
**Then** the system classifies the signal direction as buy/open/accumulate or sell/close/reduce where confidence is sufficient.

**Given** a position signal is classified
**When** it is stored or passed to summarization
**Then** it preserves token/project, direction, source message ID, confidence, and evidence text.

**Given** the digest renders `Open Positions`
**When** a buy/open/accumulate signal appears
**Then** it is shown with a green dot marker.

**Given** the digest renders `Open Positions`
**When** a sell/close/reduce signal appears
**Then** it is shown with a red dot marker.

**Given** a message is ambiguous or sarcastic
**When** the extractor cannot classify the position confidently
**Then** it does not create a directional position signal and leaves the message available for normal summarization.
