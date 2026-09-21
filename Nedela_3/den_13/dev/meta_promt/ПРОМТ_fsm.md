# ПРОМТ_fsm — Этап F: Task State Machine (состояние задачи)

> Метапромт Этапа F миграции `den_13` на `ND/arch/arch_den_13.md`. Фиксирует контракты,
> созданные в ходе миграции (рабочие планы `dev/migr_plan_0.md … migr_plan_8.md`, журнал —
> `dev/migr_log.md`). Конвенция — как у `ПРОМТ_person.md` дня 12 (файл удалён по
> рекомендации куратора; образец сохранён в `den_12/dev/meta_promt/`).

## 1. Цель и граница

Развернуть задел дней 11–12 (`core/state_machine.py`: Enum из 4 стадий + `next_state()`)
в **полный конечный автомат задачи** по канону `Задание_Д13.txt`:

- в любой момент явно записаны **этап** (`stage`), **текущий шаг** (`current_step` +
  `steps[]`), **ожидаемое действие** (`expected_action`);
- переходы — только по `ALLOWED_TRANSITIONS` («код запрещает, промт рекомендует»);
- **пауза на любом рабочем этапе** сохраняет `previous_stage` и позицию шага;
- **продолжение без повторных объяснений**: план не перестраивается, выполненные шаги не
  повторяются, задача не переспрашивается — включая перезапуск процесса;
- **персистентность**: `task_state.json` сейвится после каждого перехода и при выходе;
- LLM составляет план и наполняет шаги, **Python-код управляет жизненным циклом**.

Что НЕ делаем: 4 базовых этапа не сужаем (paused/failed — расширения); не строим движок
оркестрации скиллов; `validator` — заглушка задания (`len(results) > 0`); изоляция стадий
уровня 2 (контейнеры/сессии) — задел; контракты дней 11–12 не ломаем (22 критерия зелёные).

## 1.1 Алгоритм внедрения (порядок по зависимостям, arch_den_13 §5)

Каждый шаг завершается L1 (`py_compile`) + smoke в `.tmp/` и НЕ ломает зелёные тесты
предыдущих шагов; результат — записью в `dev/migr_log.md`.

1. **`core/state_machine.py`** (Этап 1): `TaskStage` (6) → `TaskState` (dataclass, 9 полей)
   → `ALLOWED_TRANSITIONS` + `transition()` (единственная точка смены этапа, лог
   «[Автомат] X → Y») → `pause_task()`/`resume_task()` (идемпотентные) →
   `save_state()`/`load_state()` (JSON, enum ↔ `.value`, битый файл → None) →
   `run_task(state, executor, validator)` (один проход). `next_state()` — обёртка.
2. **`storage/store.py`** (Этап 2): секция «Состояние задачи» — `task_state_path()` /
   `read_task_state()` (отсутствует/битый → None) / `write_task_state()`; прочие методы
   не тронуты.
3. **`memory/working.py`** (Этап 3): `as_prompt_block()` += `_task_state_lines()` —
   «Этап: … (шаг N/M): …», «Ожидаемое действие: …», «Пауза (вернуться к: …)», «Ошибка: …»;
   строка «Стадия задачи» сохранена (зеркало). `read()`/`write()` не меняются.
4. **`core/agent.py`** (Этап 4): `self.task_state` + `load_task_state()` (из `load_state()`
   и `switch_task()`) → `start_task()` + `_persist_task_state()` (единая точка: сейв JSON +
   зеркало `current_state`) → `LLMExecutor`/`StubExecutor` + `step_task()`/`run_to_end(50)`
   → `pause()`/`resume()` (guard: нет задачи/не тот этап → False) → интеграция с
   `save_state()`/`switch_task()` + `retry_task()` (failed → planning, steps/results/error
   очищены).
5. **`Kod.py`** (Этап 5): `/plan <цель>`, `/step`, `/run`, `/pause`, `/resume`, ветка
   `/task retry`; `/state` — полный снимок TaskState + карта переходов; `/help`, стартовая
   строка, `--fresh` (сброс `task_state`).
6. **Тесты** (Этап 6): миграция `test_state.py` на `TaskStage` → `unit/test_fsm.py`
   (15 тестов по канону «Что именно протестировать») → `scenario_pause_resume` (L4, 7-й)
   → `smoke.py` (+2 прогона) → гейт (+проверка №10).
7. **Документация** (Этап 7): README += «Состояние задачи (Task State Machine)»;
   `dev/Проверка.md` += строки 23–25; этот файл.

## 2. Контракты (источник истины — arch_den_13 §2.2–2.8)

### 2.1 Модель состояния
```python
class TaskStage(str, Enum):
    PLANNING = "planning"; EXECUTION = "execution"; VALIDATION = "validation"
    PAUSED = "paused"; DONE = "done"; FAILED = "failed"   # paused/failed — расширения

@dataclass
class TaskState:
    task_id: str; objective: str
    stage: TaskStage = TaskStage.PLANNING
    current_step: int = 0
    steps: list = field(default_factory=list)
    expected_action: Optional[str] = None
    results: list = field(default_factory=list)
    previous_stage: Optional[TaskStage] = None
    error: Optional[str] = None
```

