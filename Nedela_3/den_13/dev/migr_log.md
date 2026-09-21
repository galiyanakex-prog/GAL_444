# migr_log.md — журнал выполнения миграции `den_13` → `arch_den_13.md`

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_8.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §0.4, правила повтора — §0.3).
> Свод «было → стало» по Этапу F: `dev/logs_reports/stages/stage_F_state.md`.
>
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).

---

## Подшаги Этапа 0 (журнал хода)

| № | Подшаг | Проверка | Результат | Статус |
|---|---|---|---|---|
| 0.1 | Прогон базовой линии | `env -u API_KEY $PY dev/tests_debug/unit_runner.py` | 40 OK, 0 FAIL | ✅ EXIT 0 |
| 0.1 | — | `env API_KEY=test-key $PY dev/tests_debug/scenario.py` | 6 сценариев OK | ✅ EXIT 0 |
| 0.1 | — | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | 9 из 9 (FAIL=0) | ✅ EXIT 0 |
| 0.2 | Ознакомление с архитектурой | `arch_den_13.md` §2.2–2.9, §3.3, §4.3 + `Задание_Д13.txt` | регресс-лист 22 критерия + 3 новых (23–25) | ✅ |
| 0.2 | Создание журналов | `dev/logs_reports/stages/stage_F_state.md`, `dev/logs_reports/errors/`, этот файл | созданы | ✅ |
| 0.3 | Карта точек вставки | `state_machine.py`, `store.py`, `working.py`, `agent.py`, `Kod.py` | 5 файлов, точки зафиксированы (§3 stage_F_state.md) | ✅ |

**Найдено расхождений:** 4 (R1–R4, см. `stage_F_state.md` §4) — все учтены в планах Этапов 1, 5, 7.

---

## Этап 0 — Подготовка и приёмка базовой линии (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 0.1 ✅ / 0.2 ✅ / 0.3 ✅
- Было: `den_13` — копия `den_12` (персонализация + модель памяти); `core/state_machine.py`
  — задел (Enum `TaskState` из 4 стадий + `ALLOWED_TRANSITIONS` + `next_state()`);
  `store.py` не знает `task_state.json`; `working.py` даёт строку «Стадия задачи»;
  `agent.py` без жизненного цикла задачи; `Kod.py` — 12 команд; тесты L2 40 / L4 6 / гейт 9.
  В `dev/` отсутствуют `Проверка.md`, `meta_promt/`, `logs_reports/` (R1).
- Стало: базовая линия подтверждена тремя прогонами (все EXIT 0); созданы
  `dev/migr_log.md` (этот файл), `dev/logs_reports/stages/stage_F_state.md`
  (базовая линия + регресс-лист 22+3 критерия + карта точек вставки по 5 файлам +
  расхождения R1–R4), `dev/logs_reports/errors/`; рабочие планы Этапов 1, 5, 7
  скорректированы под фактическое состояние (R1, R3).
- Проверки:
  - `env -u API_KEY $PY dev/tests_debug/unit_runner.py` → 40 OK, 0 FAIL, EXIT 0
  - `env API_KEY=test-key $PY dev/tests_debug/scenario.py` → 6 сценариев OK, EXIT 0
  - `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → 9 из 9, EXIT 0
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_1.md`

---

## Этап 1 — Ядро автомата (`core/state_machine.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 1.1 ✅ / 1.2 ✅ / 1.3 ✅ / 1.4 ❌→✅ / 1.5 ✅ / 1.6 ✅ (+ внеплановая миграция
  `test_state.py`, см. ниже)
- Было: `core/state_machine.py` — задел (Enum `TaskState` 4 стадии + `ALLOWED_TRANSITIONS`
  4 ключа + `next_state()`); `Kod.py` импортировал `TaskState` как Enum.
- Стало: полный автомат — `TaskStage` (6 этапов), dataclass `TaskState` (9 полей канона),
  `ALLOWED_TRANSITIONS` (6 ключей, paused/failed), `transition()` (единственная точка смены
  этапа + лог «[Автомат]»), `next_state()` (обёртка совместимости), `pause_task()`/
  `resume_task()` (идемпотентные), `save_state()`/`load_state()` (JSON, enum↔.value, битый
  файл→None), `run_task(state, executor, validator)` (один проход). `Kod.py`: импорт
  `TaskStage`, `show_state()` по 6 этапам (R3 закрыт). `test_state.py` мигрирован на
  `TaskStage` (+ новый `test_paused_and_failed_extensions`).
- Проверки:
  - `py_compile core/state_machine.py Kod.py` → OK
  - smoke 1.2–1.6 (в `.tmp/fsm/`) → все OK: transition (planning→done ✗), pause/resume
    (канонический test_pause_and_resume), save/load roundtrip + битый/отсутствующий → None,
    run_task → DONE (3 results), failed+error, шаги не дублируются
  - `unit_runner.py` → **41 OK, 0 FAIL** (было 40; +1 новый тест state)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → **9/9**
- Повторы/ошибки: подшаг 1.4 — ❌ на первом прогоне: канонический `test_pause_and_resume`
  из `Задание_Д13.txt` требует, чтобы после resume `expected_action` был восстановлён, а
  пример `pause_task` в том же файле перезаписывает его на «Ожидать команды продолжения»
  (внутреннее противоречие первоисточника). **Решение:** приоритет отдан исполняемому тесту
  и JSON-снимку paused из `Задание_Д13.txt` (`expected_action="Собрать информацию"` —
  сохранённое) → `pause_task()` НЕ перезаписывает `expected_action`; факт паузы несёт
  `stage == PAUSED`. Зафиксировано комментарием в коде. После правки — ✅.
  **Отклонение от плана:** миграция `test_state.py` (планировалась на Этап 6.1) выполнена
  здесь — переименование Enum→`TaskStage` есть прямое следствие Этапа 1, и это снимает
  статус ⚠ (гейт зелёный на всех последующих этапах). На Этапе 6.1 останется только
  сверить тест с итоговым `test_fsm.py`.
