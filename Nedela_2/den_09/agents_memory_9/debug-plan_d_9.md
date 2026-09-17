# debug-plan_d_9.md — план дебага `den_9_Kod.py`

> Составлен на базе `Nedela_2/debug-plan_N2.md` (универсальный алгоритм) и уже
> выполненного `den_08/agents_memory_8/debug-plan_d_08.md` (эталон переноса фиксов).
> Источники: `den_09/README_d9.md`, `den_09/Проверка_Д9.md`, `den_09/agents_memory_9/` (plan/mem).

---

## Блок 0 — Диагноз (первичный grep)

`den_9_Kod.py` сделан копией **промежуточной** версии `den_8_Kod.py` (до отладочных
фиксов Дня 8), поэтому потерял все фиксы Дней 7–8. Подтверждено grep:

| Признак | den_9 | финальный den_8 |
|---|---|---|
| `KNOWN_COMMANDS` | 0 | есть |
| `def cmd_help` | 0 | есть |
| `def get_user_message` | 0 | есть |
| `--fresh` | 0 | есть |
| `stdout.reconfigure` | 0 | есть |
| `saved_count` / `mark_saved` | 0 | есть |
| `summary_by_layer` / `COMPRESS_PROMPTS` / `PRIORITY_CAP` | 0 | есть |
| `KNOWN_STRATEGIES` / `KNOWN_MEMORY_TYPES` | 0 | есть |
| `def _run_compression` / `get_summary_length` | 0 | есть |
| `def load_history` / `def load_summary` / `load_history(LOG_FILE)` | есть | удалены |
| `SUMMARY_FILE = … basename(LOG_FILE) …` | есть | исправлен на `splitext(LOG_FILE)` |
| `cmd_layer` через `get_history()` | есть | `get_user_message()` |
| `startswith("/layer ")` без голого `/layer` | есть | исправлено |

Фичи **Дня 9 сохранены** и не должны быть затронуты: `--compress-every`,
`--summary-word-limit`, `--compress-temperature`, `_detect_language`,
`build_compare_variants` / `estimate_compare` / `ask_once` / `cost_summarization`,
`summary_usage`, `cmd_compare`, `cmd_compress_toggle` (`/compress on|off`), снимок v3.

---

## Блок 1 — Debug-plan (группы A–D)

### A. Регрессии (перенос фиксов из den_8)

- **A1** Вернуть `KNOWN_COMMANDS` (14 команд + `/compare`, `/tokens`, `/cost`, `/scenario`) и фильтр `startswith("/")` → «Неизвестная команда…».
- **A2** Вернуть `cmd_help` с пометкой доступности + новые команды дня.
- **A3** Вернуть `Agent.get_user_message()` и починить `cmd_layer` (текст по нумерации `set_layer`).
- **A4** Вернуть `sys.stdout.reconfigure(errors='replace')`.
- **A5** Вернуть флаг `--fresh`.
- **A6** `SUMMARY_FILE = os.path.splitext(LOG_FILE)[0] + ".summary.md"`.
- **A7** `try/except OSError` вокруг создания лога и записи приветствия.
- **A8** `try/except EOFError` вокруг `input("Нажмите Enter…")`.
- **A9** Ловить голое `/layer`.
- **A10** `save_history` в append-режим + `saved_count`/`mark_saved`.

### B. JSON-персистентность (валидация + единый источник истины)

- **B1** `KNOWN_STRATEGIES` / `KNOWN_MEMORY_TYPES` + валидация `window`.
- **B2** `MIN_MIGRATABLE_VERSION` + проверка версии (ниже мин. и выше текущей — отказ).
- **B3** `load_context_json(..., cli_strategy, cli_memory, cli_window)` + `[Конфиг]`-предупреждения.
- **B4** Удалить `load_history`/`load_summary`; `notify_old_log()` только при невосстановленном снимке.
- **B5** `clear_context`: сброс `saved_count` + удаление `SUMMARY_FILE`.

### C. Эволюция leveled-памяти (функциональная дыра, унаследована из den_7)

- **C1** `summary_by_layer` (high/mid/low) для layered; `self.summary` — только compressed.
- **C2** `COMPRESS_PROMPTS` (3 шаблона с языком/лимитом слов) + `_compress_history(..., prompt)`.
- **C3** `_run_compression` / `_apply_compression` — послойное сжатие.
- **C4** Приоритетный блок high/mid вне окна (`PRIORITY_CAP`) в `_build_messages_leveling`.
- **C5** Синхронизация `save_summary`, `get_summary`, `get_layers_stats`, `get_context_summary`, `get_summary_length`.

### D. Собственные дефекты Дня 9

