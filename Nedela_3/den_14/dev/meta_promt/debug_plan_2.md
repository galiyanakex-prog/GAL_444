# debug_plan_2.md — рабочий план этапа D2 «Константы модели/цен + бюджет промта»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** дебага проекта `den_14`
> по плану-эталону `dev/meta_promt/debug_plan.md`. Разворачивает этап **D2** из
> `debug_plan.md` §5 в конкретные правки и проверки. Закрывает проблемы **A2, A3**.
> **Конец этого этапа — автоматический гейт в этап D3** (`debug_plan_3.md`).
> Источники: `debug_plan.md` §3 (A2, A3), §3.3 (решения: константы — один источник
> истины; `budget` — дефолт `None`), `den_12/dev/meta_promt/ПРОМТ_llm.md` §3.1
> (первоисточник констант).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **D2** — Константы модели/цен + бюджет промта |
| Рабочий план | `dev/meta_promt/debug_plan_2.md` (этот файл) |
| Зависит от | **D1** (доставка блоков починена) |
| Открывает | `dev/meta_promt/debug_plan_3.md` (D3 — Косметика ядра) |
| Закрывает | **A2** (константы), **A3** (проводка `budget`) |
| Основные артефакты | `core/llm_client.py`, `core/agent.py`, `Kod.py`, `dev/tests_debug/unit/test_agent.py` |
| Живой ключ | **Не нужен** |
| Меняет поведение | **Нет** (при дефолтах: `budget=None` — обрезание выключено; цены те же 11/33) |

**Цель этапа.** Вернуть в `core/llm_client.py` константы из `ПРОМТ_llm.md` §3.1
(`MODEL_CONTEXT_LIMIT`, `PRICE_IN_PER_M`, `PRICE_OUT_PER_M`), связать с ними дефолты
argparse; провести `budget` через `Agent` в рабочий путь с флагом `--budget`
(дефолт `None` — выключен).

---

## 1. Вход и предусловия

- `core/llm_client.py`: константы `URL`, `MODEL`, `REQUEST_TIMEOUT`, `RETRY_DELAYS`
  (четыре из шести предписанных; сигнатуры классов — контракт, не менять).
- `Kod.py`: `--price-in`/`--price-out` с литеральными дефолтами `11.0`/`33.0`;
  флага `--budget` нет.
- `core/agent.py`: `respond()` вызывает `self.prompts.build(prompt_ctx,
  self.deliver)` — без `budget`.
- `core/prompt_builder.py`: `build(ctx, deliver, budget=None)` — параметр уже есть
  (проверен только юнит-тестом `test_budget_trims_optional`).
- D1 зелёный (доставка блоков работает).

**Предусловия:** A2/A3 подтверждены в D0 (таблица «ID → файл:строка»).

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 2.1 — Константы в `core/llm_client.py`
1. Дополнить блок констант (рядом с `URL`/`MODEL`, стиль — как у существующих):
   ```python
   MODEL_CONTEXT_LIMIT = 262144   # окно модели (Step-3.5-Flash_params.md)
   PRICE_IN_PER_M = 11.0          # ₽ / 1M входящих
   PRICE_OUT_PER_M = 33.0         # ₽ / 1M исходящих
   ```
2. **Не** трогать классы `LLMClient`/`RouterAIClient`/`MockClient` (контракт §0.2).
3. **Ожидаемый результат:** шесть констант из `ПРОМТ_llm.md` §3.1 на месте;
   модуль импортируется.

### Шаг 2.2 — Дефолты цен в `Kod.py` из констант
1. Импорт: дополнить существующую строку `from core.llm_client import ...` —
   `PRICE_IN_PER_M, PRICE_OUT_PER_M` (и `MODEL_CONTEXT_LIMIT` — для help-текста
   шага 2.4; это же закрывает «неиспользуемый импорт `MODEL`» из A7 по этому файлу:
   либо использовать, либо не импортировать — решить на шаге, зафиксировать).
2. Дефолты argparse:
   ```python
   parser.add_argument("--price-in", type=float, default=PRICE_IN_PER_M, ...)
   parser.add_argument("--price-out", type=float, default=PRICE_OUT_PER_M, ...)
   ```
3. **Ожидаемый результат:** литералы `11.0`/`33.0` в `Kod.py` отсутствуют; значения
   те же (поведение `/cost` не меняется).

### Шаг 2.3 — Проводка `budget` через `Agent`
1. `core/agent.py`, `__init__` (после `self.deliver = ...`):
   ```python
   # Бюджет промта (входящие токены, локальная оценка): None — обрезание
   # выключено (поведение дней 11–14 не меняется); число — необязательные
   # блоки опускаются при превышении (роль и текущий запрос — всегда).
   self.prompt_budget = None
   ```
2. `respond()`: `messages = self.prompts.build(prompt_ctx, self.deliver,
   budget=self.prompt_budget)`.
3. **Ожидаемый результат:** бюджет передаётся в рабочем пути; при `None` поведение
   побайтово то же (параметр уже опционален в `build()`).

### Шаг 2.4 — Флаг `--budget` в `Kod.py`
1. Argparse (после `--max-tokens`):
   ```python
   parser.add_argument("--budget", type=int, default=None,
                       help="Лимит входящих токенов промта: необязательные блоки "
                            "опускаются (роль и запрос — всегда). Ориентир для "
                            "ручного значения — MODEL_CONTEXT_LIMIT (%d) минус "
                            "резерв под ответ. По умолчанию выключен." % MODEL_CONTEXT_LIMIT)
   ```