- Следующий этап: `dev/migr_plan_2.md`

---

## Этап 2 — Хранилище (`storage/store.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 2.1 ✅
- Было: `Store` не знал `task_state.json`; docstring-дерево без снимка состояния.
- Стало: новая секция «Состояние задачи (state machine)» — `task_state_path()`,
  `read_task_state()` (отсутствует/битый → None), `write_task_state()` (через `ensure_task`
  + `write_json`); docstring-дерево дополнено `task_state.json`. Существующие методы не
  тронуты.
- Проверки:
  - `py_compile storage/store.py` → OK
  - smoke roundtrip (`.tmp/store_fsm_*`): write→read сохраняет все поля (включая
    previous_stage, error); read на отсутствующем → None → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_storage 7 зелёные — регрессии нет)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_3.md`

---

## Этап 3 — Память (`memory/working.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 3.1 ✅ / 3.2 ✅
- Было: `as_prompt_block()` давал строку «Стадия задачи: {current_state}» (зеркало).
- Стало: инжект формализованного состояния (arch §2.7) — хелпер `_task_state_lines(ctx)`
  читает `store.read_task_state` и добавляет строки «Этап: … (шаг N/M): …», «Пауза
  (вернуться к: …)», «Ожидаемое действие: …», «Ошибка: …»; строка «Стадия задачи»
  сохранена (обратная совместимость). `read()`/`write()` не менялись (контракт слоя).
  Решение 3.2: зеркало `current_state` пишется из `Agent._persist_task_state()` (Этап 4) —
  ветка `if key == "current_state"` в `write()` уже существует.
- Проверки:
  - `py_compile memory/working.py` → OK
  - smoke: блок содержит «Этап: paused» + «Пауза (вернуться к: execution)» + «Ожидаемое
    действие»; execution → «Этап: execution (шаг 2/3): Сравнить»; без task_state.json блок
    формируется как в Д12 (не падает) → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_memory 6, test_prompt 4 зелёные)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_4.md`

---

## Этап 4 — Оркестратор (`core/agent.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 4.1 ✅ / 4.2 ✅ / 4.3 ✅ / 4.4 ❌→✅ / 4.5 ✅
- Было: `Agent` — контракт дня 12 (identify/interview/respond/switch_profile/switch_task/
  save_state), без жизненного цикла задачи; `__init__` без executor/validator.
- Стало: полный жизненный цикл (arch §2.8):
  - импорты `TaskStage/TaskState/run_task/pause_task/resume_task/transition`, `asdict`,
    `safe_name`; `__init__` + `executor`/`validator` (инжектируемые, по умолчанию
    `LLMExecutor` + `default_validator`) и `self.task_state = None`;
  - класс `LLMExecutor` (plan/execute через LLMClient, блок working в execute) +
    `default_validator(results) = len(results) > 0` (заглушка задания);
  - `load_task_state()` (dict→TaskState, битый→None) — вызывается из `load_state()` и
    `switch_task()`; `_persist_task_state()` — единая точка: сейв JSON + зеркало
    `current_state` в working;
  - `start_task()` (safe_name → task_id, PLANNING, отметки working/long_term, сейв),
    `step_task()` (один проход run_task + сейв), `run_to_end(max_passes=50)` (до
    DONE/FAILED/PAUSED), `pause()`/`resume()` (guard: нет задачи/не тот этап → False),
    `retry_task()` (FAILED→PLANNING, steps/results/error очищены);
  - `save_state()` дополнительно сейвит `task_state.json`.
  Решение: `LLMExecutor` размещён рядом с оркестратором в `core/agent.py` (план 4.3).
- Проверки:
  - `py_compile core/agent.py` → OK
  - smoke (MockClient + StubExec, `.tmp/agent_fsm_*`): start_task→planning+файл;
    step_task→execution (шаг 0); pause→paused; **новый Agent, тот же memory-dir** →
    загрузил paused (step=1); resume→execution (шаг 1, план НЕ перестроен);
    run_to_end→done (results=3 без дублей); switch_task туда-обратно сохраняет состояния
    обеих задач; retry_task failed→planning; guard без задачи → False/None → всё OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_agent 4, test_person 9 зелёные — регресса нет)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → 9/9
- Повторы/ошибки: подшаг 4.4 — ❌ на первом прогоне smoke: в тесте путь
  `root/users/alice/...`, а `Store` кладёт в `root/alice/...` (без `users/`). Ошибка в
  тестовом скрипте, не в коде (отладка подтвердила: `task_state.json` создан). После
  правки путей в smoke — ✅.
- Следующий этап: `dev/migr_plan_5.md`

---

## Этап 5 — CLI (`Kod.py`) (2026-09-20)

- Статус: ✅ выполнен после 2 повторов
- Подшаги: 5.1 ✅ / 5.2 ✅ / 5.3 ✅
- Было: 12 команд без жизненного цикла; `show_state()` — только карта переходов;
  `--fresh` не знал `task_state.json`; в `--mock` план строился бы из «сырого» ответа
  MockClient (один шаг на сотни символов).
