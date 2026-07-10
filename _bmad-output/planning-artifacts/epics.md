---
stepsCompleted:
  - bmad-help
  - lean-epic-created
  - epic-2-time-window-digest-created
  - bmad-create-epics-and-stories:step-01-validate-prerequisites
  - bmad-create-epics-and-stories:step-02-design-epics
  - bmad-create-epics-and-stories:step-03-create-stories
  - bmad-create-epics-and-stories:step-04-final-validation
inputDocuments:
  - AGENTS.md
  - README.md
  - _bmad-output/planning-artifacts/epics.md
  - User request: Epic 3 source quality scoring and signal memory
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

FR16: The system can maintain source quality metadata for each configured source, including a simple operator-readable trust or quality score.

FR17: The system can use source quality metadata to influence message scoring and digest ordering without hiding lower-trust source messages from audit output.

FR18: The system can detect repeated token or project signals across multiple messages and sources inside a digest window.

FR19: The system can track signal memory for tokens or projects across prior ingested messages, including first-seen time, latest-seen time, mention count, and source spread.

FR20: The digest can surface signal memory labels such as new, repeated, heating up, or cooling down based on current-window activity compared with prior activity.

FR21: The system can render source quality and signal memory context in the digest in a concise operator-readable format.

FR22: The system can provide a local CLI inspection path for source quality and signal memory calculations.

### NonFunctional Requirements

NFR1: The smoke test must be runnable locally without requiring production scheduling.

NFR2: Networked Telegram access must be isolated behind the ingestion adapter boundary and must not leak credentials.

NFR3: Tests must mock Telegram/network behavior unless an explicit live integration run is requested.

NFR4: The implementation must preserve the existing SQLite-first MVP architecture.

NFR5: Time-window digest generation must remain runnable locally from the CLI and be schedulable at 2-hour, 6-hour, and 12-hour cadences.

NFR6: Position extraction must be testable without live network access and must preserve source-message traceability for every classified signal.

NFR7: Source quality and signal memory behavior must remain SQLite-compatible and runnable in the existing CLI-oriented operating model.

NFR8: Source quality and signal memory calculations must be testable without live network access.

NFR9: Signal memory must preserve source traceability so digest claims can be audited back to source messages.

NFR10: The implementation must not add services, queues, schedulers, agents, orchestration layers, or frontend complexity.

NFR11: Source quality scoring must be transparent and deterministic enough for operators to understand why a source or signal was ranked higher.

### Additional Requirements

- Use existing project boundaries: `app/ingest`, `app/processing`, `app/summarization`, `app/cli.py`, and `app/db`.
- Keep Telegram credentials in environment variables and document them in `.env.example` if new variables are required.
- Do not add queues, workers, orchestration services, or frontend surfaces for this smoke test.
- Keep the result inspectable from the CLI.
- Keep the first time-window implementation compatible with SQLite and the existing CLI-oriented operating model.
- Do not remove raw high-score message audit output until a replacement audit/debug path exists.
- Keep source quality scoring simple and explicit; avoid ML ranking or opaque reputation models for this epic.
- Treat signal memory as local database-derived state rather than a new external service.
- Preserve existing digest commands and daily/window behavior while enriching their output.

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
- FR16 -> Story 3.1
- FR17 -> Story 3.1
- FR18 -> Story 3.3
- FR19 -> Story 3.2
- FR20 -> Story 3.3
- FR21 -> Story 3.3
- FR22 -> Story 3.5

## Epic List

1. Epic 1: Telegram Alpha Signal Smoke Test - Validate the first useful end-to-end alpha discovery slice: pull recent Telegram messages and confirm the system can surface a known signal. Covers FR1-FR10.
2. Epic 2: Time-Window Digest Format and Position Signal Extraction - Make the digest useful for intraday operation by supporting time-window runs, clearer operator-facing formatting, position signals, exports, and broadcast delivery. Covers FR11-FR15.
3. Epic 3: Source Quality Scoring and Signal Memory - Improve digest usefulness by ranking trusted sources, detecting repeated signals across sources, tracking first-seen/latest-seen tokens or projects, and showing concise signal-memory context in the digest without adding services or frontend complexity. Covers FR16-FR22.

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

## Epic 3: Source Quality Scoring and Signal Memory

Improve digest usefulness by ranking trusted sources, detecting repeated signals across sources, tracking first-seen/latest-seen tokens or projects, and showing concise signal-memory context in the digest without adding services or frontend complexity.

