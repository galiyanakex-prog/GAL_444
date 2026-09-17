# debug-plan_d_10.md — план дебага `den_10_Kod.py`

> Составлен на базе `Nedela_2/debug-plan_N2.md` и уже выполненных
> `den_08/.../debug-plan_d_08.md`, `den_09/.../debug-plan_d_9.md`.
> Донор дня — `den_9_Kod.py`.

---

## Блок 0 — Диагноз

`den_10_Kod.py` (3710 строк) сделан копией **промежуточной** версии `den_9_Kod.py`
(до отладочных фиксов Дня 9), поэтому потерял все фиксы Дней 7–9. Фичи самого Дня 10
на месте: `facts`, `branching`, `branches`, `active_branch`, `_build_messages_facts`,
`_build_messages_branching`, `FACTS_PROMPT`, `cmd_facts`, `cmd_branch`,
`cmd_compare_strategies`, `facts_usage`, снимок v4.

Подтверждено grep: все «фиксы» = 0 (`KNOWN_COMMANDS`, `cmd_help`, `get_user_message`,
`--fresh`, `stdout.reconfigure`, `saved_count`/`mark_saved`, `summary_by_layer`,
`COMPRESS_PROMPTS`, `PRIORITY_CAP`, `KNOWN_STRATEGIES`/`KNOWN_MEMORY_TYPES`,
`_run_compression`, `get_summary_length`); регрессии = 1 (`load_history`,
`load_summary`, `load_history(LOG_FILE)`, `basename(LOG_FILE)`).

---

## Блок 1 — Debug-plan (группы A–D, идентичны Дню 9)

### A. Регрессии
- A1 `KNOWN_COMMANDS` (+ `/facts`, `/branch`, `/compare-strategies`) + фильтр `startswith("/")`.
- A2 `cmd_help`.
- A3 `get_user_message()` + `cmd_layer`.
- A4 `sys.stdout.reconfigure(errors='replace')`.
- A5 `--fresh`.
- A6 `SUMMARY_FILE = os.path.splitext(LOG_FILE)[0] + ".summary.md"`.
- A7 `try/except OSError` (создание лога + приветствие).
- A8 `try/except EOFError` (`Нажмите Enter…`).
- A9 голое `/layer`.
- A10 `save_history` append + `saved_count`/`mark_saved`.

### B. JSON-персистентность
- B1 `KNOWN_STRATEGIES`/`KNOWN_MEMORY_TYPES` + валидация `window`.
- B2 `MIN_MIGRATABLE_VERSION` + проверка версии (миграция v1–v3 → v4).
- B3 `load_context_json(..., cli_strategy, cli_memory, cli_window)` + `[Конфиг]`.
- B4 удалить `load_history`/`load_summary`; `notify_old_log()`.
- B5 `clear_context`: `saved_count` + удаление `SUMMARY_FILE`.

### C. Leveled-память
- C1 `summary_by_layer` (high/mid/low).
- C2 `COMPRESS_PROMPTS` (шаблоны язык/лимит) + `_compress_history(..., prompt)`.
- C3 `_run_compression`/`_apply_compression` послойно.
- C4 приоритетный блок `PRIORITY_CAP` в `_build_messages_leveling`.
- C5 синхронизация `save_summary`/`get_summary`/`get_layers_stats`/`get_context_summary`/`get_summary_length`.

### D. Специфика дня
- D1 сброс токен-счётчиков (`usage_total`, `summary_usage`, `facts_usage`, `last_usage`, `exchanges`) при отказе загрузки.
- D2 `cmd_tokens` — оценка последнего сообщения **пользователя**.
- D3 `facts_usage` восстанавливать из снимка v4.

---

## Блок 2 — Порядок
1. A4, A6, A1 → 2. B-константы → 3. C1+`saved_count` → 4. C2–C3 → 5. C4 → 6. C5 → 7. B1–B3+D1 (переписать `load_context_json`) → 8. B4 → 9. A3, A10 → 10. A5, A7, A8, A9, A2 → 11. A1-фильтр в цикле, `/exit`→`save_history` → 12. Проверки.

---

## Блок 3 — Проверки

```bash
python3 -m py_compile den_10_Kod.py
grep -n "def load_history\|def load_summary\|load_history(LOG_FILE)" den_10_Kod.py  # пусто
for s in KNOWN_COMMANDS "def cmd_help" "def get_user_message" "notify_old_log" "--fresh" \
         summary_by_layer COMPRESS_PROMPTS PRIORITY_CAP KNOWN_STRATEGIES KNOWN_MEMORY_TYPES \
         saved_count mark_saved "def _run_compression" "stdout.reconfigure"; do
  printf '%-26s -> ' "$s"; grep -c "$s" den_10_Kod.py
done
```

---

## Блок 4 — Результат

Все пункты Блока 1 применены к `den_10_Kod.py`. `py_compile` — OK.

**Причина багов.** `den_10_Kod.py` сделан копией **промежуточной** версии
`den_9_Kod.py` (до отладочных фиксов Дня 9), поэтому потерял все фиксы Дней 7–9.
Фичи самого Дня 10 (`facts`, `branching`, `branches`, `active_branch`,
`_build_messages_facts`/`_build_messages_branching`, `FACTS_PROMPT`, `cmd_facts`,
`cmd_branch`, `cmd_compare_strategies`, `facts_usage`, снимок v4) сохранены.

**Сделано (по группам):**
- **A (регрессии):** A1–A10 — выполнены (`KNOWN_COMMANDS` + фильтр, `cmd_help`,
  `get_user_message` в `cmd_layer`, `stdout.reconfigure`, `--fresh`,
  `SUMMARY_FILE = splitext(LOG_FILE)`, `try/except OSError/EOFError`, голое `/layer`,
  `save_history` append + `saved_count`/`mark_saved`).
- **B (JSON-валидация):** B1–B5 — выполнены (`KNOWN_STRATEGIES` с facts/branching,
  `KNOWN_MEMORY_TYPES`, `MIN_MIGRATABLE_VERSION` + проверка версии, `[Конфиг]`,
  удалены `load_history`/`load_summary`, `notify_old_log()`, полный сброс в `clear_context`).
- **C (leveled-память):** C1–C5 — выполнены (`summary_by_layer`, `COMPRESS_PROMPTS`,
  `_run_compression`/`_apply_compression` послойно, приоритетный блок `PRIORITY_CAP`,
  синхронизация методов вывода).
- **D (специфика дня):** D1–D3 — выполнены (сброс `usage_total`/`summary_usage`/
  `facts_usage`/`last_usage`/`exchanges` при отказе; `cmd_tokens` оценивает реплику
  пользователя; `facts_usage` восстанавливается из снимка v4).

**Проверки.**
- `py_compile` — OK (исправлена лишняя `)` в `_build_messages_leveling`).
- grep-чеклист: регрессии/двойной источник — 0; все фиксы — на месте.
- Смоук-тест (`API_KEY=test-key`, `--fresh`, branching/session): `/help`,
  фильтр неизвестной команды, `/branch list` (активная ветка `main` видна),
  `/facts` корректно отклоняется в режиме branching, `notify_old_log`,
  `save_history` при `/exit` — без падений, EXIT=0.

**Открытые вопросы (не блокируют).**
1. Живой прогон с реальным API не выполнялся (только с явного согласия пользователя).
2. `__pycache__/den_10_Kod.cpython-313.pyc` перекомпилирован как следствие правки кода.
3. Директория `ND/` в корне репозитория — не артефакт дебага (пользовательские файлы,
   созданы до правок), не трогал.
