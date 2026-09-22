# debug_plan_1.md — рабочий план этапа D1 «Доставка блоков: DELIVERABLE»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** дебага проекта `den_14`
> по плану-эталону `dev/meta_promt/debug_plan.md`. Разворачивает этап **D1** из
> `debug_plan.md` §5 в конкретные правки и проверки. Закрывает проблему **A1**.
> **Конец этого этапа — автоматический гейт в этап D2** (`debug_plan_2.md`).
> Источники: `debug_plan.md` §3 (A1), §3.3 (решение), факт бага из D0.

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **D1** — Доставка блоков: `DELIVERABLE` |
| Рабочий план | `dev/meta_promt/debug_plan_1.md` (этот файл) |
| Зависит от | **D0** (baseline зелёный, баг A1 воспроизведён) |
| Открывает | `dev/meta_promt/debug_plan_2.md` (D2 — Константы + бюджет) |
| Закрывает | **A1** (баг: `invariants`/`summary` вырезаются из `deliver`) |
| Основные артефакты | `core/prompt_builder.py`, `Kod.py`, `dev/tests_debug/unit/test_prompt.py` |
| Живой ключ | **Не нужен** (`MockClient` / `API_KEY=test-key`) |
| Меняет поведение | **Да — намеренно** (к заявленному spec'ом: блок инвариантов виден в промте) |

**Цель этапа.** Ввести канонический набор доставляемых имён блоков `DELIVERABLE` в
`core/prompt_builder.py`; заменить оба пересечения с `LAYER_ORDER` в `Kod.py`;
дополнить дефолт `--deliver`. Итог: блок `[system: invariants]` реально попадает в
промт CLI, `summary` достижим из CLI.

---

## 1. Вход и предусловия

- `core/prompt_builder.py` (`BLOCK_ORDER` — уже содержит `invariants`/`summary`;
  сборка блоков по `deliver` — не менять логику сборки, только источник имён).
- `Kod.py`: два места пересечения — `main()` (~строка `agent.deliver = deliver &
  set(LAYER_ORDER)`) и обработчик `/deliver` (`agent.deliver = chosen &
  set(LAYER_ORDER)`); дефолт argparse `--deliver` —
  `"profile,long_term,working,short_term"` (без `invariants`).
- `memory/manager.py`: `LAYER_ORDER` — **не трогать** (порядок слоёв памяти, не блоков).
- Факт бага A1 из D0 (воспроизведение в `debug_log.md`).

**Предусловия:** D0 зелёный; `Agent.__init__` уже ставит `deliver` с `invariants`
(проверено D0) — перезапись в `main()` и есть баг.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 1.1 — `DELIVERABLE` в `core/prompt_builder.py`
1. Добавить константу сразу после `BLOCK_ORDER`:
   ```python
   # Имена блоков, управляемые дозированной доставкой (role и current — всегда,
   # неуправляемы). Канонический набор для --deliver / /deliver / Agent.deliver.
   DELIVERABLE = ("profile", "invariants", "long_term", "working",
                  "summary", "short_term")
   ```
2. Комментарий к `BLOCK_ORDER` дополнить указанием, что доставляемое подмножество —
   `DELIVERABLE` (порядок — `BLOCK_ORDER`, состав — `DELIVERABLE`).
3. **Ожидаемый результат:** константа объявлена; `set(DELIVERABLE) ⊆
   set(BLOCK_ORDER)`; логика `build()` не изменена.

### Шаг 1.2 — Заменить пересечения в `Kod.py`
1. Импорт: `from core.prompt_builder import PromptBuilder, DELIVERABLE`
   (дополнить существующую строку импорта `PromptBuilder`).
2. `main()`: `agent.deliver = deliver & set(DELIVERABLE)`.
3. Обработчик `/deliver`: `agent.deliver = chosen & set(DELIVERABLE)`.
4. Убрать импорт `LAYER_ORDER` из `memory.manager`, **если** он больше не
   используется в `Kod.py` (проверить grep; используется — оставить).
5. **Ожидаемый результат:** оба пересечения — по `DELIVERABLE`; `invariants` и
   `summary` больше не вырезаются.

### Шаг 1.3 — Дефолт `--deliver` в argparse
1. Заменить дефолт на полный канонический набор:
   ```python
   parser.add_argument("--deliver", type=str,
                       default="profile,invariants,long_term,working,short_term", ...)
   ```
2. **Ожидаемый результат:** без флага `--deliver` блок инвариантов включён
   (совпадает с дефолтом `Agent.__init__`).

### Шаг 1.4 — Юнит-тесты (тест с правкой)
В `dev/tests_debug/unit/test_prompt.py` добавить:
1. `test_deliverable_canonical`: `DELIVERABLE` содержит `invariants` и `summary`;
   `set(DELIVERABLE) <= set(BLOCK_ORDER)`; `role`/`current` не входят.
2. `test_summary_reachable_via_deliverable`: сборка с
   `deliver={"profile", "summary"}` и непустым `ctx.summary` → блок summary в
   сообщениях (дополняет существующий `test_summary_block` — теперь через
   канонический набор).
3. В `dev/tests_debug/unit/test_agent.py` (или `test_prompt.py`, по месту):
   `test_agent_deliver_keeps_invariants` — `Agent` с дефолтным `deliver` и
   непустым `constraints` → в собранном промте есть блок `[system: invariants]`
   (закрывает регрессию бага A1 на уровне агента).
4. **Ожидаемый результат:** новые тесты зелёные; прежние 69 — без правок и падений.

### Шаг 1.5 — Контрольный прогон CLI (баг-фикс «после»)
Повторить прогон из D0 (шаг 0.3) — тот же сценарий, тот же `--memory-dir` в `.tmp/`:
1. С дефолтным `--deliver` (без флага): в ответе `MockClient` **виден** блок
   `[system: invariants]` / «Обязательные инварианты:».
2. С `--deliver profile,working`: блок инвариантов **отсутствует** (дозированная
   доставка работает в обе стороны).
3. `--deliver profile,summary` (после `/summary`-сессии): блок summary включается.
4. Зафиксировать пару «до (D0) / после (D1)» в `debug_log.md`.
5. **Ожидаемый результат:** баг A1 закрыт; доставка управляема в обе стороны.

### Шаг 1.6 — Регрессия контура
```bash
python -m py_compile Kod.py core/*.py memory/*.py storage/*.py
env -u API_KEY python dev/tests_debug/unit_runner.py
env API_KEY=test-key python dev/tests_debug/smoke.py
env API_KEY=test-key python dev/tests_debug/scenario.py
env API_KEY=test-key bash dev/tests_debug/check_acceptance.sh
```
**Ожидаемый результат:** L2 69 + 3 новых = 72 OK / 0 FAIL; L3 OK; L4 8/8 (вкл.
`scenario_invariant_conflict`); гейт 12/12; все EXIT 0.

---

## 3. Выход этапа

- `core/prompt_builder.py` (+ `DELIVERABLE`), `Kod.py` (2 пересечения + дефолт
  `--deliver` + импорт).
- 3 новых юнит-теста (`test_prompt.py` / `test_agent.py`).
- Пара «до/после» баг-фикса A1 в `debug_log.md`.
- Запись этапа **D1** в `dev/meta_promt/debug_log.md`; статус A1 → ✅.

---

## 4. Автоматический гейт D1→D2

Гейт считается **зелёным**, если одновременно:
- [ ] при дефолтном запуске CLI блок `[system: invariants]` **виден** в промте
      (MockClient/`Den_log.md`, шаг 1.5);
- [ ] `--deliver profile,working` исключает блок инвариантов; `summary` достижим;
- [ ] новые тесты зелёные; L2 без падений (72 OK); L3 OK; L4 8/8; гейт 12/12;
- [ ] `LAYER_ORDER` в `memory/manager.py` не изменён; логика `build()` не изменена;
- [ ] `scenario_invariant_conflict` зелёный.

**Зелёный** → запись D1 в `debug_log.md` (✅, A1 → ✅) → **перечитать
`debug_plan.md`** → создать/открыть `debug_plan_2.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап D1
остаётся открыт.

---

## 5. Запись в `debug_log.md` (форма §7.4 `debug_plan.md`)

```text
## Этап D1 — Доставка блоков: DELIVERABLE
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Закрыто: A1
- Было: deliver ∩ LAYER_ORDER вырезал invariants/summary; дефолт --deliver без invariants
- Стало: DELIVERABLE в prompt_builder.py; оба пересечения по DELIVERABLE; дефолт
  --deliver полный; блок [system: invariants] виден в CLI
- Проверка: <новые тесты; L2 72 OK; L3; L4 8/8; гейт 12/12; прогон до/после>
- Артефакты: core/prompt_builder.py, Kod.py, test_prompt.py [, test_agent.py]
- Спорное/риски: <состав промта при дефолте изменился (заявлено spec'ом — критерий 27)>
- Перечитывание debug_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт D1→D2: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/meta_promt/debug_plan.md`, затем приступить к **D2** по
`dev/meta_promt/debug_plan_2.md` (константы `MODEL_CONTEXT_LIMIT`/цены в
`core/llm_client.py` + проводка `budget` — закрытие A2, A3).
