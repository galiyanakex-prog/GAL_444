# migr_plan_5.md — рабочий план этапа M5 «Тесты и отладка»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_15`
> на целевую архитектуру `Nedela_3/den_15/arch_den_15.md`. Разворачивает этап **M5** из
> `migr_plan.md` §4. Закрывает тестовый контур контролируемых переходов
> (`arch_den_15.md` §3.2).
> **Конец этого этапа — автоматический гейт в этап M6** (`migr_plan_6.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_15.md` §3.2, `Задание_Д15.txt`
> (проверки: попытки недопустимых состояний, реакция, продолжение после паузы).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M5** — Тесты и отладка |
| Рабочий план | `dev/migr_plan_5.md` (этот файл) |
| Зависит от | **M1–M4** (реализация) |
| Открывает | `dev/migr_plan_6.md` (M6 — Документация) |
| Закрывает | `arch_den_15.md` §3.2 (`test_transitions.py`, адаптация `test_fsm.py`, `scenario_controlled_transitions`, `smoke.py`, гейт 15) |
| Основные артефакты | `dev/tests_debug/unit/test_transitions.py` (новый), `test_fsm.py`, `scenario.py`, `smoke.py`, `check_acceptance.sh` |
| Живой ключ | **Не нужен** (`API_KEY=test-key` / `MockClient`; `env -u API_KEY` для L2) |
| Меняет поведение | **Нет** (только тестовый контур) |

**Цель этапа.** Закрыть все зафиксированные на M1–M4 отклонения (`test_fsm.py`,
`scenario_pause_resume`, `test_agent.py` — если были) и расширить контур: новый
модуль `test_transitions.py`, 9-й сценарий L4, гейт 15 проверок. Всё — без живого
ключа, временные файлы только в `.tmp/`.

---

## 1. Вход и предусловия

- Реализация M1–M4 зелёная по смоукам; список зафиксированных отклонений L2/L4 —
  в `migr_log.md` (M1/M3).
- Существующий контур: `unit_runner.py` (9 модулей, 76 тестов), `smoke.py`,
  `scenario.py` (8 сценариев), `check_acceptance.sh` (12 проверок).
- `pytest` в venv нет — L2 через `unit_runner.py`.

**Предусловия:** тесты не выходят в сеть; `users/` проекта не трогается; проверки
гейта идемпотентны.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 5.1 — `unit/test_transitions.py` (новый, канон arch §3.2)
Тесты (все на заглушках):
1. `test_can_transition_allowed`: `PLANNING→PLAN_APPROVED`, `PLAN_APPROVED→
   IMPLEMENTATION`, `IMPLEMENTATION→VALIDATION`, `VALIDATION→DONE` → `True`.
2. `test_can_transition_forbidden`: `NEW→IMPLEMENTATION`, `PLANNING→
   IMPLEMENTATION`, `IMPLEMENTATION→DONE`, `PLANNING→DONE`, `DONE→NEW`,
   `PAUSED→IMPLEMENTATION`, `PAUSED→DONE` → `False`.
3. `test_try_transition_rejects_without_state_change`: из `planning` в
   `implementation` → `InvalidTransitionError`; `stage`/`current_step`/`steps`/
   `results` не тронуты.
4. `test_invalid_transition_error_explains`: сообщение содержит «запрещён», стадии
   и список разрешённых.
5. `test_full_flow_with_approval`: `new → planning` (план построен, остановка) →
   `approve` → `plan_approved` → `implementation` (шаги) → `validation` → `done`;
   `results` без дублей.
6. `test_run_does_not_skip_approval`: `run_to_end` из `planning` останавливается в
   `planning`; в `transition_log` нет перехода в `implementation`.
7. `test_transition_log_records_attempts`: после отказа — запись `allowed=False` с
   `reason`; после успеха — `allowed=True`.
8. `test_refusal_texts`: `refusal_text(PLANNING, IMPLEMENTATION)` содержит «нельзя
   делать реализацию до утверждённого плана» и «/approve»;
   `refusal_text(IMPLEMENTATION, DONE)` — «нельзя … без валидации».
9. `test_pause_resume_same_position`: `pause` из `implementation` →
   `previous_stage=IMPLEMENTATION`; `resume` → та же стадия/шаг;
   `can_transition(IMPLEMENTATION, VALIDATION)` → `True`, `→ DONE` → `False`.
10. `test_restart_preserves_state_and_log`: save → load → стадия/шаг/журнал равны;
    `paused` после загрузки → `resume` → `implementation` с тем же `current_step`.
11. `test_snapshot_migration`: `from_dict` с `"execution"` → `IMPLEMENTATION`; без
    `transition_log` → `[]`.
12. `test_pause_is_not_loophole`: `can_transition(PAUSED, IMPLEMENTATION)` →
    `False`; `can_transition(PAUSED, DONE)` → `False`.
**Ожидаемый результат:** модуль зелёный в `unit_runner.py`.

### Шаг 5.2 — Адаптация `test_fsm.py` (закрытие ⚠ M1)
1. Заменить `EXECUTION` → `IMPLEMENTATION`; добавить стадии `NEW`/`PLAN_APPROVED`
   в проверки карты/переходов; флоу-тесты — под утверждение плана.
2. Прежнее покрытие не терять: переходы только по карте, pause/resume
   идемпотентность, round-trip, `max_passes`.
**Ожидаемый результат:** `test_fsm.py` зелёный; ⚠ M1 закрыт.

### Шаг 5.3 — Адаптация прочих зафиксированных ⚠
1. `test_agent.py` (если ⚠ M3): тесты `start_task`/флоу — под новый поток.
2. `scenario.py::scenario_pause_resume` (⚠ M1/M3): под новый флоу (с `/approve`).
**Ожидаемый результат:** все зафиксированные отклонения закрыты; L2/L4 полностью
зелёные.

### Шаг 5.4 — `scenario_controlled_transitions` (9-й сценарий L4)
Сквозной, по канону «Проверьте» задания (через CLI-субпроцесс или in-process — по
образцу существующих сценариев): `/plan` → `/goto implementation` (отказ, состояние
не изменилось) → `/approve` → `/goto done` (отказ) → `/run` → done → `/goto new`
(отказ, терминальная) → проверка `transition_log` (3 отказа) + ветка паузы
(перезапуск → resume → тот же шаг).
**Ожидаемый результат:** 9/9 сценариев OK.

### Шаг 5.5 — `smoke.py` (L3)
1. In-process + CLI subprocess с новым флоу (утверждение плана, отказ `/goto`);
   логи в `.tmp/`.
**Ожидаемый результат:** SMOKE OK.

### Шаг 5.6 — `check_acceptance.sh`: гейт 12 → 15
1. Добавить 3 проверки (идемпотентные, `TMP=$TST/.tmp/acc_$$`):
   - [13] недопустимый переход блокируется кодом: прогон CLI `/plan` → `/goto
     implementation` → вывод содержит «ОТКАЗАНО»/правило; `task_state.json` —
     стадия `planning` (не изменилась); в снимке есть `transition_log` с
     `allowed=false`;
   - [14] флоу утверждения: `/plan` → `/approve` → `/run` → `done` (снимок:
     стадия `done`, `results` заполнены);
   - [15] пауза → перезапуск → resume: два прогона CLI; после второго — стадия
     доведена до `done`, шаг не повторён (`results` без дублей).
2. Существующие 12 проверок не менять (README-проверки [2], [7] остаются ⚠ до M6).
**Ожидаемый результат:** гейт **13 из 15** (2 известных ⚠ README — до M6).

### Шаг 5.7 — Полный прогон
```bash
env -u API_KEY python dev/tests_debug/unit_runner.py   # L2: все зелёные
API_KEY=test-key python dev/tests_debug/smoke.py        # L3
API_KEY=test-key python dev/tests_debug/scenario.py     # L4: 9/9
API_KEY=test-key bash dev/tests_debug/check_acceptance.sh  # гейт: 13/15 (2⚠ README)
```
**Ожидаемый результат:** L2 — 0 FAIL (76 − адаптации + ~12 новых); L4 9/9; гейт
13+2⚠; всё EXIT 0.

---

## 3. Выход этапа

- `dev/tests_debug/unit/test_transitions.py` (новый); адаптированные `test_fsm.py`/
  `test_agent.py`/`scenario.py`/`smoke.py`; `check_acceptance.sh` (15 проверок).
- Все ⚠ M1–M4 закрыты.
- Запись этапа **M5** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M5→M6

Гейт считается **зелёным**, если одновременно:
- [ ] `test_transitions.py` зелёный (12 тестов канона arch §3.2);
- [ ] `test_fsm.py`/`test_agent.py`/`scenario_pause_resume` — ⚠ закрыты, L2 0 FAIL;
- [ ] L4 — 9 сценариев OK (вкл. `scenario_controlled_transitions`);
- [ ] гейт — 15 проверок, из них зелёных 13 (2 ⚠ README — единственные, причина
      зафиксирована, закрываются M6);
- [ ] всё без живого ключа; временные файлы только в `.tmp/`; `users/` не тронут;
- [ ] идемпотентность гейта (повторный прогон — тот же результат).

**Зелёный** → запись M5 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_6.md`.
**Красный** → карточка ошибки, этап M5 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4)

```text
## Этап M5 — Тесты и отладка
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: контур дня 14 (76 тестов, 8 сценариев, гейт 12); отклонения M1–M4
- Стало: <test_transitions.py; адаптация; scenario 9; гейт 15 (13+2⚠ README)>
- Проверка: <L2 N OK / L4 9/9 / гейт 13+2⚠, EXIT 0>
- Артефакты: dev/tests_debug/*
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M5→M6: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M6** по
`dev/migr_plan_6.md` (`README.md` с разделом «Контролируемые переходы состояний»,
`dev/Проверка.md` строки 31–35, `scen_1.md` под День 15; закрытие ⚠ README-проверок
гейта [2], [7]).