- Стало:
  - новые команды: `/plan <цель>` (start_task + первый проход: LLM/заглушка строит
    steps), `/step` (один проход + снимок), `/run` (run_to_end + снимок), `/pause`,
    `/resume`, ветка `/task retry` (failed→planning); guard-подсказки «сначала /plan
    <цель>»;
  - `show_state(agent)` — полный снимок TaskState (задача/id, этап, шаг N/M + текст,
    expected_action, previous_stage, error, число results) + карта переходов; хелпер
    `print_task_snapshot()` для компактной печати после команд;
  - `/help`, стартовая строка и шапка-комментарий дополнены новыми командами;
  - `--fresh` дополнительно сбрасывает `agent.task_state = None` (игнор JSON-снимка);
  - `core/agent.py`: добавлен `StubExecutor` (детерминированный план из 3 шагов) —
    инжектится в `build_agent()` при `--mock`/test-key (решение: план в mock-режиме
    должен быть человекочитаемым, arch §2.4 допускает заглушку исполнителя);
  - `core/state_machine.py` (уточнение Этапа 1): в ветке EXECUTION `expected_action`
    теперь = СЛЕДУЮЩИЙ шаг (после инкремента current_step), при последнем — «Проверить
    результаты»; семантика сверена с JSON-снимком из `Задание_Д13.txt`
    (current_step=1 ↔ expected_action="Собрать информацию").
- Проверки:
  - `py_compile Kod.py core/agent.py core/state_machine.py` → OK
  - **полный CLI-сценарий Д13 в двух процессах** (один `--memory-dir`): прогон 1
    `/plan «Найди три Python-фреймворка и сравни их»` → `/step` (шаг 1/3) → `/pause`
    (paused, вернуться к execution) → `/exit`; прогон 2 (новый процесс) `/resume`
    (execution, шаг 1/3 — НЕ 0, план не перестроен, задача не переспрошена) → `/run`
    → done 3/3, results=3 → `/state` снимок → EXIT 0 оба; `task_state.json` на диске
    совпадает со снимком
  - `--fresh` поверх done-состояния → «Нет активной задачи» (старт с PLANNING) → OK
  - регресс 12 старых команд (echo-пайп /memory /tasks /deliver /summary /tokens /cost
    /help /exit) → все маркеры на месте, EXIT 0
  - `/task retry` вне failed → подсказка «задача не в состоянии failed»
  - `unit_runner.py` → 41 OK, 0 FAIL; `smoke.py` → 0; `scenario.py` → 0; гейт → 9/9
- Повторы/ошибки:
  1. ❌ NameError `StubExecutor` — правка импорта в `Kod.py` не применилась с первого
     раза (инструмент отчитался об успехе, но строка осталась старой); повторный
     `replace` с расширенным контекстом — ✅.
  2. ❌ Семантика `expected_action` — первая реализация ставила «текущий шаг» до
     выполнения, из-за чего снимок после шага показывал уже выполненный шаг. Сверено с
     JSON-снимком `Задание_Д13.txt` → правка в `run_task()` (expected = следующий шаг),
     smoke 1.6 перезапущен — ✅.
- Следующий этап: `dev/migr_plan_6.md`

---

## Этап 6 — Тесты (`dev/tests_debug/`) (2026-09-20)

- Статус: ✅ выполнен после 2 повторов
- Подшаги: 6.1 ✅ (выполнен досрочно на Этапе 1 — отклонение зафиксировано там) /
  6.2 ✅ / 6.3 ✅ / 6.4 ❌→✅ (гейт)
- Было: L2 — 7 модулей, 41 тест (`test_state.py` уже мигрирован на Этапе 1); L3 smoke —
  2 прогона (in-process + CLI) без команд жизненного цикла; L4 — 6 сценариев;
  гейт — 9 проверок.
- Стало:
  - `unit/test_fsm.py` — 15 тестов по канону `Задание_Д13.txt`/arch §3.3: переходы
    (разрешённые/запрещённые, карта = next_state), дословный `test_pause_and_resume`
    (execution, шаг 2, «Выполнить шаг 3»), пауза на planning/execution/validation,
    идемпотентность pause/resume, save/load roundtrip (enum как строки, previous_stage),
    битый/отсутствующий файл → None, «перезапуск» → продолжение с current_step (план тот
    же, results=3 без дублей), expected_action = следующий шаг, validation: успех → done /
    ошибка → failed + error, failed → только planning. Всё на заглушках
    (`execute_step`/`validate_results`/`StubExecutor`), файлы — только `.tmp/`;
  - `scenario.py` — седьмой сценарий `scenario_pause_resume`: /plan «Найди три
    Python-фреймворка и сравни их» → шаг 0 → /pause → снимок JSON по канону задания
    (paused, previous_stage=execution, current_step=1, results=1) → новый Agent (тот же
    memory-dir) → /resume с шага 1 без повторного плана → /run → done, results=3 без
    дублей, лог содержит «[Автомат]»;
  - `smoke.py` — +2 прогона: `test_fsm_in_process` (plan→step→pause→«перезапуск»→resume→
    run→done) и `test_cli_fsm_subprocess` (CLI-пайп /plan /step /pause /resume /run /state,
    маркеры [План][Шаг][Пауза][Продолжение][Прогон][Состояние задачи], «Этап: done»);
  - `check_acceptance.sh` — проверка №10 «task_state.json переживает перезапуск
    (пауза→resume→done)»: CLI-пайп в два процесса во временном каталоге `.tmp/acc_PID`,
    grep по снимку («stage»: «paused» → «stage»: «done»).
- Проверки:
  - `env -u API_KEY $PY $TST/unit_runner.py` → **56 OK, 0 FAIL** (8 модулей: 41 прежний +
    15 fsm), EXIT 0
  - `env API_KEY=test-key $PY $TST/smoke.py` → 4 прогона OK, EXIT 0
  - `env API_KEY=test-key $PY $TST/scenario.py` → **7 сценариев** OK, EXIT 0
  - `API_KEY=test-key bash $TST/check_acceptance.sh` → **10 из 10** (FAIL=0), EXIT 0
  - Корень дня чист: каталог `$D` удалён, временные файлы только в `.tmp/`
