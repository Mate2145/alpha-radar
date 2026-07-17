# Public Meme Coin Dashboard Plan

## Direction

Use the laptop as the private ingestion, grading, and enrichment engine. Publish static or read-only dashboard artifacts every 5 hours.

Recommended shape:

```text
Laptop job every 5h
  -> ingest Telegram
  -> grade/enrich signals
  -> resolve market-cap snapshots
  -> write public JSON artifacts
  -> deploy/sync to Vercel dashboard

Vercel React dashboard
  -> reads static JSON
  -> renders heatmap, signal table, token detail pages, and latest digest
```

Telegram should remain an alert surface, not the primary public dashboard.

## Why Dashboard First

A public dashboard is better than Telegram for:

- browsing many tokens
- filtering and sorting signals
- heatmaps
- historical context
- market-cap and mention trend display
- source/evidence inspection
- sharing a public URL

Telegram is still useful for hot alerts, but it is not enough for public discovery or analysis.

## Recommended Product Split

Use both surfaces:

- Vercel React dashboard: public product surface.
- Telegram channel/bot: push alerts for hot signals only.

## Initial Architecture

Keep Vercel simple and static at first.

Laptop responsibilities:

- Telegram ingestion
- signal extraction
- grading
- market-cap resolution
- market-cap snapshot storage
- public JSON artifact generation
- deploy/sync command

Vercel responsibilities:

- host React frontend
- serve or bundle static JSON artifacts
- render read-only public views

Do not expose Telegram credentials, local DB access, or scraping logic from Vercel.

## Public Artifact Shape

Candidate files:

```text
data/public/latest.json
data/public/signals.json
data/public/tokens.json
data/public/heatmap.json
data/public/runs/YYYYMMDDTHHMMSS.json
```

The React dashboard should read these artifacts directly.

## First Dashboard Views

### 1. Heatmap

Show tokens sized and colored by signal strength.

Possible encodings:

- size: mention count, source count, or score
- color: market-cap change, grade, or trend
- border/icon: risk flags or unresolved market cap

### 2. Signal Table

Columns:

- token/signal
- grade
- action
- priority/confidence
- mentions
- sources
- market cap
- market-cap change since first/previous mention
- flags
- latest seen

### 3. Token Detail

For each token:

- first seen
- latest seen
- mention history
- source spread
- market-cap snapshots
- change since first/previous signal
- raw evidence messages
- resolution method/confidence

### 4. Latest Digest

Render the compact window digest as a readable latest-summary page.

## Avoid Initially

Avoid these until the static dashboard proves useful:

- public write APIs
- live backend
- auth
- queues
- real-time updates
- server-side scraping from Vercel
- user accounts/watchlists
- complex deployment infrastructure

## Later Evolution

If the dashboard grows:

- move ingestion from laptop to VPS or scheduled worker
- move snapshots to Postgres/Supabase
- add API endpoints
- add watchlists and alerts
- add paid/private views if needed

## Current Recommendation

Build:

```text
Laptop batch engine + static Vercel React dashboard + Telegram hot-alert channel
```

This keeps the system simple, protects private credentials, and gives a public product surface without committing to backend infrastructure too early.
