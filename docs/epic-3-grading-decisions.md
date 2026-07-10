# Epic 3 Grading Decisions

This document captures the design decisions from the Epic 3 grilling session about source quality scoring, signal memory, and Codex CLI grading.

## Scope Direction

Epic 3 should focus first on a Codex CLI grading workflow rather than rewriting the existing deterministic scoring formula.

The existing scoring code should stay mostly unchanged for now. The app should prepare the best available Telegram and signal context, hand it to Codex CLI as structured files, receive structured JSON grading output, validate that output, and later use it in digests or persistence once the loop proves useful.

## Decisions

### 1. Signal Memory Is Derived

Signal memory should be computed on demand from existing `messages` and `extracted_entities` rows, not stored in a dedicated `signal_memory` table for Epic 3.

Rationale:

- Existing rows already contain source, timestamp, content hash, and extracted entities.
- A persisted memory table would introduce cache invalidation when extraction, dedupe, or historical data changes.
- Derived memory keeps the first implementation simpler and easier to audit.

### 2. Signal Identity Uses Tickers And Contract Addresses

The primary signal identifiers are:

- Tickers, such as `$SOL` or `$TIA`.
- Contract addresses, primarily EVM and Solana addresses.

Keywords remain context only. They should not be treated as primary signal identities in Epic 3.

### 3. Contract Address Is A Separate Entity Type

Contract addresses should be extracted as a distinct entity type:

```text
contract_address
```

They should not be stored as tickers.

Initial regex direction:

- EVM: `0x` followed by 40 hex characters.
- Solana: base58-like address, roughly 32-44 characters, excluding ambiguous characters such as `0`, `O`, `I`, and `l`.

### 4. Ticker And Contract Pairing Is Proximity-Based

If a ticker and a contract address appear close together in the same message, they can be treated as one signal.

If they are far apart, ambiguous, or there are multiple possible ticker/contract pairs, the system should avoid automatic pairing and keep them as separate signals.

The pairing distance should be configurable.

Proposed default:

```env
SIGNAL_PAIRING_MAX_DISTANCE=120
```

### 5. Contract Address Wins As Main Key

When a ticker and contract address are paired, the contract address is the primary signal key and the ticker is an alias/context value.

Rules:

- Only ticker: `ticker:$ABC`
- Only contract: `contract_address:0x...`
- Paired ticker + contract: `contract_address:0x...`, alias `$ABC`

### 6. Signal Labels Are Computed

Digest labels should be computed from current and previous window data, not stored as permanent state.

Definitions:

- `new`: first known occurrence is inside the current digest window.
- `repeated`: appears in at least two messages in the current window.
- `cross-source`: appears from at least two distinct sources in the current window.
- `heating up`: current window mention count is greater than the previous same-length window.
- `cooling down`: current window mention count is lower than the previous same-length window.

### 7. Cross-Source Means Distinct Source ID

For Epic 3, `cross-source` means the signal appears across distinct `Source.id` values.

Known limitation:

- If the same Telegram channel is represented as multiple source records through aliases, Epic 3 will treat them as separate sources. Source aliasing/merging is out of scope for now.

### 8. No Fuzzy Dedupe In Epic 3

Repeated and cross-source calculations should rely only on the existing `content_hash` dedupe behavior.

No near-duplicate or fuzzy duplicate detection should be added in Epic 3.

Rationale:

- Fuzzy dedupe can suppress real cross-source confirmation.
- It adds complexity outside the core signal memory and grading loop.
- A later epic can add near-duplicate detection if needed.

### 9. Source Quality Has VIP Config Plus Future Feedback

Source quality should have two layers:

1. A config-based VIP/trusted source list controlled by the operator.
2. A future feedback loop for non-VIP sources based on observed performance.

Epic 3 should focus on the config-based trusted source mechanism and leave automated performance scoring for later.

### 10. Trusted Source Config Is Telegram-Focused YAML

The first trusted source config should be a YAML file optimized for Telegram channel names.

Proposed path:

```text
config/trusted_sources.yaml
```

Optional env:

```env
TRUSTED_SOURCES_CONFIG=config/trusted_sources.yaml
```

Example:

```yaml
telegram:
  vip:
    - channel: "@smartmoneyalpha"
      quality_score: 3.0
      reason: "High signal quality"
  trusted:
    - channel: "@earlycalls"
      quality_score: 2.0
      reason: "Usually early"
  watchlist:
    - channel: "@maybeuseful"
      quality_score: 1.2
      reason: "Needs more observation"
```

### 11. Configured But Unseen Sources Do Not Create DB Rows

If a Telegram channel appears in `trusted_sources.yaml` but has not been ingested yet, the app should not create a `Source` row just because it is configured.

Behavior:

- CLI inspection should show it as configured but not seen.
- When ingestion first sees the channel, its `Source` row should receive the configured trusted source score.

### 12. Trusted Source YAML Is Authoritative

For Telegram sources listed in `trusted_sources.yaml`, the YAML `quality_score` is authoritative.

Behavior:

- If a source is listed in YAML, the YAML score wins over any existing DB score.
- Inspection should show `score_source: trusted_sources.yaml`.
- Future feedback scoring should apply only to non-configured sources.

### 13. Codex CLI Grading Is The Main Epic 3 Direction

Epic 3 should introduce a Codex CLI grading workflow.

The app should:

1. Select candidate signals.
2. Build structured grading input.
3. Include the latest raw messages for context.
4. Ask Codex CLI to produce grading JSON.
5. Validate the output JSON.
6. Keep valid output for later digest/persistence use.

This should be prepared for a future multi-step loop, but the first version should stay controlled and file-based.

### 14. Grading Is A Separate CLI Command

The first grading implementation should be a separate command, likely:

```bash
alpha grade-signals --since-hours 6
```

