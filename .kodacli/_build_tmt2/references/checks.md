# Checks

## Before running the script
- Mode resolved (explicit `mode=...` or inferred from wording).
- User text passed to the script unchanged.
- Long or multi-line text sent via `--file`/stdin, not via `--text`.

## Script exit codes
- `0` — pipeline completed, blocks printed.
- `1` — a pipeline step failed (API error, bad response shape).
- `2` — configuration error: no `API_KEY` or empty input text.

## After running the script
- Required block present: `[COMPRESS]` for compress, `[RESTORE]` for restore/roundtrip/ask.
- No `API_KEY` value anywhere in the output.
- Meaning preserved: no added facts, no dropped constraints.
- Structure preserved: lists stay lists, identifiers and numbers unchanged.
- Russian output reads naturally (not machine-calqued) for restore/roundtrip/ask.
- Length sane: compressed form is not longer than the source.

## Failure handling
- Exit 2 with "API_KEY не найден": check `.env` location (script searches upward from CWD)
  or pass `--env <путь>`. Do not paste the key into chat.
- Exit 1 with 429: rate limit, retries already exhausted — suggest waiting, then rerun.
- Exit 1 with network error: verify routerai.ru availability and key validity.
- Never substitute a hand-made translation for a failed call.

## Sanity test without spending tokens
`--dry-run` builds the pipeline and prints truncated placeholders instead of API calls.
Use it to verify paths, venv and arguments before a real run.