2. В `main()` после `build_agent(...)`: `agent.prompt_budget = args.budget`.
3. `/help`: строка про `--budget` не нужна (это флаг запуска, не REPL-команда);
   но стартовая печать режима дополнить: при заданном `--budget` печатать
   `[Режим] Бюджет промта: N токенов (необязательные блоки опускаются)`.
4. **Запрещено** (§3.3 эталона): автоматический дефолт `budget =
   MODEL_CONTEXT_LIMIT` — локальная оценка токенов ≠ реальные токены API;
   молчаливое изменение поведения.
5. **Ожидаемый результат:** флаг работает; без флага — поведение неизменно.

### Шаг 2.5 — Юнит-тест проводки (тест с правкой)
В `dev/tests_debug/unit/test_agent.py` добавить:
```python
def test_prompt_budget_passed_in_respond(tmp_path):
    # Agent с prompt_budget=1: необязательный блок (profile) опускается
    # в рабочем пути respond(), роль и запрос — остаются.
    ...
```
1. Собрать агента на `MockClient` + изолированном `Store` (по образцу существующих
   тестов агента); `agent.prompt_budget = 1`; записать профиль; вызвать
   `respond("вопрос")`; в `MockClient.calls[-1]` (последний собранный промт)
   утверждать: блок profile отсутствует, `messages[-1]["content"] == "вопрос"`.
2. Контроль: `prompt_budget = None` → блок profile присутствует (проводка не
   меняет поведение по умолчанию).
3. **Ожидаемый результат:** тест зелёный; проводка `budget` покрыта (раньше —
   только `test_budget_trims_optional` на уровне билдера).

### Шаг 2.6 — Регрессия контура
```bash
python -m py_compile Kod.py core/*.py memory/*.py storage/*.py
env -u API_KEY python dev/tests_debug/unit_runner.py
env API_KEY=test-key python dev/tests_debug/smoke.py
env API_KEY=test-key python dev/tests_debug/scenario.py
env API_KEY=test-key bash dev/tests_debug/check_acceptance.sh
```
Плюс ручной смоук флага (в `.tmp/`):
```bash
D=dev/tests_debug/.tmp/dbg_budget; rm -rf "$D"; mkdir -p "$D"
printf 'u\nИ\nкраткий\nPython\nцель\nВопрос\n/exit\n' \
  | API_KEY=test-key python Kod.py --mock --user u --budget 1 \
    --memory-dir "$D/users" --log "$D/log.md" --token-log "$D/tokens.csv"
```
**Ожидаемый результат:** L2 72 + 1 = 73 OK / 0 FAIL; L3 OK; L4 8/8; гейт 12/12;
`--budget 1` урезает необязательные блоки (в ответе MockClient меньше сообщений),
без флага — состав промта прежний.

---

## 3. Выход этапа

- `core/llm_client.py` (+3 константы), `core/agent.py` (`prompt_budget` + проводка),
  `Kod.py` (дефолты цен из констант, `--budget`, стартовая печать).
- Новый юнит-тест проводки бюджета.
- Запись этапа **D2** в `dev/meta_promt/debug_log.md`; статусы A2, A3 → ✅.

---

## 4. Автоматический гейт D2→D3

Гейт считается **зелёным**, если одновременно:
- [ ] `grep -n "11.0\|33.0" Kod.py` — литералы цен отсутствуют (дефолты из констант);
- [ ] `MODEL_CONTEXT_LIMIT`/`PRICE_*` объявлены в `core/llm_client.py` и
      импортируются в `Kod.py`;
- [ ] `--budget 1` урезает необязательные блоки; без флага состав промта прежний;
- [ ] тест проводки зелёный; L2 73 OK / 0 FAIL; L3 OK; L4 8/8; гейт 12/12;
- [ ] сигнатуры `LLMClient`/`RouterAIClient`/`MockClient` не изменены;
- [ ] дефолт `budget` — `None` (автодефолт от `MODEL_CONTEXT_LIMIT` не вводился).

**Зелёный** → запись D2 в `debug_log.md` (✅, A2/A3 → ✅) → **перечитать
`debug_plan.md`** → создать/открыть `debug_plan_3.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап D2
остаётся открыт.

---

## 5. Запись в `debug_log.md` (форма §7.4 `debug_plan.md`)

```text
## Этап D2 — Константы модели/цен + бюджет промта
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Закрыто: A2, A3
- Было: константы ПРОМТ_llm §3.1 отсутствовали; цены — литералы в argparse;
  budget не передавался в рабочем пути
- Стало: константы в llm_client.py; дефолты argparse из них; Agent.prompt_budget +
  --budget (дефолт None); проводка покрыта тестом
- Проверка: <L2 73 OK; L3; L4 8/8; гейт 12/12; смоук --budget 1 / без флага>
- Артефакты: core/llm_client.py, core/agent.py, Kod.py, test_agent.py
- Спорное/риски: <решение по импорту MODEL в Kod.py — зафиксировать>
- Перечитывание debug_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт D2→D3: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/meta_promt/debug_plan.md`, затем приступить к **D3** по
`dev/meta_promt/debug_plan_3.md` (окно short_term, `ROLES`, `identify()`, импорты —
закрытие A4–A7).
