# migr_plan_1.md — Рабочий план. Этап 1: Ядро автомата — `core/state_machine.py`

> **Тип файла: РАБОЧИЙ ПЛАН** (создан из план-эталона `dev/migr_plan.md`, раздел «Этап 1»).
> Миграция выполняется **по этому файлу**, подшаг за подшагом.
> **Автономный режим: включён по умолчанию** — действия считаются заранее одобренными;
> живые LLM-вызовы с реальным ключом — только с явного согласия пользователя.
>
> **Цель этапа:** развернуть задел дней 11–12 (Enum `TaskState` из 4 стадий + `next_state()`)
> в полный конечный автомат по `arch_den_13.md` §2.2–2.5: `TaskStage` (6 этапов), dataclass
> `TaskState`, `ALLOWED_TRANSITIONS` + `transition()`, `pause_task()`/`resume_task()`,
> `save_state()`/`load_state()` (JSON), `run_task()`.
>
> **Источники истины:** `Задание_Д13.txt` (блоки кода — канон) → `$ARCH` §2.2–2.5.

---

## Входные условия этапа

- [ ] Этап 0 завершён: в `dev/migr_log.md` есть запись «Этап 0 … ✅».
- [ ] Базовая линия зелёная (гейт 9/9 «до»).
- [ ] Переменные: `$KOD`, `$TST`, `$PY`, `$ARCH` — как в эталоне §0.5 п. 8.

## Правила этапа (наследуются из эталона §0.5 и §0.3)

1. Порядок подшагов **строгий**: модель → переходы → пауза → персистентность → цикл
   (1.4 зависит от имён 1.3, 1.6 — от 1.3–1.5).
2. После каждого подшага: `py_compile` + smoke-проверка → запись в `migr_log.md`.
3. Retry-цикл: при неуспехе — фиксация ❌, минимальная правка, повтор до ✅.
4. Smoke-файлы — только в `$TST/.tmp/`; не коммитить; `Задание_Д13.txt` не трогать.
5. **Осознанное исключение этапа:** `dev/tests_debug/unit/test_state.py` может упасть на
   старых именах — статус ⚠ в `migr_log.md` (миграция теста — Этап 6, подшаг 6.1);
   остальные 6 модулей unit-тестов обязаны быть зелёными.

---

## Подшаги этапа

### Подшаг 1.1 — `TaskStage` (6 этапов) + совместимость `Kod.py` (расхождение R3)
- Цель: заменить Enum `TaskState` (4 стадии) на `TaskStage(str, Enum)` из 6 этапов:
  PLANNING/EXECUTION/VALIDATION/PAUSED/DONE/FAILED; 4 базовых сохранены (канон: стадии
  расширяем, не сужаем).
  **R3 (из `stage_F_state.md` §4):** `Kod.py` строка 60 импортирует `TaskState` как Enum и
  `show_state()` итерирует по нему — после введения dataclass `TaskState` это сломает
  гейт [1] и smoke. Поэтому **в этом же подшаге** минимально правится `Kod.py`:
  импорт → `from core.state_machine import TaskStage, ALLOWED_TRANSITIONS`, `show_state()`
  → итерация по `TaskStage` (полное расширение `/state` снимком задачи — Этап 5.3).
- Прочитать: текущий `core/state_machine.py`; `Kod.py` (строка 60, раздел 12 `show_state()`).
- Изменить/создать: `core/state_machine.py` — класс `TaskStage`; `Kod.py` — импорт +
  `show_state()` (минимально, без новых команд).
- Проверка: `$PY -m py_compile core/state_machine.py Kod.py`; гейт [1] не падает.
- Запись в журнал: 1.1.
- Объём: ~40 строк чтения, ~25 строк правки.
- Кандидат на батч: да (с 1.2 — один файл, последовательные секции).

### Подшаг 1.2 — dataclass `TaskState`
- Цель: состояние задачи по канону задания: `task_id, objective, stage, current_step,
  steps[], expected_action, results[], previous_stage, error`.
- Прочитать: `Задание_Д13.txt` (блок `@dataclass TaskState`).
- Изменить/создать: `core/state_machine.py` — dataclass `TaskState` (дефолты как в задании).
- Проверка: `py_compile`; smoke: `$PY -c "from core.state_machine import TaskState; s=TaskState('t','цель'); print(s.stage, s.current_step)"` → `TaskStage.PLANNING 0`.
- Запись в журнал: 1.2.
- Объём: ~40 строк чтения, ~30 строк правки.
- Кандидат на батч: да (с 1.1).

### Подшаг 1.3 — `ALLOWED_TRANSITIONS` + `transition()`
- Цель: карта переходов §2.3 (planning→{execution,paused,failed}; execution→{validation,
  planning,paused,failed}; validation→{done,execution,planning,paused,failed}; paused→∅;
  done→∅; failed→{planning}) + единственная точка смены этапа `transition(state, target)
  -> bool` с логом «[Автомат] X → Y» / ворнингом «переход запрещён».