- Повторы/ошибки:
  1. ❌ Гейт, проверка №10: «SNAP: не заданы границы переменной» (EXIT 1) — в теле
     `bash -c "…"` внутренние переменные (`$D`, `$MD`, `$SNAP`) раскрывались внешним
     шеллом вместо внутреннего (`set -u` → падение). Правка: экранирование `\# migr_log.md — журнал выполнения миграции `den_13` → `arch_den_13.md`

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_8.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §0.4, правила повтора — §0.3).
> Свод «было → стало» по Этапу F: `dev/logs_reports/stages/stage_F_state.md`.
>
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).

---

## Подшаги Этапа 0 (журнал хода)

| № | Подшаг | Проверка | Результат | Статус |
|---|---|---|---|---|
| 0.1 | Прогон базовой линии | `env -u API_KEY $PY dev/tests_debug/unit_runner.py` | 40 OK, 0 FAIL | ✅ EXIT 0 |
| 0.1 | — | `env API_KEY=test-key $PY dev/tests_debug/scenario.py` | 6 сценариев OK | ✅ EXIT 0 |
| 0.1 | — | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | 9 из 9 (FAIL=0) | ✅ EXIT 0 |
| 0.2 | Ознакомление с архитектурой | `arch_den_13.md` §2.2–2.9, §3.3, §4.3 + `Задание_Д13.txt` | регресс-лист 22 критерия + 3 новых (23–25) | ✅ |
| 0.2 | Создание журналов | `dev/logs_reports/stages/stage_F_state.md`, `dev/logs_reports/errors/`, этот файл | созданы | ✅ |
| 0.3 | Карта точек вставки | `state_machine.py`, `store.py`, `working.py`, `agent.py`, `Kod.py` | 5 файлов, точки зафиксированы (§3 stage_F_state.md) | ✅ |

**Найдено расхождений:** 4 (R1–R4, см. `stage_F_state.md` §4) — все учтены в планах Этапов 1, 5, 7.

---

## Этап 0 — Подготовка и приёмка базовой линии (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 0.1 ✅ / 0.2 ✅ / 0.3 ✅
- Было: `den_13` — копия `den_12` (персонализация + модель памяти); `core/state_machine.py`
  — задел (Enum `TaskState` из 4 стадий + `ALLOWED_TRANSITIONS` + `next_state()`);
  `store.py` не знает `task_state.json`; `working.py` даёт строку «Стадия задачи»;
  `agent.py` без жизненного цикла задачи; `Kod.py` — 12 команд; тесты L2 40 / L4 6 / гейт 9.
  В `dev/` отсутствуют `Проверка.md`, `meta_promt/`, `logs_reports/` (R1).
- Стало: базовая линия подтверждена тремя прогонами (все EXIT 0); созданы
  `dev/migr_log.md` (этот файл), `dev/logs_reports/stages/stage_F_state.md`
  (базовая линия + регресс-лист 22+3 критерия + карта точек вставки по 5 файлам +
  расхождения R1–R4), `dev/logs_reports/errors/`; рабочие планы Этапов 1, 5, 7
  скорректированы под фактическое состояние (R1, R3).
- Проверки:
  - `env -u API_KEY $PY dev/tests_debug/unit_runner.py` → 40 OK, 0 FAIL, EXIT 0
  - `env API_KEY=test-key $PY dev/tests_debug/scenario.py` → 6 сценариев OK, EXIT 0
  - `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → 9 из 9, EXIT 0
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_1.md`

---

## Этап 1 — Ядро автомата (`core/state_machine.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 1.1 ✅ / 1.2 ✅ / 1.3 ✅ / 1.4 ❌→✅ / 1.5 ✅ / 1.6 ✅ (+ внеплановая миграция
  `test_state.py`, см. ниже)
- Было: `core/state_machine.py` — задел (Enum `TaskState` 4 стадии + `ALLOWED_TRANSITIONS`
  4 ключа + `next_state()`); `Kod.py` импортировал `TaskState` как Enum.
- Стало: полный автомат — `TaskStage` (6 этапов), dataclass `TaskState` (9 полей канона),
  `ALLOWED_TRANSITIONS` (6 ключей, paused/failed), `transition()` (единственная точка смены
  этапа + лог «[Автомат]»), `next_state()` (обёртка совместимости), `pause_task()`/
  `resume_task()` (идемпотентные), `save_state()`/`load_state()` (JSON, enum↔.value, битый
  файл→None), `run_task(state, executor, validator)` (один проход). `Kod.py`: импорт
  `TaskStage`, `show_state()` по 6 этапам (R3 закрыт). `test_state.py` мигрирован на
  `TaskStage` (+ новый `test_paused_and_failed_extensions`).
- Проверки:
  - `py_compile core/state_machine.py Kod.py` → OK
  - smoke 1.2–1.6 (в `.tmp/fsm/`) → все OK: transition (planning→done ✗), pause/resume
    (канонический test_pause_and_resume), save/load roundtrip + битый/отсутствующий → None,
    run_task → DONE (3 results), failed+error, шаги не дублируются
  - `unit_runner.py` → **41 OK, 0 FAIL** (было 40; +1 новый тест state)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → **9/9**
- Повторы/ошибки: подшаг 1.4 — ❌ на первом прогоне: канонический `test_pause_and_resume`
  из `Задание_Д13.txt` требует, чтобы после resume `expected_action` был восстановлён, а
  пример `pause_task` в том же файле перезаписывает его на «Ожидать команды продолжения»
  (внутреннее противоречие первоисточника). **Решение:** приоритет отдан исполняемому тесту
  и JSON-снимку paused из `Задание_Д13.txt` (`expected_action="Собрать информацию"` —
  сохранённое) → `pause_task()` НЕ перезаписывает `expected_action`; факт паузы несёт
  `stage == PAUSED`. Зафиксировано комментарием в коде. После правки — ✅.
  **Отклонение от плана:** миграция `test_state.py` (планировалась на Этап 6.1) выполнена
  здесь — переименование Enum→`TaskStage` есть прямое следствие Этапа 1, и это снимает
  статус ⚠ (гейт зелёный на всех последующих этапах). На Этапе 6.1 останется только
  сверить тест с итоговым `test_fsm.py`.
