# migr_plan_1.md — рабочий план этапа M1 «Ядро: состояния, карта, API контроля»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_15`
> на целевую архитектуру `Nedela_3/den_15/arch_den_15.md`. Разворачивает этап **M1** из
> `migr_plan.md` §4 в конкретные правки и проверки. Закрывает ядро строгой машины
> состояний (`arch_den_15.md` §2.2–2.6, §2.9).
> **Конец этого этапа — автоматический гейт в этап M2** (`migr_plan_2.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_15.md` §2.2–2.9, `Задание_Д15.txt`
> (API `can_transition`/`try_transition`/`InvalidTransitionError` — канон имён).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M1** — Ядро: состояния, карта, API контроля |
| Рабочий план | `dev/migr_plan_1.md` (этот файл) |
| Зависит от | **M0** (baseline, точки внедрения) |
| Открывает | `dev/migr_plan_2.md` (M2 — Хранение: transition_log + миграция снимков) |
| Закрывает | `arch_den_15.md` §2.2 (TaskStage 8, TaskState+transition_log), §2.3 (карта+API), §2.4 (запреты топологией), §2.5 (approve-флоу в run_task), §2.6 (REFUSAL_RULES), §2.9 (pause/resume на новых стадиях) |
| Основные артефакты | `core/state_machine.py` (модернизация) |
| Живой ключ | **Не нужен** (примитив-смоук инлайн, без LLM) |
| Меняет поведение | **Да** (автомат: новый флоу с утверждением плана; `/plan` больше не ведёт сразу в реализацию) — заявлено `arch_den_15.md` §2.5 |

**Цель этапа.** Превратить `core/state_machine.py` дня 13/14 в строгую машину состояний
канона `Задание_Д15.txt`: 8 допустимых состояний, whitelist-карта переходов,
программный контроль (`can_transition`/`try_transition`/`InvalidTransitionError`),
журнал переходов, утверждение плана как отдельная стадия, отказы с правилами.

---

## 1. Вход и предусловия

- `core/state_machine.py` текущий (день 13/14): `TaskStage` — 6 (без `NEW`/
  `PLAN_APPROVED`, с `EXECUTION`); `ALLOWED_TRANSITIONS` с прямой дугой
  `PLANNING → EXECUTION`; `transition() -> bool`; `next_state()` (задел, не
  вызывается); `pause_task`/`resume_task`; `run_task` сразу ведёт в реализацию.
- `core/agent.py`, `Kod.py` — callers автомата (адаптируются на M3/M4; на M1 —
  только минимальная правка имён, чтобы проект компилировался: замена
  `TaskStage.EXECUTION` → `TaskStage.IMPLEMENTATION` в callers, без изменения логики).
- M0 зелёный (baseline: L2 76 / L4 8 / гейт 10+2⚠).

**Предусловия:** контракты дней 11–14 вне автомата не трогать; `test_fsm.py` на этом
этапе **допустимо временно красным** (адаптация — M5), но L1 (компиляция) обязана быть
зелёной; падение прочих тестов недопустимо.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 1.1 — `TaskStage`: 8 состояний (канон имён из задания)
1. Переименовать `EXECUTION = "execution"` → `IMPLEMENTATION = "implementation"`.
2. Добавить `NEW = "new"` (задача создана, не начата) и
   `PLAN_APPROVED = "plan_approved"` (план утверждён).
3. Порядок в enum: `NEW`, `PLANNING`, `PLAN_APPROVED`, `IMPLEMENTATION`,
   `VALIDATION`, `DONE`, `PAUSED`, `FAILED`.
4. **Ожидаемый результат:** 8 состояний; 4 базовых этапа куратора детализированы
   (не удалены).

### Шаг 1.2 — `ALLOWED_TRANSITIONS`: whitelist по `arch_den_15.md` §2.3
```python
ALLOWED_TRANSITIONS = {
    TaskStage.NEW:            {TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PLANNING:       {TaskStage.PLAN_APPROVED, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PLAN_APPROVED:  {TaskStage.IMPLEMENTATION, TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.IMPLEMENTATION: {TaskStage.VALIDATION, TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.VALIDATION:     {TaskStage.DONE, TaskStage.IMPLEMENTATION, TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PAUSED:         set(),
    TaskStage.DONE:           set(),
    TaskStage.FAILED:         {TaskStage.PLANNING},
}
```
Ключевые запреты (топологией, не `if`): `PLANNING → IMPLEMENTATION` (нет дуги —
«нельзя реализацию до утверждённого плана»); `* → DONE` кроме `VALIDATION → DONE`
(«нельзя финал без валидации»); `PAUSED → *` (только `resume_task()`).
**Ожидаемый результат:** карта соответствует arch §2.3 построчно.

### Шаг 1.3 — API контроля (имена из `Задание_Д15.txt`)
1. `can_transition(from_state, to_state) -> bool` — `to_state in
   ALLOWED_TRANSITIONS.get(from_state, set())`.
2. `class InvalidTransitionError(Exception)`: поля `current`, `proposed`; сообщение
   «Переход X → Y запрещён. Разрешено из X: …».
3. `try_transition(state, proposed) -> TaskState`: отказ → `raise
   InvalidTransitionError` (состояние **не меняется**, попытка пишется в
   `transition_log` с `allowed=False`); успех → смена стадии + запись `allowed=True`.
4. `transition(state, target, log=None) -> bool` — обёртка над `try_transition`
   (ловит исключение, пишет ворнинг в лог, возвращает `False`) — обратная
   совместимость callers дня 13/14.
5. Удалить задел `next_state()` (замещён `can_transition`/`try_transition`; задел
   «не вызывается» — теперь есть рабочий API).
**Ожидаемый результат:** API канона задания; прежний `transition()` работает.

### Шаг 1.4 — `REFUSAL_RULES` (тексты правил отказов, `arch_den_15.md` §2.6)
Словарь `(from, to) → текст правила + корректный шаг`. Обязательные пары:
`(PLANNING, IMPLEMENTATION)`, `(NEW, IMPLEMENTATION)`, `(PLAN_APPROVED, DONE)`,
`(IMPLEMENTATION, DONE)`, `(PLANNING, DONE)`, `(DONE, *)` (терминальная),
`(PAUSED, *)` (только /resume). Функция `refusal_text(current, proposed) -> str`:
специальное правило или общий шаблон («Разрешено из X: …; ближайший корректный шаг:
<expected_action>»).
**Ожидаемый результат:** детерминированные тексты без LLM.

### Шаг 1.5 — `TaskState.transition_log` + `_log_transition`
1. Поле `transition_log: list[dict] = field(default_factory=list)`.
2. `_log_transition(state, frm, to, allowed, reason="")`: append
   `{"from", "to", "allowed", "reason", "at"}` (формат — arch §2.7).
3. `to_dict`/`from_dict`: сериализация `transition_log`; миграция: `"stage":
   "execution"` → `IMPLEMENTATION`; отсутствие `transition_log` → `[]`; отсутствие
   `stage`/неизвестное → `NEW` (дефолт входной стадии).
**Ожидаемый результат:** журнал в модели; старые снимки читаются.

### Шаг 1.6 — `approve_plan` + pause/resume на новых стадиях
1. `approve_plan(state, log=None)`: `PLANNING → PLAN_APPROVED` через
   `try_transition`; из других стадий — отказ с объяснением (не исключение:
   возвращаем текст отказа, состояние не меняется). Идемпотентность: из
   `PLAN_APPROVED` — «план уже утверждён».
2. `pause_task`: разрешён из `NEW`/`PLANNING`/`PLAN_APPROVED`/`IMPLEMENTATION`/
   `VALIDATION`; из `DONE`/`FAILED` — отказ с объяснением.
3. `resume_task`: возврат в `previous_stage` (fallback `IMPLEMENTATION`), не трогая
   `current_step`/`expected_action`/`steps`/`results`.
**Ожидаемый результат:** контрольный пункт утверждения + пауза на всех рабочих стадиях.

### Шаг 1.7 — `run_task`: новый поток (arch §2.5)
1. `PLANNING`: `executor.plan(objective)` → `steps[]`, `current_step=0`,
   `expected_action="утвердить план (/approve)"` — **остановка в `PLANNING`**
   (перехода в реализацию нет).
2. `PLAN_APPROVED`: переход в `IMPLEMENTATION` (первый шаг выполняется этим же
   проходом или следующим — по факту текущей реализации `run_task`; главное —
   переход только из `PLAN_APPROVED`).
3. `IMPLEMENTATION`: шаг → `results.append` → `current_step += 1`; шаги кончились →
   `VALIDATION`.
4. `VALIDATION`: `validator(results)` → `DONE` (`expected_action=None`) либо
   `FAILED` (`error`).
5. `NEW`: проход → переход в `PLANNING` (сборка плана).
**Ожидаемый результат:** `/run` из `planning` не может обойти утверждение.

### Шаг 1.8 — Минимальная правка callers (только компиляция)
1. `core/agent.py`, `Kod.py`: заменить `TaskStage.EXECUTION` →
   `TaskStage.IMPLEMENTATION` (механически, без изменения логики; полная адаптация
   флоу — M3/M4).
2. `grep -rn "EXECUTION" core/ Kod.py` → пусто.
**Ожидаемый результат:** L1 зелёный.

### Шаг 1.9 — Примитив-смоук (инлайн, без LLM)
```bash
python - <<'EOF'
# can_transition: разрешённые/запрещённые
# try_transition: отказ не меняет состояние; InvalidTransitionError объясняет
# полный поток: new → planning → approve → plan_approved → implementation →
#   шаги → validation → done; run_task из planning останавливается
# from_dict: "execution" → IMPLEMENTATION; без transition_log → []
EOF
```
**Ожидаемый результат:** все блоки смоука OK, EXIT 0.

### Шаг 1.10 — Регрессия (допустимые отклонения зафиксировать)
1. L1 `py_compile` → ok.
2. L2 `unit_runner.py`: ожидание — прочие модули зелёные; `test_fsm.py` —
   **допустимо ⚠ красным** (адаптация на M5; зафиксировать число падений в журнале).
3. L4 `scenario.py`: `scenario_pause_resume` — допустимо ⚠ (новый флоу); прочие —
   зелёные.
4. Гейт: 10+2⚠ (README) — без новых красных, кроме зафиксированных.
**Ожидаемый результат:** отклонения только перечисленные; каждое — с причиной.

---

## 3. Выход этапа

- Модернизированный `core/state_machine.py` (TaskStage 8, карта, API контроля,
  REFUSAL_RULES, transition_log, approve_plan, новый run_task).
- Минимальные правки `core/agent.py`/`Kod.py` (только имена стадий).
- Запись этапа **M1** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M1→M2

Гейт считается **зелёным**, если одновременно:
- [ ] `TaskStage` — 8 состояний; карта соответствует arch §2.3 построчно;
- [ ] `can_transition(PLANNING, IMPLEMENTATION)` → `False`;
      `can_transition(VALIDATION, DONE)` → `True`; `can_transition(PAUSED, *)` → `False`;
- [ ] `try_transition` из `planning` в `implementation` → `InvalidTransitionError`,
      `state.stage` **не изменился**, в `transition_log` запись `allowed=False`;
- [ ] полный поток `new → planning → (approve) → plan_approved → implementation →
      validation → done` проходит; `run_task` из `planning` останавливается
      (перехода в реализацию не было — по `transition_log`);
- [ ] `from_dict("execution")` → `IMPLEMENTATION`; без `transition_log` → `[]`;
- [ ] L1 зелёный; L2/L4 — отклонения только зафиксированные (`test_fsm` ⚠ до M5);
- [ ] контракты дней 11–14 вне автомата не тронуты (grep-сверка импортов/сигнатур).

**Зелёный** → запись M1 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_2.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап M1 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4 `migr_plan.md`)

```text
## Этап M1 — Ядро: состояния, карта, API контроля
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: TaskStage 6 (EXECUTION, без NEW/PLAN_APPROVED); переход PLANNING → EXECUTION
  напрямую; transition() -> bool; next_state() — задел; run_task сразу в реализацию
- Стало: <TaskStage 8; карта whitelist; can_transition/try_transition/
  InvalidTransitionError; REFUSAL_RULES; transition_log; approve_plan; run_task
  останавливается в planning>
- Проверка: <примитив-смоук; L1; L2/L4 с зафиксированными отклонениями>
- Артефакты: core/state_machine.py; минимальные правки agent.py/Kod.py
- Спорное/риски: <test_fsm ⚠ до M5; прочее>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M1→M2: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M2** по
`dev/migr_plan_2.md` (хранение: `transition_log` в `task_state.json`, миграция
снимков, зеркало `current_state` в `working.py`).
