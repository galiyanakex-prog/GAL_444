# migr_log.md — журнал выполнения миграции `den_14` → `arch_den_14.md`

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_N.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §0.4, правила повтора — §0.3).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).

---

## Подшаги Этапа 0 (журнал хода)

| № | Подшаг | Проверка | Результат | Статус |
|---|---|---|---|---|
| 0.1 | Прогон базовой линии | `env -u API_KEY $PY dev/tests_debug/unit_runner.py` | 40 OK, 0 FAIL | ✅ EXIT 0 |
| 0.1 | — | `env API_KEY=test-key $PY dev/tests_debug/scenario.py` | 6 сценариев OK | ✅ EXIT 0 |
| 0.1 | — | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | 9 из 9 (FAIL=0) | ✅ EXIT 0 |
| 0.2 | Ознакомление с архитектурой | `arch_den_14.md`, `Задание_Д13.txt` |  | ✅ |
| 0.2 | Создание журналов | `dev/logs_reports/stages/stage_F_state.md`, `dev/logs_reports/errors/`, этот файл | созданы | ✅ |
| 0.3 | Карта точек вставки | `state_machine.py`, `store.py`, `working.py`, `agent.py`, `Kod.py` |  точки зафиксированы| ✅ |

**Найдено расхождений:

---

## Этап 0 — Подготовка и приёмка базовой линии (2026-09-21)

- Статус: ✅ выполнен
- Подшаги: 0.1 ✅ / 0.2 ✅ / 0.3 ✅
- Было: `den_14` — копия `den_13
  — задел.
- Стало: базовая линия подтверждена тремя прогонами (все EXIT 0); созданы
  `dev/migr_log.md` (этот файл), `dev/logs_reports/stages/stage_F_state.md`
  (базовая линия + регресс-лист критерия + карта точек вставки +
  расхождения R1–R4), `dev/logs_reports/errors/`; рабочие планы Этапов 1, 5, 7
  скорректированы под фактическое состояние (R1, R3).
- Проверки:
  - ...
  - 
  - ...
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_1.md`

---

## Этап 1 — ... (2026-09-21)

....

---

## Этап M0 — Базовая линия и инвентаризация (2026-09-21 11:41)

- Статус: ✅ завершён
- Было: слой инвариантов отсутствует; baseline неизвестен; расхождения с `arch_den_14.md` §2.1
  не зафиксированы.
- Стало: baseline подтверждён (L2/L3/L4/гейт, все EXIT 0); дерево модулей сверено с
  `arch_den_14.md` §2.1; расхождения и точки внедрения зафиксированы.