- Следующий этап: `dev/migr_plan_2.md`

---

## Этап 2 — Хранилище (`storage/store.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 2.1 ✅
- Было: `Store` не знал `task_state.json`; docstring-дерево без снимка состояния.
- Стало: новая секция «Состояние задачи (state machine)» — `task_state_path()`,
  `read_task_state()` (отсутствует/битый → None), `write_task_state()` (через `ensure_task`
  + `write_json`); docstring-дерево дополнено `task_state.json`. Существующие методы не
  тронуты.
- Проверки:
  - `py_compile storage/store.py` → OK
  - smoke roundtrip (`.tmp/store_fsm_*`): write→read сохраняет все поля (включая
    previous_stage, error); read на отсутствующем → None → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_storage 7 зелёные — регрессии нет)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_3.md`

---

## Этап 3 — Память (`memory/working.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 3.1 ✅ / 3.2 ✅
- Было: `as_prompt_block()` давал строку «Стадия задачи: {current_state}» (зеркало).
- Стало: инжект формализованного состояния (arch §2.7) — хелпер `_task_state_lines(ctx)`
  читает `store.read_task_state` и добавляет строки «Этап: … (шаг N/M): …», «Пауза
  (вернуться к: …)», «Ожидаемое действие: …», «Ошибка: …»; строка «Стадия задачи»
  сохранена (обратная совместимость). `read()`/`write()` не менялись (контракт слоя).
  Решение 3.2: зеркало `current_state` пишется из `Agent._persist_task_state()` (Этап 4) —
  ветка `if key == "current_state"` в `write()` уже существует.
- Проверки:
  - `py_compile memory/working.py` → OK
  - smoke: блок содержит «Этап: paused» + «Пауза (вернуться к: execution)» + «Ожидаемое
    действие»; execution → «Этап: execution (шаг 2/3): Сравнить»; без task_state.json блок
    формируется как в Д12 (не падает) → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_memory 6, test_prompt 4 зелёные)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_4.md`

---

## Этап 4 — Оркестратор (`core/agent.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 4.1 ✅ / 4.2 ✅ / 4.3 ✅ / 4.4 ❌→✅ / 4.5 ✅
- Было: `Agent` — контракт дня 12 (identify/interview/respond/switch_profile/switch_task/
  save_state), без жизненного цикла задачи; `__init__` без executor/validator.
- Стало: полный жизненный цикл (arch §2.8):
  - импорты `TaskStage/TaskState/run_task/pause_task/resume_task/transition`, `asdict`,
    `safe_name`; `__init__` + `executor`/`validator` (инжектируемые, по умолчанию
    `LLMExecutor` + `default_validator`) и `self.task_state = None`;
  - класс `LLMExecutor` (plan/execute через LLMClient, блок working в execute) +
    `default_validator(results) = len(results) > 0` (заглушка задания);
  - `load_task_state()` (dict→TaskState, битый→None) — вызывается из `load_state()` и
    `switch_task()`; `_persist_task_state()` — единая точка: сейв JSON + зеркало
    `current_state` в working;
  - `start_task()` (safe_name → task_id, PLANNING, отметки working/long_term, сейв),
    `step_task()` (один проход run_task + сейв), `run_to_end(max_passes=50)` (до
    DONE/FAILED/PAUSED), `pause()`/`resume()` (guard: нет задачи/не тот этап → False),
    `retry_task()` (FAILED→PLANNING, steps/results/error очищены);
  - `save_state()` дополнительно сейвит `task_state.json`.
  Решение: `LLMExecutor` размещён рядом с оркестратором в `core/agent.py` (план 4.3).
- Проверки:
  - `py_compile core/agent.py` → OK
  - smoke (MockClient + StubExec, `.tmp/agent_fsm_*`): start_task→planning+файл;
    step_task→execution (шаг 0); pause→paused; **новый Agent, тот же memory-dir** →
    загрузил paused (step=1); resume→execution (шаг 1, план НЕ перестроен);
    run_to_end→done (results=3 без дублей); switch_task туда-обратно сохраняет состояния
    обеих задач; retry_task failed→planning; guard без задачи → False/None → всё OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_agent 4, test_person 9 зелёные — регресса нет)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → 9/9
- Повторы/ошибки: подшаг 4.4 — ❌ на первом прогоне smoke: в тесте путь
  `root/users/alice/...`, а `Store` кладёт в `root/alice/...` (без `users/`). Ошибка в
  тестовом скрипте, не в коде (отладка подтвердила: `task_state.json` создан). После
  правки путей в smoke — ✅.
- Следующий этап: `dev/migr_plan_5.md`

---

## Этап 5 — CLI (`Kod.py`) (2026-09-20)

- Статус: ✅ выполнен после 2 повторов
- Подшаги: 5.1 ✅ / 5.2 ✅ / 5.3 ✅
- Было: 12 команд без жизненного цикла; `show_state()` — только карта переходов;
  `--fresh` не знал `task_state.json`; в `--mock` план строился бы из «сырого» ответа
  MockClient (один шаг на сотни символов).