### 2.2 Карта переходов
```python
ALLOWED_TRANSITIONS = {
    PLANNING:   {EXECUTION, PAUSED, FAILED},
    EXECUTION:  {VALIDATION, PLANNING, PAUSED, FAILED},
    VALIDATION: {DONE, EXECUTION, PLANNING, PAUSED, FAILED},
    PAUSED:     set(),          # выход только через resume_task()
    DONE:       set(),          # терминальная
    FAILED:     {PLANNING},     # восстановление — явный /task retry
}
def transition(state, target, log=None) -> bool   # единственная точка смены этапа
```

### 2.3 Пауза/продолжение (идемпотентные, не через transition)
- `pause_task(state)`: повторная пауза — no-op; сохраняет `previous_stage`, ставит PAUSED.
  **Решение миграции** (внутреннее противоречие первоисточника, `migr_log.md` Этап 1):
  `expected_action` НЕ перезаписывается — канонический `test_pause_and_resume` и
  JSON-снимок paused из `Задание_Д13.txt` требуют восстановления ожидаемого действия;
  факт паузы несёт `stage == PAUSED`.
- `resume_task(state)`: не на паузе — no-op; возврат в `previous_stage` (fallback
  EXECUTION); `current_step`/`expected_action` не тронуты.

### 2.4 Персистентность
- `save_state(state, filename)`: `asdict` + enum → `.value`, `ensure_ascii=False, indent=2`.
- `load_state(filename) -> TaskState | None`: битый/отсутствующий → None (не падает).
- Путь знает только фасад: `users/<id>/tasks/<task>/task_state.json`
  (`store.task_state_path/read_task_state/write_task_state`).
- Зеркало: `working_memory.json.current_state` (авторитет — `task_state.json`).

### 2.5 Цикл исполнения
- `run_task(state, executor, validator, log=None)` — один атомарный проход:
  PLANNING → `executor.plan(objective)` → steps, step=0 → EXECUTION;
  EXECUTION → `executor.execute(step)` → `results.append` → `current_step += 1`
  (**решение миграции**, `migr_log.md` Этап 5: `expected_action` = СЛЕДУЮЩИЙ шаг —
  семантика JSON-снимка задания: current_step=1 ↔ expected_action=steps[1]; при последнем
  шаге — «Проверить результаты»); шаги кончились → VALIDATION;
  VALIDATION → `validator(results)` → DONE (expected_action=None) | FAILED (error заполнен).
- Инжектируемые зависимости: `executor` — `.plan(objective) -> list[str]`,
  `.execute(step) -> Any` (`LLMExecutor` — живой режим; `StubExecutor` — детерминированный
  план из 3 шагов для `--mock`/`test-key`); `validator(results) -> bool`
  (`default_validator = len(results) > 0` — заглушка задания).
- `Agent.run_to_end(max_passes=50)` — защита от бесконечного цикла.

### 2.6 CLI (arch §2.9)
`/plan <цель>` · `/step` · `/run` · `/pause` · `/resume` · `/task retry` — новые;
`/state` — расширена (снимок TaskState + карта переходов); `--fresh` дополнительно
игнорирует `task_state.json`. Без активной задачи — подсказка «сначала /plan <цель>».

## 3. Критерии приёмки Этапа F (arch §4.3, строки 23–25 `dev/Проверка.md`)

| № | Критерий | Чем проверяется |
|---|---|---|
| 23 | Формализованное состояние (этап/шаг/ожидаемое действие) | `test_fsm.py` (поля dataclass), `/state`, блок working в промте |
| 24 | Пауза на любом этапе + продолжение без повторных объяснений | `test_fsm.py` (pause/resume на planning/execution/validation, no-op), `scenario_pause_resume` (перезапуск → resume с того же шага, план не перестроен) |
| 25 | Персистентность и жизненный цикл | save/load roundtrip, «перезапуск» → продолжение с `current_step`, шаги не повторяются, validation → done/failed, переходы только по `ALLOWED_TRANSITIONS`, гейт-проверка №10 |

Регресс: прежние 22 критерия зелёные. Гейт: L2 (56) → L3 (4 прогона) → L4 (7 сценариев) →
`check_acceptance.sh` 10/10 — всё без живого ключа.

## 4. Запреты (наследуются из START-PROMT.md)

- не менять `Задание_Д13.txt`, файлы других дней, `ND/arch/*` (кроме чтения);
- временные файлы — только `dev/tests_debug/.tmp/`;
- живые LLM-вызовы — только с явного согласия пользователя (тесты — MockClient/заглушки);
- ничего не коммитить без прямой команды пользователя.
