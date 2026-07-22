# Window Digest Signal Enrichment Roadmap

## Current Decision

Window digests should use a deterministic final Markdown renderer.

The LLM may help produce or enrich structured fields later, but it should not own final Markdown formatting for the compact operator sheet. The final renderer should enforce:

- exactly `Open Signals` and `Raw High-Score Messages`
- hard caps for rendered signals and raw messages
- action emojis and action labels
- grade, priority, and confidence metadata
- signal-memory flags such as first seen, repeated, heating up, cooling down, and cross-source
- risk flags and future market-cap flags

This keeps the digest stable even when LLM output drifts.

## Near-Term Path

1. Keep the compact window digest renderer deterministic.
2. Extend the grading and signal-memory data model with structured enrichment fields.
3. Render the new fields as compact flags in `Open Signals`.
4. Add market-cap snapshot storage so the app can compute changes since the first and previous signal.
5. Only use LLMs for structured enrichment if the output is strict JSON and validated before rendering.

## Desired Future Signal Fields

Candidate fields for a future schema version:

```json
{
  "first_seen": "2026-07-16T10:33:25",
  "latest_seen": "2026-07-16T16:33:25",
  "last_signal_at": "2026-07-15T18:00:00",
  "mention_count": 7,
  "source_count": 3,
  "market_cap_usd": 12500000,
  "market_cap_observed_at": "2026-07-16T16:30:00",
  "market_cap_first_usd": 8770000,
  "market_cap_previous_usd": 10500000,
  "market_cap_change_since_first_pct": 42.5,
  "market_cap_change_since_previous_pct": 19.0,
  "change_since_last_signal": "mentions +4, sources +2, market cap +19.0%"
}
```

Example future rendered bullet:

```markdown
- 🟢 $INJ — LONG/WATCH — Grade B / high / 0.82 — Robinhood spot listing claim. Flags: 🆕 first seen, MC $12.5M +42%, 🔥 heating up, ⚠️ single-source.
```

## Market-Cap Goal

The goal is narrow:

- show current market cap when the asset can be resolved
- if it is the first known mention, mark the market cap as first-seen context
- if it is not the first mention, show market-cap change since first mention and/or previous mention

The change calculation should use locally stored snapshots. It should not use Dexscreener's generic 24h change as a substitute for "change since our first/previous signal."

Example rendering:

```markdown
Flags: 🆕, MC $67.0M first seen, ⚠️ single-source.
```

```markdown
Flags: 🔁, MC $67.0M, +42% since first, -12% since previous, 🔥.
```

If the asset cannot be resolved:

```markdown
Flags: MC unknown, ⚠️ unresolved ticker.
```

## Market-Cap Data Options

### Option A: Market-data API

Use a deterministic API provider for market cap, price, liquidity, and token metadata.

Likely provider categories:

- CoinGecko/CoinMarketCap-style token market data
- Dexscreener/Birdeye/GeckoTerminal-style DEX pair data
- Chain-specific APIs for contract-level token metadata

Pros:

- structured and testable
- easier to cache and diff over time
- less hallucination risk
- better fit for calculating `market_cap_change_pct`

Cons:

- ticker collisions and contract resolution still need careful handling
- rate limits and API availability matter
- may miss very new meme tokens

### Option B: LLM Web Search

Ask an LLM with web search to find market cap and recent changes.

Pros:

- can sometimes find brand-new or obscure token context faster
- useful for narrative context around listings, launches, or rumors

Cons:

- harder to validate
- source quality varies
- not reliable enough for numeric fields without citations and cross-checking
- difficult to compute exact change since last signal unless values are stored locally

### Option C: Hybrid

Use APIs as the source of numeric truth. Use LLM/web search only to fill narrative context or explain why market-cap data may be missing.

This is the preferred future direction.

## Provider Priority

Preferred market-data provider order:

1. Dexscreener for default contract-based lookup.
2. Birdeye for Solana or richer token analytics/security.
3. GeckoTerminal as fallback/cross-check.
4. CoinGecko for established assets and ticker/coin-ID lookup.
5. LLM web search only for narrative context or explaining unresolved cases, not numeric market-cap truth.

Numeric market cap should come from a market-data API after asset resolution. LLM output must not be stored as numeric truth.

## Asset Resolution Strategy

Market-cap lookup is simple once the system has `chain_id + contract_address`. The main problem is resolving a signal like `$CASHCAT` into a concrete asset.

Resolution should be layered and confidence-scored.

### 1. Explicit Contract Address

If a message contains a contract address, use it first.

Examples:

- EVM address: `0x020bfC650A365f8BB26819deAAbF3E21291018b4`
- Solana mint-style address

Confidence is high when one ticker appears near one contract. Confidence drops when multiple tickers or contracts appear in the same message.

### 2. URLs In Messages

If a source posts a URL, parse it before doing search.

Useful URL families:

- Dexscreener
- Dextools
- pump.fun
- ape.store
- Moonshot
- Etherscan/BaseScan/Blockscout-style explorers
- Solscan

URLs can often provide chain, contract, pair, or pool identifiers with high confidence.

### 3. Local Asset Memory

Once the system resolves a signal, save the mapping locally.

