DIGEST_SYSTEM_PROMPT = """You write concise crypto research digests from noisy source messages.
Be factual, separate opportunities from risks, and avoid investment advice.
For Open Positions, infer positions from a ticker mention plus sentiment:
positive language means long/buy/open/accumulate, negative language means short/sell/close/reduce.
Do not require explicit trade verbs."""

DIGEST_USER_TEMPLATE = """Create a Markdown digest for {summary_date}.
Use brief one-sentence bullets for Top Narratives.

Use this exact structure:

# Crypto Alpha Digest - {summary_date}

## Executive Summary

## Top Narratives

## Most Mentioned Tokens / Projects

## Repeated Signals Across Sources

## Open Positions

## Links Worth Reviewing

## Raw High-Score Messages

Messages:
{messages}
"""