- Стало:
  - новые команды: `/plan <цель>` (start_task + первый проход: LLM/заглушка строит
    steps), `/step` (один проход + снимок), `/run` (run_to_end + снимок), `/pause`,
    `/resume`, ветка `/task retry` (failed→planning); guard-подсказки «сначала /plan
    <цель>»;
  - `show_state(agent)` — полный снимок TaskState (задача/id, этап, шаг N/M + текст,
    expected_action, previous_stage, error, число results) + карта переходов; хелпер
    `print_task_snapshot()` для компактной печати после команд;
  - `/help`, стартовая строка и шапка-комментарий дополнены новыми командами;
  - `--fresh` дополнительно сбрасывает `agent.task_state = None` (игнор JSON-снимка);
  - `core/agent.py`: добавлен `StubExecutor` (детерминированный план из 3 шагов) —
    инжектится в `build_agent()` при `--mock`/test-key (решение: план в mock-режиме
    должен быть человекочитаемым, arch §2.4 допускает заглушку исполнителя);
  - `core/state_machine.py` (уточнение Этапа 1): в ветке EXECUTION `expected_action`
    теперь = СЛЕДУЮЩИЙ шаг (после инкремента current_step), при последнем — «Проверить
    результаты»; семантика сверена с JSON-снимком из `Задание_Д13.txt`
    (current_step=1 ↔ expected_action="Собрать информацию").
- Проверки:
  - `py_compile Kod.py core/agent.py core/state_machine.py` → OK
  - **полный CLI-сценарий Д13 в двух процессах** (один `--memory-dir`): прогон 1
    `/plan «Найди три Python-фреймворка и сравни их»` → `/step` (шаг 1/3) → `/pause`
    (paused, вернуться к execution) → `/exit`; прогон 2 (новый процесс) `/resume`
    (execution, шаг 1/3 — НЕ 0, план не перестроен, задача не переспрошена) → `/run`
    → done 3/3, results=3 → `/state` снимок → EXIT 0 оба; `task_state.json` на диске
    совпадает со снимком
  - `--fresh` поверх done-состояния → «Нет активной задачи» (старт с PLANNING) → OK
  - регресс 12 старых команд (echo-пайп /memory /tasks /deliver /summary /tokens /cost
    /help /exit) → все маркеры на месте, EXIT 0
  - `/task retry` вне failed → подсказка «задача не в состоянии failed»
  - `unit_runner.py` → 41 OK, 0 FAIL; `smoke.py` → 0; `scenario.py` → 0; гейт → 9/9
- Повторы/ошибки:
  1. ❌ NameError `StubExecutor` — правка импорта в `Kod.py` не применилась с первого
     раза (инструмент отчитался об успехе, но строка осталась старой); повторный
     `replace` с расширенным контекстом — ✅.
  2. ❌ Семантика `expected_action` — первая реализация ставила «текущий шаг» до
     выполнения, из-за чего снимок после шага показывал уже выполненный шаг. Сверено с
     /`\"`
     для всех внутренних обращений → ✅.
  2. ❌ Загрязнение корня: `MD='\$D/users'` (одинарные кавычки) передавал literal `$D`
     в `--memory-dir` → в корне дня создавался мусорный каталог `$D/` с тестовыми
     данными. Правка: `MD=\"\$D/users\"`; `$D/` удалён → ✅.
     Карточка: `dev/logs_reports/errors/error_20260920_234900.md`.
     Примечание: буквальная правка `\# migr_log.md — журнал выполнения миграции `den_13` → `arch_den_13.md`

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_8.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §0.4, правила повтора — §0.3).
> Свод «было → стало» по Этапу F: `dev/logs_reports/stages/stage_F_state.md`.
>
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).

---

## Подшаги Этапа 0 (журнал хода)

| № | Подшаг | Проверка | Результат | Статус |
|---|---|---|---|---|
| 0.1 | Прогон базовой линии | `env -u API_KEY $PY dev/tests_debug/unit_runner.py` | 40 OK, 0 FAIL | ✅ EXIT 0 |
| 0.1 | — | `env API_KEY=test-key $PY dev/tests_debug/scenario.py` | 6 сценариев OK | ✅ EXIT 0 |
| 0.1 | — | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | 9 из 9 (FAIL=0) | ✅ EXIT 0 |
| 0.2 | Ознакомление с архитектурой | `arch_den_13.md` §2.2–2.9, §3.3, §4.3 + `Задание_Д13.txt` | регресс-лист 22 критерия + 3 новых (23–25) | ✅ |
| 0.2 | Создание журналов | `dev/logs_reports/stages/stage_F_state.md`, `dev/logs_reports/errors/`, этот файл | созданы | ✅ |
| 0.3 | Карта точек вставки | `state_machine.py`, `store.py`, `working.py`, `agent.py`, `Kod.py` | 5 файлов, точки зафиксированы (§3 stage_F_state.md) | ✅ |

**Найдено расхождений:** 4 (R1–R4, см. `stage_F_state.md` §4) — все учтены в планах Этапов 1, 5, 7.

---

## Этап 0 — Подготовка и приёмка базовой линии (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 0.1 ✅ / 0.2 ✅ / 0.3 ✅
- Было: `den_13` — копия `den_12` (персонализация + модель памяти); `core/state_machine.py`
  — задел (Enum `TaskState` из 4 стадий + `ALLOWED_TRANSITIONS` + `next_state()`);
  `store.py` не знает `task_state.json`; `working.py` даёт строку «Стадия задачи»;
  `agent.py` без жизненного цикла задачи; `Kod.py` — 12 команд; тесты L2 40 / L4 6 / гейт 9.
  В `dev/` отсутствуют `Проверка.md`, `meta_promt/`, `logs_reports/` (R1).
- Стало: базовая линия подтверждена тремя прогонами (все EXIT 0); созданы
  `dev/migr_log.md` (этот файл), `dev/logs_reports/stages/stage_F_state.md`
  (базовая линия + регресс-лист 22+3 критерия + карта точек вставки по 5 файлам +
  расхождения R1–R4), `dev/logs_reports/errors/`; рабочие планы Этапов 1, 5, 7
  скорректированы под фактическое состояние (R1, R3).
- Проверки:
  - `env -u API_KEY $PY dev/tests_debug/unit_runner.py` → 40 OK, 0 FAIL, EXIT 0
  - `env API_KEY=test-key $PY dev/tests_debug/scenario.py` → 6 сценариев OK, EXIT 0
  - `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → 9 из 9, EXIT 0
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_1.md`

---

## Этап 1 — Ядро автомата (`core/state_machine.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 1.1 ✅ / 1.2 ✅ / 1.3 ✅ / 1.4 ❌→✅ / 1.5 ✅ / 1.6 ✅ (+ внеплановая миграция
  `test_state.py`, см. ниже)