It should not be hidden inside `build-window-digest` at first.

Rationale:

- Easier debugging.
- Easier inspection of input/output files.
- Digest build can continue without grading.
- Validator can be tested independently.

Future direction:

- A Codex-facing CLI or API module may allow Codex to query read-only DB data dynamically.
- That is out of scope for the first grading loop.

Preferred model:

- Use `gpt-5.4-mini` for Codex CLI grading tasks when available through the local Codex CLI.
- Keep the model configurable through `CODEX_MODEL`; do not hard-code the model in application logic.
- If the configured local Codex CLI cannot run `gpt-5.4-mini`, the command should fail clearly through the existing Codex error path rather than silently switching models.

### 15. Grading Output Starts As Files

Codex grading output should initially be stored in files, not DB.

Proposed paths:

```text
data/signal-grading/output/latest.json
data/signal-grading/output/YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json
```

Later, once the workflow proves useful, valid grades can be persisted to DB with history, prompt version, and schema version.

### 16. Market Data Is A Later Command

Market cap, price, and price change lookup are out of scope for grading schema v1.

Those should be implemented later as a separate command or enrichment step.

### 17. Grading JSON Schema V1

The first output schema should be intentionally small.

Required top-level fields:

```json
{
  "schema_version": "1.0",
  "window": {
    "start": "2026-07-10T12:00:00",
    "end": "2026-07-10T18:00:00"
  },
  "grades": []
}
```

Each grade should include:

```json
{
  "signal_type": "ticker",
  "signal_key": "$ABC",
  "aliases": [],
  "chain": "unknown",
  "source_message_ids": ["db:123"],
  "grade": "A",
  "confidence": 0.82,
  "priority": "high",
  "summary": "Strong repeated signal across VIP Telegram sources.",
  "reasoning": [
    "Mentioned by 2 VIP sources."
  ],
  "risk_flags": [
    "Low liquidity not verified."
  ],
  "recommended_action": "review"
}
```

Allowed value direction:

- `signal_type`: `ticker` or `contract_address`
- `chain`: `evm`, `solana`, or `unknown`
- `grade`: `A`, `B`, `C`, `D`, or `ignore`
- `confidence`: float from `0.0` to `1.0`
- `priority`: `high`, `medium`, `low`, or `ignore`
- `recommended_action`: `review`, `watch`, or `ignore`

### 18. Source Message IDs Use DB IDs

In grading JSON, `source_message_ids` should use this format:

```text
db:{message.id}
```

Example:

```json
"source_message_ids": ["db:123", "db:124"]
```

### 19. Grading Input Has Structured Signals And Raw Messages

The Codex grading input should include both structured signal candidates and raw message context.

Proposed input shape:

```json
{
  "schema_version": "1.0",
  "task": "grade_crypto_signals",
  "window": {
    "start": "2026-07-10T12:00:00",
    "end": "2026-07-10T18:00:00"
  },
  "signals": [
    {
      "signal_type": "contract_address",
      "signal_key": "0x1234567890abcdef1234567890abcdef12345678",
      "aliases": ["$ABC"],
      "chain": "evm",
      "labels": ["new", "repeated", "cross-source"],
      "first_seen": "2026-07-10T12:15:00",
      "latest_seen": "2026-07-10T17:45:00",
      "mention_count": 4,
      "source_count": 2,
      "vip_source_count": 1,
      "source_message_ids": ["db:123", "db:124"]
    }
  ],
  "raw_messages": [
    {
      "id": "db:123",
      "created_at": "2026-07-10T12:15:00",
      "source": "@alpha",
      "source_tier": "vip",
      "score": 7.5,
      "content": "Buying $ABC CA: 0x123..."
    }
  ]
}
```

### 20. Grading Input And Output Are File-Based

The grading command should write input JSON to disk before invoking Codex CLI.

The Codex CLI should receive the input file path and write an output JSON file.

Proposed folder structure:

```text
data/signal-grading/
  input/
    latest.json
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json
  output/
    latest.json
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.json
  invalid/
    YYYYMMDDTHHMMSS-YYYYMMDDTHHMMSS.invalid.json
```

Rationale:

- Auditability: exact Codex input and output are preserved.
- Debuggability: bad outputs can be inspected.
- Reproducibility: the same input can be rerun.
- Multi-step loops become easier.

Guardrails:

- Validate input schema before calling Codex.
- Validate output schema before accepting Codex results.
- Limit raw messages, signal candidates, and message content length.
- Add retention later if file growth becomes a problem.

Proposed limits:

- `raw_messages`: latest/top 80 messages.
- `signals`: top 30 candidates initially.
- `content`: truncate per message, for example 1000 characters.

### 21. Invalid Grading Output Fails The Command But Preserves Last Valid Output

If Codex CLI writes invalid grading JSON, `alpha grade-signals` should fail with a non-zero exit code.

Behavior:

- Save or move the invalid output under `data/signal-grading/invalid/`.
- Do not update `data/signal-grading/output/latest.json`.
- Preserve the previous valid `output/latest.json` if one exists.
- Report the validation error clearly to the operator.
- Do not block digest building automatically, because digest generation remains a separate command.

Rationale:

- The grading command should be honest about invalid structured output.
- Operators need the invalid file for debugging prompt/schema issues.
- Keeping the last valid output avoids replacing good grading context with bad data.
- Separating grading failure from digest build preserves the current reliable digest path.

## Open Questions For Next Session

1. Should `grade-signals` choose raw messages by latest timestamp, score, or a blend?
2. Should signal candidates be selected before or after source quality YAML is applied?
3. What exact prompt should Codex CLI receive for writing valid JSON?
4. Should the validator be a hidden helper command or public CLI command?
5. Should the current Epic 3 stories be revised to make Codex grading the first story?