- Прочитать: `$ARCH` §2.3.
- Изменить/создать: `core/state_machine.py` — `ALLOWED_TRANSITIONS`, `transition()`;
  старая `next_state()` сохраняется как тонкая обёртка (обратная совместимость до миграции
  `test_state.py` на Этапе 6).
- Проверка: `py_compile`; smoke: transition(planning→execution)=True, (planning→done)=False.
- Запись в журнал: 1.3.
- Объём: ~30 строк чтения, ~40 строк правки.
- Кандидат на батч: нет (1.4 зависит от имён 1.3).

### Подшаг 1.4 — `pause_task()` / `resume_task()`
- Цель: пауза/продолжение по канону задания: pause сохраняет `previous_stage`, ставит
  `expected_action="Ожидать команды продолжения"`; resume возвращает в `previous_stage`
  (fallback EXECUTION), `current_step`/`expected_action` не трогает; обе идемпотентны
  (no-op на повторной паузе / resume не на паузе).
- Прочитать: `Задание_Д13.txt` (блоки pause/resume), `$ARCH` §2.3.
- Изменить/создать: `core/state_machine.py` — две функции.
- Проверка: `py_compile`; smoke в `$TST/.tmp/`: execution step=2 → pause → resume →
  step==2, stage==EXECUTION.
- Запись в журнал: 1.4.
- Объём: ~50 строк чтения, ~30 строк правки.
- Кандидат на батч: да (с 1.5 — один файл).

### Подшаг 1.5 — `save_state()` / `load_state()` (JSON)
- Цель: персистентность по канону задания: `asdict` + сериализация enum в `.value`
  (stage, previous_stage), `ensure_ascii=False, indent=2`; load — обратная конверсия
  `TaskStage(...)` → `TaskState(**data)`; битый/отсутствующий файл → `None` (не падает).
- Прочитать: `Задание_Д13.txt` (блоки save/load), `$ARCH` §2.5.
- Изменить/создать: `core/state_machine.py` — `save_state(state, filename)`,
  `load_state(filename) -> TaskState | None`.
- Проверка: `py_compile`; smoke: roundtrip через `$TST/.tmp/state.json`, поля равны.
- Запись в журнал: 1.5.
- Объём: ~40 строк чтения, ~40 строк правки.
- Кандидат на батч: да (с 1.4).

### Подшаг 1.6 — `run_task()` (один проход автомата)
- Цель: цикл исполнения §2.4: PLANNING → `executor.plan(objective)` → steps, step=0,
  transition(EXECUTION); EXECUTION → шаг → `executor.execute(step)` → results.append →
  current_step+1; шаги кончились → transition(VALIDATION); VALIDATION → `validator(results)`
  → DONE (expected_action=None) либо FAILED (error заполнен). `executor`/`validator` —
  параметры функции (LLM или заглушка).
- Прочитать: `Задание_Д13.txt` («Пример основного цикла» + заглушки), `$ARCH` §2.4.
- Изменить/создать: `core/state_machine.py` — `run_task(state, executor, validator)`.
- Проверка: `py_compile`; smoke на заглушках из задания (`execute_step`, `validate_results`):
  3 прохода → DONE, results из 3 элементов.
- Запись в журнал: 1.6.
- Объём: ~60 строк чтения, ~50 строк правки.
- Кандидат на батч: нет (зависит от 1.3–1.5; после него — общий `py_compile` файла).

---

## Чек-лист приёмки этапа

- [ ] `py_compile core/state_machine.py` — OK.
- [ ] `py_compile Kod.py` — OK (R3: импорт `TaskStage`, `show_state()` не падает);
      гейт `check_acceptance.sh` — по-прежнему 9/9 (кроме возможного ⚠ по п. [5] из-за
      `test_state.py`).
- [ ] Все smoke-проверки подшагов 1.2–1.6 пройдены (файлы smoke — в `$TST/.tmp/`).
- [ ] `TaskStage` содержит 6 этапов, из них 4 базовых (planning/execution/validation/done).
- [ ] `TaskState` — dataclass с 9 полями канона задания.
- [ ] `transition()` запрещает planning→done, done→*; `pause_task`/`resume_task` идемпотентны.
- [ ] `save_state`/`load_state` — roundtrip без потерь (enum → `.value` → enum).
- [ ] `unit_runner.py`: 6 модулей зелёные; `test_state.py` — ⚠ (зафиксировано в журнале).

## Последний пункт алгоритма этапа (выполняется только после ✅ приёмки)

1. Записать в `dev/migr_log.md` блок «## Этап 1 — Ядро автомата (`core/state_machine.py`)»
   по формату эталона §0.4 (Статус, Подшаги, Было/Стало, Проверки, Повторы/ошибки).
2. **Перейти к выполнению следующего этапа: открыть `dev/migr_plan_2.md` и начать с его
   подшага 2.1.** (Если этап не принят — повторять подшаги/правки до успеха.)
