# Modes

All transformations are executed by the external model via `scripts/tmt.py`.
The agent only selects the mode, launches the script and delivers the result.

## compress
Input: natural Russian text.
Pipeline: RU -> EN machine (1 API call).
Return to user: `[COMPRESS]`.

## restore
Input: compact machine-style English.
Pipeline: EN machine -> RU (1 API call).
Return to user: `[RESTORE]`.

## roundtrip (default)
Input: natural Russian text.
Pipeline: RU -> EN machine -> RU (2 API calls).
Return to user: `[RESTORE]`; `[COMPRESS]` only on request.

## ask
Input: a Russian request that expects an answer.
Pipeline: RU -> EN machine -> model answer in EN machine -> RU (3 API calls).
Return to user: `[RESTORE]` (the Russian answer); `[ANSWER-EN]` only on request.

## Auto-selection
- Russian input + "shorten / compress / machine style" -> `compress`
- Telegraphic English input + "restore / translate back / expand" -> `restore`
- "show both forms", "check the roundtrip" -> `roundtrip`
- a question or task phrased in Russian + "through machine English" / "via Step-3.5-Flash" -> `ask`
- explicit `mode=...` always wins
- if still unclear -> ask one short clarifying question

## Cost note
Each step is a paid API call (11 RUB / 1M input, 33 RUB / 1M output tokens).
Prefer the smallest mode that satisfies the request: `compress` or `restore`
over `roundtrip`, `roundtrip` over `ask`.
