---
name: text-mode-translator_2
description: Auto-routing two-way translator. Sends Russian compress-requests to Step-3.5-Flash (routerai.ru) and returns the restored natural Russian answer.
---

# Purpose
Automatic pipeline around the external model `stepfun/step-3.5-flash` (RouterAI):

- `compress`: RU text -> compact machine English (done by the external model, not by the agent)
- `restore`: compact machine English -> natural Russian (done by the external model)
- `roundtrip`: RU -> EN machine -> RU (default)
- `ask`: RU -> EN machine -> model answer in EN machine -> RU answer here

Unlike v1 (`text-mode-translator`), the agent never performs the transformation itself.
Every transformation goes through `scripts/tmt.py`.

# Activation (automatic)
Use this skill WITHOUT waiting for an explicit request when the user:
- writes `mode=compress`, `mode=restore`, `mode=roundtrip` or `mode=ask`
- asks to compress / shorten / normalize Russian text into machine English
- asks to restore / expand machine English back into Russian
- asks to run a request through Step-3.5-Flash in machine-English form

Mode selection:
- input is Russian + "shorten/compress/machine style" -> `compress`
- input is telegraphic English + "restore/translate back" -> `restore`
- user wants to see both forms -> `roundtrip`
- user wants an ANSWER produced in machine English and delivered here in Russian -> `ask`
- still unclear -> ask one short clarifying question

# Workflow
1. Resolve the mode (see above).
2. Run the script (Python from the AI_9 venv, key taken from the nearest `.env`):

```bash
/home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9/.venv/bin/python \
  /home/u/.kodacli/skills/text-mode-translator_2/scripts/tmt.py \
  --mode <mode> --text "<текст>"
```

   Long text: `--file <путь>`. Multi-line text: pipe via stdin.
   Machine-readable output: add `--json`.
   No API calls (structure check): add `--dry-run`.
3. Read the script output blocks `[COMPRESS]`, `[ANSWER-EN]`, `[RESTORE]`.
4. Reply to the user with the final Russian text (`[RESTORE]` for `roundtrip`/`ask`,
   `[COMPRESS]` for `compress`, `[RESTORE]` for `restore`).
   Attach intermediate blocks only if the user asked to see them.

# Hard rules
- Never transform the text by hand when this skill is active — always call the script.
- Never print, log or commit `API_KEY`.
- Preserve meaning exactly; add no facts, assumptions or opinions.
- Keep structure stable (lists, code fragments, key terms).
- Be concise; do not explain the transformation.
- On script failure (exit code 1 or 2) report the error line from stderr and stop;
  do not silently fall back to a hand-made translation.

# Reference files
- `references/modes.md`: mode definitions and routing rules
- `references/rules.md`: transformation rules
- `references/examples.md`: example pairs
- `references/checks.md`: validation checklist
- `references/api.md`: endpoint, model, parameters, key lookup
- `scripts/tmt.py`: the pipeline itself