- Было: `core/state_machine.py` — задел (Enum `TaskState` 4 стадии + `ALLOWED_TRANSITIONS`
  4 ключа + `next_state()`); `Kod.py` импортировал `TaskState` как Enum.
- Стало: полный автомат — `TaskStage` (6 этапов), dataclass `TaskState` (9 полей канона),
  `ALLOWED_TRANSITIONS` (6 ключей, paused/failed), `transition()` (единственная точка смены
  этапа + лог «[Автомат]»), `next_state()` (обёртка совместимости), `pause_task()`/
  `resume_task()` (идемпотентные), `save_state()`/`load_state()` (JSON, enum↔.value, битый
  файл→None), `run_task(state, executor, validator)` (один проход). `Kod.py`: импорт
  `TaskStage`, `show_state()` по 6 этапам (R3 закрыт). `test_state.py` мигрирован на
  `TaskStage` (+ новый `test_paused_and_failed_extensions`).
- Проверки:
  - `py_compile core/state_machine.py Kod.py` → OK
  - smoke 1.2–1.6 (в `.tmp/fsm/`) → все OK: transition (planning→done ✗), pause/resume
    (канонический test_pause_and_resume), save/load roundtrip + битый/отсутствующий → None,
    run_task → DONE (3 results), failed+error, шаги не дублируются
  - `unit_runner.py` → **41 OK, 0 FAIL** (было 40; +1 новый тест state)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → **9/9**
- Повторы/ошибки: подшаг 1.4 — ❌ на первом прогоне: канонический `test_pause_and_resume`
  из `Задание_Д13.txt` требует, чтобы после resume `expected_action` был восстановлён, а
  пример `pause_task` в том же файле перезаписывает его на «Ожидать команды продолжения»
  (внутреннее противоречие первоисточника). **Решение:** приоритет отдан исполняемому тесту
  и JSON-снимку paused из `Задание_Д13.txt` (`expected_action="Собрать информацию"` —
  сохранённое) → `pause_task()` НЕ перезаписывает `expected_action`; факт паузы несёт
  `stage == PAUSED`. Зафиксировано комментарием в коде. После правки — ✅.
  **Отклонение от плана:** миграция `test_state.py` (планировалась на Этап 6.1) выполнена
  здесь — переименование Enum→`TaskStage` есть прямое следствие Этапа 1, и это снимает
  статус ⚠ (гейт зелёный на всех последующих этапах). На Этапе 6.1 останется только
  сверить тест с итоговым `test_fsm.py`.
- Следующий этап: `dev/migr_plan_2.md`

---

## Этап 2 — Хранилище (`storage/store.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 2.1 ✅
- Было: `Store` не знал `task_state.json`; docstring-дерево без снимка состояния.
- Стало: новая секция «Состояние задачи (state machine)» — `task_state_path()`,
  `read_task_state()` (отсутствует/битый → None), `write_task_state()` (через `ensure_task`
  + `write_json`); docstring-дерево дополнено `task_state.json`. Существующие методы не
  тронуты.
