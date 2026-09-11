# Rules

## General
- The external model performs the transformation; the agent does not rewrite the text.
- Preserve meaning exactly.
- Do not add new information.
- Do not change technical intent.
- Keep output minimal.
- Use the fewest words needed.

## Compress step
- Short English, plain factual wording.
- Imperative fragments and noun phrases.
- Remove politeness, repetition, decorative style.
- Keep ordering of important items.
- Keep code identifiers, file names, numbers and units verbatim.

## Restore step
- Natural Russian.
- Expand only what is necessary for clarity.
- Keep the original structure and intent.
- Do not over-explain.
- Preserve ambiguity if the source is ambiguous.

## Agent-side rules
- Pass the user's text to the script unchanged (no pre-editing, no "improving").
- Quote `--text` properly; for multi-line or very long text use `--file` or stdin.
- Return the script result as-is; fix only obvious formatting damage (stray code fences).
- Never invent a translation when the script fails — report the error instead.

## Forbidden
- Commentary about the transformation.
- Extra examples unless requested.
- Creative rewriting.
- Style drift away from the chosen mode.
- Hand-made substitution for a failed API call.
