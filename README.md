# Alpha Digest

Alpha Digest is a self-hosted crypto alpha digest MVP. It ingests RSS now, keeps Telegram and Discord ingestion modular for credentials later, stores raw messages in SQLite, extracts basic entities, scores noisy messages, and builds a daily Markdown digest. Digest generation supports a rule-based fallback, OpenAI-compatible APIs, OpenRouter, and local Codex CLI runs.

## Architecture

- `app/ingest`: RSS and Telegram ingestion plus Discord stub.
- `app/db`: SQLAlchemy models and table creation.
- `app/processing`: content hashing, entity extraction, and rule scoring.
- `app/summarization`: OpenAI-compatible client, prompts, and fallback digest builder.
- `app/delivery`: Telegram Bot API delivery plus a Discord delivery stub.
- `app/cli.py`: Typer CLI commands exposed as `alpha`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alpha init-db
```

If you prefer plain requirements:

```bash
pip install -r requirements.txt
python -m app.main init-db
```

## Environment Variables

- `DATABASE_URL`: defaults to `sqlite:///data/alpha_digest.db`.
- `RSS_FEEDS`: comma-separated RSS feed URLs.
- `LLM_PROVIDER`: `fallback`, `openai`, `openrouter`, or `codex_cli`.
- `OPENAI_API_KEY`: required only when `LLM_PROVIDER=openai`.
- `OPENAI_BASE_URL`: OpenAI-compatible API base URL.
- `OPENAI_MODEL`: OpenAI model name for summaries.
- `OPENROUTER_API_KEY`: required only when `LLM_PROVIDER=openrouter`.
- `OPENROUTER_BASE_URL`: OpenRouter API base URL.
- `OPENROUTER_MODEL`: OpenRouter model name for summaries.
- `CODEX_COMMAND`: Codex CLI command, defaults to `codex`.
- `CODEX_MODEL`: optional Codex model override.
- `CODEX_TIMEOUT_SECONDS`: timeout for `codex exec`.
- `TELEGRAM_API_ID`: Telegram API ID for history reads via Telethon.
- `TELEGRAM_API_HASH`: Telegram API hash for history reads via Telethon.
- `TELEGRAM_SESSION_NAME`: local Telethon session path/name.
- `TELEGRAM_SOURCE_CHANNELS`: comma-separated Telegram source channels. The smoke test expects exactly two.
- `TELEGRAM_INGEST_LOOKBACK_HOURS`: lookback window for normal Telegram ingestion.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token for sending the digest.
- `TELEGRAM_CHAT_ID`: target Alpha Ingest Telegram channel or chat ID.

## LLM Providers

The default `LLM_PROVIDER=fallback` requires no external account and generates an extractive rule-based digest.

For OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=openai/gpt-4o-mini
```

For Codex CLI with your ChatGPT/Codex subscription, sign in locally first:

```bash
codex login
```

Then set:

```env
LLM_PROVIDER=codex_cli
CODEX_MODEL=
```

`codex_cli` shells out to `codex exec --ephemeral`, passes the digest source messages on stdin, and stores the final stdout as the daily summary. It is best for local runs, not unattended production scheduling.

Check the configured summarizer before a full digest run:

```bash
alpha check-llm
```

For an AI-written Telegram digest through Codex CLI:

```bash
alpha ingest-all
alpha check-llm
alpha build-digest --date YYYY-MM-DD
alpha export-digest --date YYYY-MM-DD
alpha send-digest --date YYYY-MM-DD
```

`export-digest` writes `data/digest-YYYY-MM-DD.md` by default for local inspection.

## Adding RSS Sources

Edit `.env` and set `RSS_FEEDS`:

```env
RSS_FEEDS=https://example.com/feed.xml,https://another.example/rss
```

`alpha ingest-rss` creates or updates matching `sources` rows automatically.

## Commands

```bash
alpha init-db
alpha ingest-rss
alpha ingest-all
alpha check-llm
alpha build-digest --date 2026-07-08
alpha build-window-digest --since-hours 6
alpha build-window-digest --from 2026-07-08T06:00:00 --to 2026-07-08T12:00:00
alpha export-digest --date 2026-07-08
alpha send-digest --date 2026-07-08
alpha smoke-telegram-signal --lookback-hours 24 --expected-signal '$cashchat'
```

Recommended daily schedule:

```bash
alpha ingest-all
alpha build-digest --date YYYY-MM-DD
alpha send-digest --date YYYY-MM-DD
```

For scheduled intraday summaries, build a separate time-window digest without overwriting the daily summary:

```bash
alpha ingest-all
alpha build-window-digest --since-hours 6
```

Use `--since-hours 2`, `--since-hours 6`, or `--since-hours 12` for rolling scheduled windows, or pass explicit ISO datetimes with `--from` and `--to`.

## Docker Compose

```bash
cp .env.example .env
docker compose build
docker compose run --rm alpha-digest init-db
docker compose run --rm alpha-digest ingest-all
docker compose run --rm alpha-digest build-digest --date 2026-07-08
docker compose run --rm alpha-digest send-digest --date 2026-07-08
```

## Telegram Signal Smoke Test

The MVP Telegram smoke test checks exactly two configured channels over the last 24 hours and reports whether a Robinhood-related `$cashchat` signal is present.

Configure:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_NAME=data/alpha_digest_telegram
TELEGRAM_SOURCE_CHANNELS=@channel_one,@channel_two
TELEGRAM_INGEST_LOOKBACK_HOURS=24
```

Run:

```bash
alpha smoke-telegram-signal --lookback-hours 24 --expected-signal '$cashchat'
```

This uses Telethon because the Telegram Bot API cannot fetch arbitrary historical channel messages unless the bot already received those updates.

The normal digest pipeline also uses the same source channel configuration:

```bash
alpha ingest-all
alpha build-digest --date YYYY-MM-DD
alpha send-digest --date YYYY-MM-DD
```

`alpha ingest-all` persists Telegram messages into the same SQLite message table as RSS, so `build-digest` summarizes Telegram and RSS messages together.

## MVP Limitations

- Telegram ingestion uses Telethon user/session credentials to read configured channel history.
- Discord ingestion and delivery are stubs.
- Entity extraction is currently regex/keyword-based, not a full crypto-aware extraction algorithm.
- Deduplication is based on normalized content hash only.
- Scoring is rule-based and intentionally simple.
- SQLite is the default store and is best for a single-node MVP.
- The fallback digest is extractive and less useful than the LLM summary.

## Next Steps

- Add Telegram ingestion for your Alpha Ingest channel and any source channels you control.
- Add Discord bot ingestion for selected servers and channels.
- Replace or augment primitive entity extraction with a crypto-aware algorithm covering token/project aliases, contract addresses, chains, protocols, exchanges, and contextual risk/opportunity signals.
- Add a time-window digest format that keeps `Executive Summary`, one-sentence `Top Narratives`, `Most Mentioned Tokens / Projects`, `Repeated Signals Across Sources`, `Links Worth Reviewing`, and a temporary `Raw High-Score Messages` audit section. Rename `Potential Opportunities` to `Open Positions` and classify bought/opened/accumulated positions with a green dot and sold/closed/reduced positions with a red dot.
- Use n8n, cron, or systemd timers to schedule ingestion, digest generation, and delivery.
- Add source quality tuning and per-source configuration.
- Migrate to Postgres when multiple workers, larger volume, or hosted analytics are needed.