- Проверки:
  - `py_compile storage/store.py` → OK
  - smoke roundtrip (`.tmp/store_fsm_*`): write→read сохраняет все поля (включая
    previous_stage, error); read на отсутствующем → None → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_storage 7 зелёные — регрессии нет)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_3.md`

---

## Этап 3 — Память (`memory/working.py`) (2026-09-20)

- Статус: ✅ выполнен
- Подшаги: 3.1 ✅ / 3.2 ✅
- Было: `as_prompt_block()` давал строку «Стадия задачи: {current_state}» (зеркало).
- Стало: инжект формализованного состояния (arch §2.7) — хелпер `_task_state_lines(ctx)`
  читает `store.read_task_state` и добавляет строки «Этап: … (шаг N/M): …», «Пауза
  (вернуться к: …)», «Ожидаемое действие: …», «Ошибка: …»; строка «Стадия задачи»
  сохранена (обратная совместимость). `read()`/`write()` не менялись (контракт слоя).
  Решение 3.2: зеркало `current_state` пишется из `Agent._persist_task_state()` (Этап 4) —
  ветка `if key == "current_state"` в `write()` уже существует.
- Проверки:
  - `py_compile memory/working.py` → OK
  - smoke: блок содержит «Этап: paused» + «Пауза (вернуться к: execution)» + «Ожидаемое
    действие»; execution → «Этап: execution (шаг 2/3): Сравнить»; без task_state.json блок
    формируется как в Д12 (не падает) → OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_memory 6, test_prompt 4 зелёные)
  - `check_acceptance.sh` → 9/9
- Повторы/ошибки: нет
- Следующий этап: `dev/migr_plan_4.md`

---

## Этап 4 — Оркестратор (`core/agent.py`) (2026-09-20)

- Статус: ✅ выполнен после 1 повтора
- Подшаги: 4.1 ✅ / 4.2 ✅ / 4.3 ✅ / 4.4 ❌→✅ / 4.5 ✅
- Было: `Agent` — контракт дня 12 (identify/interview/respond/switch_profile/switch_task/
  save_state), без жизненного цикла задачи; `__init__` без executor/validator.
- Стало: полный жизненный цикл (arch §2.8):
  - импорты `TaskStage/TaskState/run_task/pause_task/resume_task/transition`, `asdict`,
    `safe_name`; `__init__` + `executor`/`validator` (инжектируемые, по умолчанию
    `LLMExecutor` + `default_validator`) и `self.task_state = None`;
  - класс `LLMExecutor` (plan/execute через LLMClient, блок working в execute) +
    `default_validator(results) = len(results) > 0` (заглушка задания);
  - `load_task_state()` (dict→TaskState, битый→None) — вызывается из `load_state()` и
    `switch_task()`; `_persist_task_state()` — единая точка: сейв JSON + зеркало
    `current_state` в working;
  - `start_task()` (safe_name → task_id, PLANNING, отметки working/long_term, сейв),
    `step_task()` (один проход run_task + сейв), `run_to_end(max_passes=50)` (до
    DONE/FAILED/PAUSED), `pause()`/`resume()` (guard: нет задачи/не тот этап → False),
    `retry_task()` (FAILED→PLANNING, steps/results/error очищены);
  - `save_state()` дополнительно сейвит `task_state.json`.
  Решение: `LLMExecutor` размещён рядом с оркестратором в `core/agent.py` (план 4.3).
- Проверки:
  - `py_compile core/agent.py` → OK
  - smoke (MockClient + StubExec, `.tmp/agent_fsm_*`): start_task→planning+файл;
    step_task→execution (шаг 0); pause→paused; **новый Agent, тот же memory-dir** →
    загрузил paused (step=1); resume→execution (шаг 1, план НЕ перестроен);
    run_to_end→done (results=3 без дублей); switch_task туда-обратно сохраняет состояния
    обеих задач; retry_task failed→planning; guard без задачи → False/None → всё OK
  - `unit_runner.py` → 41 OK, 0 FAIL (test_agent 4, test_person 9 зелёные — регресса нет)
  - `smoke.py` → EXIT 0; `scenario.py` → EXIT 0; `check_acceptance.sh` → 9/9
- Повторы/ошибки: подшаг 4.4 — ❌ на первом прогоне smoke: в тесте путь
  `root/users/alice/...`, а `Store` кладёт в `root/alice/...` (без `users/`). Ошибка в
  тестовом скрипте, не в коде (отладка подтвердила: `task_state.json` создан). После
  правки путей в smoke — ✅.
- Следующий этап: `dev/migr_plan_5.md`

---

## Этап 5 — CLI (`Kod.py`) (2026-09-20)

- Статус: ✅ выполнен после 2 повторов
- Подшаги: 5.1 ✅ / 5.2 ✅ / 5.3 ✅
- Было: 12 команд без жизненного цикла; `show_state()` — только карта переходов;
  `--fresh` не знал `task_state.json`; в `--mock` план строился бы из «сырого» ответа
  MockClient (один шаг на сотни символов).
- Стало:
  - новые команды: `/plan <цель>` (start_task + первый проход: LLM/заглушка строит
    steps), `/step` (один проход + снимок), `/run` (run_to_end + снимок), `/pause`,
    `/resume`, ветка `/task retry` (failed→planning); guard-подсказки «сначала /plan
    <цель>»;
  - `show_state(agent)` — полный снимок TaskState (задача/id, этап, шаг N/M + текст,
    expected_action, previous_stage, error, число results) + карта переходов; хелпер
    `print_task_snapshot()` для компактной печати после команд;
  - `/help`, стартовая строка и шапка-комментарий дополнены новыми командами;
  - `--fresh` дополнительно сбрасывает `agent.task_state = None` (игнор JSON-снимка);
  - `core/agent.py`: добавлен `StubExecutor` (детерминированный план из 3 шагов) —
    инжектится в `build_agent()` при `--mock`/test-key (решение: план в mock-режиме
    должен быть человекочитаемым, arch §2.4 допускает заглушку исполнителя);
  - `core/state_machine.py` (уточнение Этапа 1): в ветке EXECUTION `expected_action`
    теперь = СЛЕДУЮЩИЙ шаг (после инкремента current_step), при последнем — «Проверить
    результаты»; семантика сверена с JSON-снимком из `Задание_Д13.txt`
    (current_step=1 ↔ expected_action="Собрать информацию").
- Проверки:
  - `py_compile Kod.py core/agent.py core/state_machine.py` → OK
  - **полный CLI-сценарий Д13 в двух процессах** (один `--memory-dir`): прогон 1
    `/plan «Найди три Python-фреймворка и сравни их»` → `/step` (шаг 1/3) → `/pause`
    (paused, вернуться к execution) → `/exit`; прогон 2 (новый процесс) `/resume`
    (execution, шаг 1/3 — НЕ 0, план не перестроен, задача не переспрошена) → `/run`
    → done 3/3, results=3 → `/state` снимок → EXIT 0 оба; `task_state.json` на диске
    совпадает со снимком
  - `--fresh` поверх done-состояния → «Нет активной задачи» (старт с PLANNING) → OK
  - регресс 12 старых команд (echo-пайп /memory /tasks /deliver /summary /tokens /cost
    /help /exit) → все маркеры на месте, EXIT 0
  - `/task retry` вне failed → подсказка «задача не в состоянии failed»
  - `unit_runner.py` → 41 OK, 0 FAIL; `smoke.py` → 0; `scenario.py` → 0; гейт → 9/9
- Повторы/ошибки:
  1. ❌ NameError `StubExecutor` — правка импорта в `Kod.py` не применилась с первого
     раза (инструмент отчитался об успехе, но строка осталась старой); повторный
     `replace` с расширенным контекстом — ✅.
  2. ❌ Семантика `expected_action` — первая реализация ставила «текущий шаг» до
     выполнения, из-за чего снимок после шага показывал уже выполненный шаг. Сверено с
     -последовательностей выполнена Python-скриптом —
     инструмент `replace` экранирует обратные слэши.
- Следующий этап: `dev/migr_plan_7.md`