- Проверка:
  - `env -u API_KEY ../../.venv/bin/python dev/tests_debug/unit_runner.py` → **56 OK, 0 FAIL** (EXIT 0);
  - `env API_KEY=test-key ../../.venv/bin/python dev/tests_debug/smoke.py` → **SMOKE OK** (EXIT 0);
  - `env API_KEY=test-key ../../.venv/bin/python dev/tests_debug/scenario.py` → **7 сценариев OK** (EXIT 0);
  - `env API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **10 из 10** (FAIL=0, EXIT 0);
  - `timeout 5 bash run.sh --help` → справка выведена (EXIT 0); `run.sh` исполняемый (`-rwxrwxr-x`).
- Артефакты: изменённых файлов продукта нет (этап read-only); запись в `dev/migr_log.md`.

### Дерево модулей: сверка с `arch_den_14.md` §2.1

| Модуль | Целевое (§2.1) | Факт | Статус |
|---|---|---|---|
| `Kod.py` | есть | есть | ✅ |
| `core/agent.py` | есть | есть | ✅ |
| `core/llm_client.py` | есть | есть | ✅ |
| `core/profile_router.py` | есть | есть | ✅ |
| `core/prompt_builder.py` | есть | есть | ✅ |
| `core/state_machine.py` | есть | есть | ✅ |
| `core/invariants.py` | есть (НОВОЕ) | **нет** | ❌ → M1 |
| `memory/*` (base, short_term, working, long_term, profile, manager) | есть | есть (все 6) | ✅ |
| `storage/store.py` | есть | есть | ✅ |
| `storage/db.py` | есть | есть | ✅ |
| `users/` | рантайм | есть | ✅ |
| `run.sh` / `run.desktop` | есть | есть | ✅ |
| `README.md` | + раздел «Инварианты» | есть, раздела нет | ❌ → M7 |
| `dev/tests_debug/unit/test_invariants.py` | есть (НОВОЕ) | **нет** | ❌ → M6 |
| `dev/tests_debug/scenario` (invariant_conflict) | есть (НОВОЕ) | нет | ❌ → M6 |
| `dev/Проверка.md` (строки 26–30) | есть | **нет файла** | ❌ → M7 |
| `core/__init__.py` | (пустой/реэкспорт) | пустой (0 байт) | ⚠ → M1 (реэкспорт при необходимости) |

### Точки внедрения (НЕ менять — контракты дней 11–13, `arch_den_14.md` §2.13)
- `core/llm_client.py` (`LLMClient` / `RouterAIClient` / `MockClient`)
- `memory/*` (`MemoryLayer`, `MemoryManager`, 4 слоя памяти)
- `storage/db.py` (`ProfileRepository`)
- `core/state_machine.py` (`TaskStage` / `TaskState` / переходы / pause/resume)
- `core/profile_router.py` (`ProfileRouter`)

### Перечень расхождений «текущее → целевое» (для M1–M7)
- `core/invariants.py` (модель + `InvariantChecker` + `update_invariant`) → **M1**
- `storage/store.py` (`invariants_path` / `read_invariants` / `write_invariants`) → **M2**
- блок `invariants` в `core/prompt_builder.py` (`BLOCK_ORDER`) → **M3**
- проверка/отказ в `core/agent.py` → **M4**
- CLI-команды инвариантов в `Kod.py` → **M5**
- `unit/test_invariants.py` + `scenario_invariant_conflict` → **M6**
- раздел «Инварианты» в `README.md` + `dev/Проверка.md` (26–30) → **M7**
- финальный прогон + приёмка → **M8**

### Спорное/риски
- **R1 (счёт гейта)**: `check_acceptance.sh` фактически выполняет **10** проверок, а в
  `migr_plan.md`/`arch_den_14.md` заявлено **11 из 11**. Причина — нумерация `check()`
  динамическая; расхождение только в заявленном числе, все проверки зелёные. Уточнить на M6.
- **R2 (число сценариев)**: `scenario.py` выполняет **7** сценариев, а `migr_plan.md` §4 (M6/M8)
  заявляет «8 сценариев» (8-й — ожидаемый `scenario_invariant_conflict`, появится в M6).
- **R3 (нет git-репозитория)**: `git status` → «не найден git репозиторий»; откат «по последнему
  зелёному гейту» физически недоступен через git. Откат — только вручную по команде пользователя.
- **R4 (нет `dev/Проверка.md`)**: `arch_den_14.md` §4.2/§3.1 ссылается на `dev/Проверка.md`
  (25+5 пунктов), но файла в `dev/` нет (есть только `dev/tests_debug/scenario/scen_1.md`).
  Создание — на M7.

### Гейт M0→M1: ✅ пройден
- [x] baseline зелёный (L2 56 OK / L3 OK / L4 7 OK / гейт 10 из 10, EXIT 0);
- [x] расхождения с `arch_den_14.md` §2.1 перечислены;
- [x] точки внедрения (неизменяемые контракты) зафиксированы;
- [x] регрессия до изменений подтверждена;
- [x] `run.sh` работает; окружение активируется.

- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:41)
- Следующий этап: `dev/migr_plan_1.md` (M1 — Ядро инвариантов)

---

## Этап M1 — Ядро инвариантов (2026-09-21 11:44)

- Статус: ✅ завершён
- Было: слой инвариантов отсутствует (`core/invariants.py` не существовал).
- Стало: создан `core/invariants.py` — `Invariant` / `ConstraintSet` / `ProposedAction` /
  `InvariantChecker` (ABC) + `RuleBasedChecker` + `add_invariant` / `update_invariant` /
  `toggle_invariant` / `example_constraints`.
- Проверка:
  - примитив-смоук (9 блоков, инлайн) → **M1 OK** (EXIT 0): разрешённое → `[]`; запрещённое
    `technology="fastapi"` при `framework.django` → 1 нарушение с `id`; `update_invariant`
    без авторизации → `PermissionError`; 2 нарушения одновременно; `active=False` снимает
    блокировку; `severity="warning"` → в `warnings`, не в `check`; round-trip
    `to_dict`/`from_dict`; битый вход → пустой набор; `stack.python` через `language`;
  - регрессия L2: `env -u API_KEY .../unit_runner.py` → **56 OK, 0 FAIL** (EXIT 0).
- Артефакты: `core/invariants.py` (новый). `core/__init__.py` пуст (0 байт) — реэкспорт
  не требуется, импорт идёт как `from core.invariants import ...` (как в остальных модулях).
- Спорное/риски: проверка реализована **обобщённо** (неймспейсы `framework.*`, `stack.*` +
  точные id `dependencies.no-new`/`database.no-schema-changes`) вместо жёсткого `if id == ...`
  из черновика `arch_den_14.md` §2.3 — это аддитивно и не нарушает канон `Задание_Д14.txt`
  (пример из задания сохранён по смыслу). `ProposedAction` дополнен полем `language` для
  инварианта `stack.python`.
- Гейт M1→M2: ✅ пройден (модуль импортируется; разрешённое → `[]`; запрещённое → нарушение
  с id; `authorized=False` → `PermissionError`; несколько нарушений; наследие не затронуто).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:44)
- Следующий этап: `dev/migr_plan_2.md` (M2 — Хранение инвариантов)

---

## Этап M2 — Хранение инвариантов (2026-09-21 11:46)

- Статус: ✅ завершён
- Было: инварианты не хранились отдельно.
- Стало: в `storage/store.py` добавлены `invariants_path` / `read_invariants` /
  `write_invariants`; набор живёт в `users/<id>/tasks/<task>/invariants.json` (отдельно от
  диалога).
- Проверка:
  - гейт-смоук (5 блоков, инлайн) → **M2 OK** (EXIT 0): round-trip `save→load` (4 правила);
    отсутствующий файл → `None` → пустой набор; удаление `session.json` НЕ удаляет
    `invariants.json`; битый JSON → `None` → пустой набор (не падает); путь соответствует
    канонической иерархии;
  - регрессия: L2 → **56 OK, 0 FAIL**; L4 → **SCENARIO OK** (EXIT 0).
- Артефакты: `storage/store.py` (добавлены 3 метода; контракты `db.py`/наследия не тронуты).
- Спорное/риски: нет.
- Гейт M2→M3: ✅ пройден (round-trip равен; отсутствие файла → пустой набор; `session.json`
  и `invariants.json` независимы; битый файл не роняет приложение; контракты не изменены).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:46)
- Следующий этап: `dev/migr_plan_3.md` (M3 — Инжект в промт)

---

## Этап M3 — Инжект инвариантов в промт (2026-09-21 11:48)

- Статус: ✅ завершён
- Было: промт не содержал блок инвариантов.
- Стало: в `core/prompt_builder.py` имя `invariants` добавлено в `BLOCK_ORDER` (после `profile`,
  до `working`); добавлены `render_invariants` + `INVARIANTS_ROLE_RULE` + `INVARIANTS_INSTRUCTIONS`;
  блок формируется из `ConstraintSet.active()`, добавляется только если `invariants` в `deliver`.
- Проверка:
  - гейт-смоук (5 блоков, инлайн) → **M3 OK** (EXIT 0): порядок блоков (profile < invariants <
    working); блок виден при наличии в `deliver` и отсутствует без него; правило роли добавлено
    только при активном блоке; выключенное правило не попадает; пустой набор → блока нет;
  - регрессия: L2 → **56 OK, 0 FAIL**; L3 → **SMOKE OK** (EXIT 0).
- Артефакты: `core/prompt_builder.py`.
- Спорное/риски: блок `invariants` добавляется как system-сообщение через duck-typing
  (`ctx.invariants` — строка или `ConstraintSet`), контракт `build(ctx, deliver, budget)` не
  изменён. `PromptContext` в `agent.py` получит поле `invariants` на этапе M4.
- Гейт M3→M4: ✅ пройден (блок виден при `deliver`, отсутствует без него; порядок сохранён;
  только активные правила; наследие не сломано).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:48)
- Следующий этап: `dev/migr_plan_4.md` (M4 — Оркестратор: проверка и отказ)

---

## Этап M4 — Оркестратор: проверка и отказ (2026-09-21 11:52)

- Статус: ✅ завершён
- Было: агент не проверял инварианты.
- Стало: в `core/agent.py` добавлены `constraints` / `checker` / `action_analyzer`,
  `load_constraints` / `save_constraints`, `check_invariants` / `invariant_warnings`,
  `propose_action`, `propose_and_check`, `_execute` (единственное место вызова инструмента),
  `_refusal_message`, `add/update/toggle_invariant`; `PromptContext` несёт `invariants`;
  `deliver` по умолчанию включает `invariants`; `switch_task`/`load_state` подтягивают набор
  задачи; `save_state` сохраняет набор. Добавлен детерминированный `TextActionAnalyzer`
  (текст → `ProposedAction`, без LLM) + счётчик `tool_calls`.
- Проверка:
  - гейт-смоук M4 (5 блоков, инлайн) → **M4 OK** (EXIT 0): запрещённое → `allowed=False`,
    `tool_calls` не растёт, отказ содержит `framework.django` и альтернативу; разрешённое →
    выполнено (`tool_calls` +1); логи `[Инварианты]`; `severity="warning"` → выполнено с
    ворнингом; набор переживает перезапуск;
  - доп. проверка извлечения id в отказе → **M4b OK** («обновить инвариант framework.django»);
  - регрессия: L2 → **56 OK, 0 FAIL**; L4 → **SCENARIO OK**; L3 → **SMOKE OK** (EXIT 0).
- Артефакты: `core/agent.py`.
- Спорное/риски: введён `TextActionAnalyzer` как анализатор действий по умолчанию (проверка
  инвариантов работает в детерминированном режиме без живого ключа). В боевом режиме анализатор
  инжектируем (LLM), но проверка остаётся кодом. Контракты наследия (`respond`, память, автомат)
  не изменены; `respond` не блокирует обычный диалог (проверка применяется в `propose_and_check`).
- Гейт M4→M5: ✅ пройден (запрещённое не вызывает инструмент; отказ с id+альтернативой;
  разрешённое выполняется; логи `[Инварианты]`; `warning` не блокирует; наследие не сломано).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:52)
- Следующий этап: `dev/migr_plan_5.md` (M5 — CLI-команды инвариантов)

---

## Этап M5 — CLI-команды инвариантов (2026-09-21 11:57)

- Статус: ✅ завершён
- Было: команды инвариантов отсутствовали.
- Стало: в `Kod.py` добавлены `/invariants`, `/invariant add|set|on|off`, `/check`;
  `--fresh` не восстанавливает `invariants.json`; `exit` сохраняет набор; обновлён `/help`.
- Проверка (REPL-смоук, mock, временный каталог `.tmp/`):
  - `/invariant add` → добавлено; `/invariants` → правило в списке (id|category|severity|active);
  - `/check перейти на FastAPI` → **ЗАПРЕЩЕНО** (нарушение `framework.django`);
  - `/invariant set ... без --yes` → «требует отдельного подтверждения» (не меняет);
    с `--yes` → изменено;
  - `/invariant on|off` → переключает; `off` снимает блокировку (`/check` → разрешено);
  - набор **переживает перезапуск** (виден в новом процессе); `--fresh` → «Набор пуст»;
  - регрессия: L2 → **56 OK, 0 FAIL**; L4 → **SCENARIO OK**; L3 → **SMOKE OK** (EXIT 0).
- Артефакты: `Kod.py`.
- Спорное/риски: команды `/invariants` и `/invariant` обрабатываются одним хендлером
  `handle_invariants_command`; демонстрация `/check` не исполняет действие (только проверка).
  Унаследованные команды дней 11–13 не тронуты.
- Гейт M5→M6: ✅ пройден (команды работают; набор переживает перезапуск; `--fresh` игнорирует
  набор; наследие не регрессирует).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-21 11:57)
- Следующий этап: `dev/migr_plan_6.md` (M6 — Тесты и отладка)

---
