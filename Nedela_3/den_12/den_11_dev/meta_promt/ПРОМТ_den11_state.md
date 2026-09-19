# ПРОМТ_den11_state — создание задела state machine (core/state_machine.py)

## 1. Цель и граница
Создать `TaskState` (Enum) с 4 базовыми стадиями и `ALLOWED_TRANSITIONS`. В Дне 11 —
ТОЛЬКО структура + хранение текущей стадии в рабочей памяти; логика переходов и
фильтр инвариантов — следующие дни недели 3.

Что НЕ делаем: не реализуем движок переходов/валидатор; НЕ удаляем ни одну из 4 стадий
(канон, Суть_N3 §4.8 п.1).

## 2. Вход (зависимостей НЕТ — изолированный слой)
- `Nedela_3/Суть_N3.md` §4.8 п.1 (4 стадии) и §3.4 (разрешённые переходы).
- `ND/arch/arch_den_11_plan_2.md` §3.7; `ND/arch/arch_den_11.md` §2.6.

## 3. Контракты (сигнатуры)
```python
class TaskState(Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    DONE = "done"

ALLOWED_TRANSITIONS = {
    TaskState.PLANNING:  {TaskState.EXECUTION},
    TaskState.EXECUTION: {TaskState.VALIDATION, TaskState.PLANNING},
    TaskState.VALIDATION:{TaskState.EXECUTION, TaskState.PLANNING},
    TaskState.DONE:      set(),
}

def next_state(current: TaskState, target: TaskState) -> bool
# вспомогательная проверка «разрешён ли переход»; логика переходов в Дне 11 НЕ ведётся.
```
Текущая стадия хранится в рабочей памяти: `working_memory.json → current_state`
(значение строкой из TaskState.value, по умолчанию "planning").

## 4. Выход (scope — только этот файл)
- `core/state_machine.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — `test_state.py` зелёный (exit 0). Проверяется: ровно 4
стадии; `next_state` истинно только для разрешённых переходов (planning→execution,
execution→validation/planning, validation→execution/planning) и ложно для запрещённых
(planning→done, done→*, planning→validation); DONE терминален.

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_07_state.md` (✅). Цикл отладки — §6.1.
Приёмка — §7 п.11 (задел state machine).