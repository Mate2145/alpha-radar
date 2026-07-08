# Story 1.4: Split long Telegram digest messages

Status: implemented

## Epic
Epic 1: Crypto Alpha Digest MVP Telegram delivery

## Story
As the digest delivery system, I want to split daily digest content into multiple Telegram messages when it exceeds the platform limit, so that long digests are still delivered successfully instead of failing with HTTP 400.

## Acceptance Criteria

1. `send_telegram_message` checks the digest length before sending.
2. If the digest is within Telegram's 4096-character limit, it sends as a single message (existing behavior).
3. If the digest is longer than 4096 characters, it is split into multiple messages at Markdown heading boundaries (h2 `## `), with each chunk staying under the limit.
4. If a single heading section exceeds the limit, it is split further at paragraph boundaries (blank-line-separated blocks), keeping each chunk under the limit.
5. Chunks preserve the original `# Crypto Alpha Digest - YYYY-MM-DD` title on the first chunk only; subsequent chunks do not repeat the title.
6. Each chunk is sent sequentially; if any chunk fails, the whole call raises a `RuntimeError` with the failing chunk index and the Telegram error detail.
7. A follow-up test verifies that a 5000-character digest is delivered in 2+ chunks.
8. Test coverage remains at or above 80%.

## Implementation Notes

- Telegram Bot API text limit: 4096 characters per message.
- Introduce `app/delivery/split_digest.py` with `split_by_headings(markdown: str, max_length: int = 4096) -> list[str]`; keep `split_digest` as the delivery-facing wrapper.
- Keep `send_telegram_message` as the public entry point; it calls the splitter and loops over chunks.
- Splitting strategy priority:
  1. Try entire message.
  2. Split on `\n## ` (h2 headings) boundaries.
  3. If a section is still too long, split on `\n\n` (paragraph) boundaries.
  4. If a paragraph is still too long, split hard at `max_length` as safety fallback.
- Add logging for number of chunks and per-chunk length.

## Test Expectations

- `test_split_by_headings_keeps_sections_under_limit`
- `test_split_by_headings_preserves_title_only_on_first_chunk`
- `test_send_long_digest_multiple_chunks`
- Existing telegram_send tests still pass.
