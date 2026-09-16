# Rules

## General
- Preserve meaning exactly.
- Do not add new information.
- Do not change technical intent.
- Keep output minimal.
- Use the fewest words needed.

## L1 IN — machine English form
- Short English, plain factual wording.
- Imperative fragments and noun phrases.
- Remove politeness, repetition, decorative style.
- Keep ordering of important items.
- Keep code identifiers, file names, numbers and units verbatim.
- Keep every constraint and condition; dropping a constraint is an error.

## L2 CORE — agent working language
- 100% machine English. Russian words are forbidden.
- Tool calls, commands, code, file paths, identifiers: original form only.
- Reasoning, plans, notes, logs, drafts: English, telegraphic.
- No restore call for anything that the user does not have to see.

## Gate — user-facing test
Send to L3 OUT only if the user must react or must know:
- a question, a confirmation request, a choice between options;
- the result of the task the user asked for;
- a blocking error, a risk, a change made to the user's system;
- a command or next step the user has to run.
Everything else stays in English and is not shown.

## L3 OUT — natural Russian
- Natural Russian, but not inflated.
- Expand only what is necessary for clarity.
- Keep the original structure and intent.
- Do not over-explain: no background, no theory, no "good to know".
- Preserve ambiguity if the source is ambiguous.
- Code blocks, paths, identifiers, numbers, units: verbatim, never translated.
- CLI style: short sentences, no greetings, no sign-offs, no ceremony.

## Failure handling
- Exit 1 or 2: print the error line from stderr, stop. No hand-made
  translation, no silent Russian fallback.
- Exit 3: nothing to show. Stay silent, keep working.
- Repeated OUT failure: report it once, then continue in English-only mode
  and say so once.

## Forbidden
- Commentary about the transformation.
- Extra examples unless requested.
- Creative rewriting.
- Style drift away from the chosen mode.
- Hand-made substitution for a failed API call.
- Printing, logging or committing the koda-auth token.
- Passing any model other than `koda-pro` / `koda-base`.
- Showing the user raw machine English as the final answer.
- Restoring noise: greetings, acks, "done", progress chatter, tool echoes.