- **D1** При отказе загрузки сбрасывать `usage_total`, `summary_usage`, `last_usage`, `exchanges`.
- **D2** `cmd_tokens` — локальная оценка последнего сообщения **пользователя** (не ответа агента).
- **D3** Восстановление `summary_usage` из снимка v3 (уже есть — сохранить при переделке B2).

---

## Блок 2 — Порядок выполнения

1. A4, A1 (константы), A6 → 2. B-константы → 3. C1 (поля) + `saved_count` → 4. C2–C3 (методы сжатия) → 5. C4 (сборка leveling) → 6. C5 (методы вывода) → 7. B1–B3 + D1 (переписать `load_context_json`) → 8. B4 (удалить `load_*`, `notify_old_log`) → 9. A3, A10 → 10. A5, A7, A8, A9, A2 (флаги/guards/команды) → 11. A1-фильтр в цикле, `/exit` → `save_history` → 12. Проверки.

---

## Блок 3 — Проверки и критерии

```bash
python3 -m py_compile den_9_Kod.py
grep -n "def load_history\|def load_summary\|load_history(LOG_FILE)" den_9_Kod.py   # пусто
for s in KNOWN_COMMANDS "def cmd_help" "def get_user_message" "notify_old_log" "--fresh" \
         summary_by_layer COMPRESS_PROMPTS PRIORITY_CAP KNOWN_STRATEGIES KNOWN_MEMORY_TYPES \
         saved_count mark_saved "def _run_compression" "stdout.reconfigure"; do
  printf '%-26s -> ' "$s"; grep -c "$s" den_9_Kod.py
done
```

Критерии (по debug-plan_N2 §7): py_compile OK; регрессии закрыты; единый источник
истины; валидация данных с диска; версионирование + миграция; сухой стаб-тест;
фичи Дня 9 (`/compare`, `/compress on|off`, `--compress-every` и др.) работают.

---

## Блок 4 — Результат

Все пункты Блока 1 применены к `den_9_Kod.py`. `py_compile` — OK.

**Причина багов.** `den_9_Kod.py` сделан копией **промежуточной** версии
`den_8_Kod.py` (до отладочных фиксов Дня 8), поэтому потерял все фиксы Дней 7–8
(регрессии, валидация JSON, эволюция leveled-памяти). Фичи самого Дня 9
(`--compress-every`, `--summary-word-limit`, `--compress-temperature`,
`_detect_language`, `/compare`, `/compress on|off`, `summary_usage`, снимок v3)
сохранены и не затронуты.

**Сделано (по группам):**
- **A (регрессии):** A1–A10 — все выполнены (`KNOWN_COMMANDS` + фильтр, `cmd_help`,
  `get_user_message` в `cmd_layer`, `stdout.reconfigure`, `--fresh`,
  `SUMMARY_FILE = splitext(LOG_FILE)`, `try/except OSError/EOFError`, голое `/layer`,
  `save_history` в append + `saved_count`/`mark_saved`).
- **B (JSON-валидация):** B1–B5 — выполнены (`KNOWN_STRATEGIES`/`KNOWN_MEMORY_TYPES`,
  `MIN_MIGRATABLE_VERSION` + проверка версии, предупреждения `[Конфиг]`, удалены
  `load_history`/`load_summary`, `notify_old_log()` только при невосстановленном снимке,
  полный сброс в `clear_context`).
- **C (leveled-память):** C1–C5 — выполнены (`summary_by_layer`, `COMPRESS_PROMPTS`
  с шаблонами язык/лимит, `_run_compression`/`_apply_compression` послойно,
  приоритетный блок `PRIORITY_CAP`, синхронизация методов вывода). Учтена специфика
  Дня 9: `_compress_history(..., prompt)` принимает послойный промпт, `COMPRESS_PROMPTS`
  — те же шаблоны `{language}`/`{word_limit}`.
- **D (специфические дефекты Дня 9):** D1–D3 — выполнены (сброс токен-счётчиков при
  отказе загрузки; `cmd_tokens` оценивает последнее сообщение **пользователя**;
  восстановление `summary_usage` сохранено).

**Проверки.**
- `py_compile` — OK.
- grep-чеклист: регрессии/двойной источник — 0; все возвращённые фиксы — на месте.
- Смоук-тест (`API_KEY=test-key`, `--fresh`, compression/compressed): `/help`,
  голое `/layer`, `/compress off` → `/compress on`, `/compare` (локально), `/tokens`,
  `/exit` — без падений, корректные сообщения, EXIT=0.

**Открытые вопросы (не блокируют).**
1. Живой прогон с реальным API не выполнялся (только с явного согласия пользователя).
2. `__pycache__/den_9_Kod.cpython-313.pyc` перекомпилирован как следствие правки кода
   (отслеживается git — побочный эффект изменения `den_9_Kod.py`).