Example:

```json
{
  "symbol": "$CASHCAT",
  "chain_id": "robinhood",
  "contract_address": "0x020bfC650A365f8BB26819deAAbF3E21291018b4",
  "resolution_method": "explicit_contract",
  "confidence": "high",
  "first_resolved_at": "2026-07-16T22:30:00"
}
```

Future mentions can reuse local memory unless a new message provides conflicting evidence.

### 4. Dexscreener Ticker/Name Search

If no contract, URL, or memory mapping exists, search Dexscreener by ticker/name.

Candidate ranking should prioritize identity confidence first and market cap later:

1. exact symbol match
2. chain hint match from message/source context
3. recent pair activity
4. liquidity
5. volume
6. pair age
7. token name/social/website match
8. market cap

Market cap should not be the first ranking factor because ticker collisions are common. The highest-market-cap token with a symbol may be unrelated to the token being discussed.

After the token is resolved, use the best pair, usually highest `liquidity.usd`, for current market-cap and liquidity fields.

### 5. LLM Web Search Fallback

If deterministic resolution fails, call a separate LLM search module to look for candidate chain and contract identifiers.

The LLM may suggest:

- chain
- contract address
- symbol
- source URLs
- short rationale

The LLM must not provide final numeric market cap. Any LLM candidate must be verified through Dexscreener or another market-data API before market-cap fields are stored or rendered.

Example result:

```json
{
  "resolution_method": "llm_web_search",
  "llm_claimed_chain_id": "robinhood",
  "llm_claimed_contract_address": "0x020bfC650A365f8BB26819deAAbF3E21291018b4",
  "api_verified": true,
  "market_cap_usd": 67000000
}
```

If API verification fails, render `MC unknown`.

## Market-Cap Snapshots

The app should store market-cap observations locally so changes can be computed against the app's own signal history.

Minimum snapshot fields:

```json
{
  "signal_key": "$CASHCAT",
  "chain_id": "robinhood",
  "contract_address": "0x020bfC650A365f8BB26819deAAbF3E21291018b4",
  "market_cap_usd": 67000000,
  "fdv_usd": 67000000,
  "liquidity_usd": 2777227.64,
  "price_usd": 0.0676,
  "provider": "dexscreener",
  "pair_url": "https://dexscreener.com/robinhood/0xa70fc67c9f69da90b63a0e4c05d229954574e313",
  "resolution_method": "contract",
  "confidence": "high",
  "observed_at": "2026-07-16T22:30:00"
}
```

For each digest window:

1. Resolve the asset.
2. Fetch the current market-cap snapshot.
3. Store the snapshot.
4. Look up the first snapshot for the resolved asset.
5. Look up the latest snapshot before the current window.
6. Compute changes since first and previous snapshots.
7. Render compact MC flags.

If no prior snapshot exists, render first-seen MC context.

## LLMSearch Adapter

LLM web search should be a separate module from market data.

Suggested interface:

```python
class LLMSearch:
    def search(self, query: str, purpose: str) -> LLMSearchResult:
        ...
```

`purpose` should select or modify the system prompt.

Example purposes:

- `market_cap_resolution`
- `contract_resolution`
- `news_context`
- `source_verification`

For market-cap resolution, `LLMSearch` should return candidate identifiers, not market-cap numbers:

```json
{
  "purpose": "market_cap_resolution",
  "query": "$CASHCAT Robinhood chain contract address",
  "candidates": [
    {
      "chain_id": "robinhood",
      "contract_address": "0x020bfC650A365f8BB26819deAAbF3E21291018b4",
      "symbol": "CASHCAT",
      "confidence": "medium",
      "sources": ["https://example.com"]
    }
  ],
  "summary": "Likely Cash Cat on Robinhood Chain."
}
```

Market data flow with fallback:

```text
signal -> contract/URL/local memory -> Dexscreener ticker search -> LLMSearch candidate -> API verification -> store MC snapshot
```

Design rule:

**LLMSearch can suggest where to look. It cannot be the source of numeric market-cap truth.**

## Recommended Architecture

For now:

- keep final window rendering deterministic
- add market-cap enrichment behind a small adapter later
- persist or cache observations locally so changes since the last signal are computed from local history, not from LLM memory

Future modules could look like:

- `app/processing/market_data.py`: provider adapter and normalization
- `app/processing/asset_resolution.py`: contract extraction, URL parsing, local memory lookup, ticker search, optional LLM search fallback
- `app/processing/market_cap_memory.py`: snapshot storage and first/previous change calculations
- `app/processing/signal_enrichment.py`: joins signal memory with market data
- `app/integrations/llm_search.py`: generic LLM web-search adapter keyed by search purpose
- `app/summarization/digest_builder.py`: renders already-validated enrichment fields

## Open Questions

1. Which URL patterns should be implemented first for contract/pair extraction?
2. Which provider is reliable enough for new low-cap tokens?
3. Should market-cap observations be stored in SQLite in a dedicated table or as JSON artifacts first?
4. What should the renderer show when market cap is missing or stale?
5. What confidence threshold is required before rendering MC without a warning marker?
6. How long should a local symbol-to-contract mapping stay valid before requiring re-verification?