### Story 3.1: Rank Sources With Transparent Quality Scores

As a crypto alpha operator,
I want each source to have a simple quality score,
So that digest ranking can favor historically useful or trusted sources without hiding lower-trust material.

**Acceptance Criteria:**

**Given** sources exist in the digest database
**When** source quality metadata is calculated or loaded
**Then** each source has an operator-readable quality score or tier
**And** the score can be inspected without requiring network access.

**Given** messages are scored for digest inclusion
**When** a message comes from a higher-quality source
**Then** source quality can increase its ranking contribution in a deterministic way
**And** the ranking logic remains transparent enough to explain from local data.

**Given** a message comes from a lower-quality source
**When** a digest is built
**Then** the message is not silently discarded solely because of source quality
**And** it remains eligible for raw audit output when otherwise selected.

**Given** source quality inputs are absent or incomplete
**When** scoring runs
**Then** the system uses a documented neutral default
**And** existing digest generation continues to work.

### Story 3.2: Track Signal Memory Across Ingested Messages

As a crypto alpha operator,
I want the system to remember when tokens or projects were first and last seen,
So that I can tell whether a signal is new, repeated, or stale.

**Acceptance Criteria:**

**Given** ingested messages contain token or project entities
**When** signal memory is calculated
**Then** the system records or derives first-seen time, latest-seen time, total mention count, and source spread for each signal.

**Given** a signal appears in multiple historical messages
**When** memory is inspected
**Then** the system reports the earliest and latest observed message timestamps
**And** includes enough source/message identifiers to audit the calculation.

**Given** no prior messages exist for a token or project
**When** it appears in the current digest window
**Then** the signal can be classified as newly seen.

**Given** signal memory tests run locally
**When** test data is provided without live integrations
**Then** first-seen, latest-seen, mention count, and source spread behavior can be verified deterministically.

### Story 3.3: Detect Repeated Signals Across Sources

As a crypto alpha operator,
I want repeated token or project signals across multiple sources to be detected,
So that cross-source confirmation stands out in the digest.

**Acceptance Criteria:**

**Given** the same token or project appears in multiple messages inside a digest window
**When** repeated signal detection runs
**Then** the system groups those mentions into a repeated signal candidate.

**Given** repeated mentions come from distinct sources
**When** the repeated signal is scored
**Then** the system records the distinct source count
**And** the signal can be ranked above equivalent single-source mentions.

**Given** duplicate or near-identical content is ingested more than once
**When** repeated signal detection runs
**Then** duplicate content does not falsely inflate source spread or mention strength.

**Given** a repeated signal is detected
**When** digest context is prepared
**Then** the system preserves representative evidence from source messages for auditability.

### Story 3.4: Render Source Quality and Signal Memory in Digests

As a crypto alpha operator,
I want digest sections to show source quality and signal memory context concisely,
So that I can scan why a signal matters without reading raw messages first.

**Acceptance Criteria:**

**Given** a digest is built from messages with signal memory context
**When** the digest is rendered
**Then** token or project entries can include concise labels such as new, repeated, heating up, or cooling down.

**Given** a signal has prior history
**When** it appears in the digest
**Then** the rendered context includes first-seen or latest-seen information where useful
**And** does not overwhelm the existing operator-readable format.

**Given** a signal appears across multiple sources
**When** it is rendered in repeated signal sections
**Then** the digest shows source spread or source count in concise language.

**Given** the existing daily and window digest commands are used
**When** source quality and signal memory data are available
**Then** the enriched digest output remains compatible with both command paths.

**Given** raw audit output is enabled
**When** enriched digest context is rendered
**Then** source messages remain available for manual verification.

### Story 3.5: Inspect Source Quality and Signal Memory From the CLI

As a crypto alpha operator,
I want a local CLI inspection command for source quality and signal memory,
So that I can debug digest ranking and memory calculations without sending a digest.

**Acceptance Criteria:**

**Given** the operator runs a local inspection command
**When** source quality data exists
**Then** the command displays source identifiers, quality scores or tiers, and the basis used by the local calculation.

**Given** the operator requests memory for a token or project
**When** matching messages exist
**Then** the command displays first-seen time, latest-seen time, mention count, source spread, and representative source references.

**Given** no matching source quality or signal memory data exists
**When** the inspection command runs
**Then** the command reports a clear empty state instead of failing ambiguously.

**Given** the inspection command is executed locally
**When** it reads from the configured database
**Then** it does not require live Telegram, Discord, RSS, or LLM access.
