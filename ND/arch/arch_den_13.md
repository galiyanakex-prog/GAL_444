# arch_den_13.md — итоговая целевая архитектура проекта `den_13` «Состояние задачи (Task State Machine)»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_13`. Базируется на `ND/arch/arch_den_12.md` (персонализация поверх модели
> памяти) и дополняет его **формализованным состоянием задачи**: конечный автомат этапов
> (stage), текущий шаг (current_step), ожидаемое действие (expected_action), пауза на любом
> этапе и продолжение без повторных объяснений.
> Источники: `Суть_N3.md`, `Задание_Д13.txt` (неизменяемый первоисточник).

---

## 0. Назначение документа

Документ фиксирует три слоя итогового состояния:

1. **Рабочая архитектура** — персонализированный stateful-агент с явной моделью памяти
   (4 слоя) и мультипрофильностью, унаследованный от `den_12` без изменений контрактов,
   **плюс task state machine**: задел `core/state_machine.py` (День 11/12 — только Enum
   из 4 стадий и `next_state()`) разворачивается в полный конечный автомат задачи с
   паузой, продолжением и персистентностью.
2. **Служебное пространство `dev/`** — «проект про проект»: всё, чем агент автономно
   создаёт, тестирует и отлаживает проект, с полным аудитом каждого этапа.

Главная идея задания (канон `Задание_Д13.txt`): **LLM может принимать решения и составлять
план, но отдельный Python-код управляет жизненным циклом задачи**. Планирование, выполнение,
проверка, пауза и продолжение происходят через явно заданные переходы, а не только через
текстовую историю диалога.

---

## 1. Ключевая идея и принципы

### 1.1 Ключевая идея
`den_13` — переход от «профиль-персонализации» (день 12) к **агенту с формализованным
состоянием задачи**. В каждый момент времени явно записано:

1. **На каком этапе** находится задача (`stage`: planning / execution / validation / paused / done / failed).
2. **Какой конкретный шаг** сейчас выполняется (`current_step` + `steps[]`).
3. **Какое действие ожидается** дальше (`expected_action`).

Агент не спрашивает каждый раз LLM «что происходит»: он читает `TaskState` и знает —
сейчас выполняется шаг 1, ожидается вызов инструмента. Это и есть конечный автомат:
система находится в одном состоянии и переходит в другое только по определённым правилам.

Формула ценности дня: **пауза на любом этапе → продолжение с того же места, без повторных
объяснений** — план не перестраивается, выполненные шаги не повторяются, задача не
переспрашивается.

### 1.2 Принципы
- **4 базовых этапа не убирать** (канон куратора, `Суть_N3.md`): planning → execution →
  validation → done. Стадии можно **расширять** (добавлены `paused` и `failed`), сужение —
  «на свой страх и риск».
- **Переходы только по разрешённым правилам** — `ALLOWED_TRANSITIONS` проверяется кодом;
  запрещённый переход не выполняется и логируется («код запрещает, промт рекомендует»).
- **`paused` — не потеря состояния**: перед паузой сохраняется `previous_stage`,
  `current_step` и `expected_action`; resume возвращает ровно в ту же точку.
- **История ≠ состояние** (наследие дней 11–12): неизменяемые сообщения (`parent_id`) vs
  пересчитываемое состояние задачи; теперь состояние задачи — отдельная сущность
  `TaskState` со своим файлом.
- **Персистентность**: состояние сейвится в JSON на каждом переходе и при выходе; после
  перезапуска программы задача продолжается «с того же места» (механика resume из лекции:
  «через 12 часов — а, точно, мы делали вот это, продолжаем»).
- **Инжект стейта в промт (уровень 1 — build-prompt)**: этап, шаг и ожидаемое действие
  попадают в блок рабочей памяти каждого промта + правило роли «работай в рамках текущего
  шага, не перепрыгивая этапы». Полная изоляция стадий (уровень 2 — контейнеры/отдельные
  сессии) — задел, не объём дня.
- **Детерминизм без LLM**: автомат (переходы, пауза, resume, save/load) полностью
  тестируется на заглушках — живой ключ не нужен.
- **Полиморфизм через интерфейсы, инкапсуляция через фасады** — наследуются из дней 11–12
  без изменений (`MemoryLayer`, `LLMClient`, `Store`).

---

## 2. Рабочая структура проекта

### 2.1 Дерево модулей

```
Nedela_3/den_13/
├── Kod.py                       # точка входа: DI-композиция + REPL (+ команды жизненного цикла)
├── core/
│   ├── __init__.py
│   ├── agent.py                 # оркестратор: + start_task/step_task/run_to_end/pause/resume
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient (без изменений)
│   ├── profile_router.py        # ProfileRouter (без изменений от дня 12)
│   ├── prompt_builder.py        # BLOCK_ORDER + deliver + budget (без изменений)
│   └── state_machine.py         # ← РАЗВЁРНУТЫЙ ЗАДЕЛ: TaskStage + TaskState + переходы + pause/resume
├── memory/
│   ├── __init__.py
│   ├── base.py                  # MemoryLayer (ABC) + MemoryContext(+profile_id) + PolicyEngine (задел)
│   ├── short_term.py            # ShortTermMemory — неизменяемые сообщения (parent_id)
│   ├── working.py               # WorkingMemory — + этап/шаг/ожидаемое действие в блоке промта
│   ├── long_term.py             # LongTermMemory — + статусы задач (done/failed) в decisions
│   ├── profile.py               # Profile — style + constraints + context + skills (без изменений)
│   └── manager.py               # MemoryManager — явная маршрутизация «что куда»
├── storage/
│   ├── __init__.py
│   ├── store.py                 # фасад: + task_state.json (read/write_task_state)
│   └── db.py                    # ProfileRepository (без изменений от дня 12)
├── users/                       # рантайм-хранилище (создаётся при работе)
├── run.sh                       # +x: cd dirname + source ../../.venv/bin/activate + python
├── run.desktop                  # Exec = абсолютный путь к .sh
├── README.md                    # + раздел «Состояние задачи (Task State Machine)»
├── Den_log.md                   # журнал: + строки переходов автомата (рантайм-артефакт)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
├── Задание_Д13.txt              # постановка куратора (неизменяемый первоисточник)
├── START-PROMT.md               # управляющий промт автономного создания (+ Этап F)
└── dev/                         # ← служебное пространство (раздел 3), в т.ч. Проверка.md
```

Naming-конвенция дня 12 сохраняется: признак дня из имён файлов и внутренних путей удалён —
проект скопирован в `den_13` без переименований (внешняя ссылка `ND/arch/arch_den_13.md` —
единственное место с номером дня, кроме `Задание_Д13.txt` и абсолютных путей в `run.desktop`).

### 2.2 Модель состояния задачи (`core/state_machine.py`)

Задел дней 11–12 (Enum `TaskState` из 4 стадий + `next_state()`) разворачивается в полную
модель по канону `Задание_Д13.txt`. Имена — как в задании: **`TaskStage`** (enum этапов)
и **`TaskState`** (dataclass состояния); старый `test_state.py` мигрирует на новые имена
(`TaskState`-enum → `TaskStage`), проверки 4 базовых стадий и переходов сохраняются.

```python
# core/state_machine.py
class TaskStage(str, Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    PAUSED = "paused"        # ← расширение базовых 4 этапов (не замена)
    DONE = "done"
    FAILED = "failed"        # ← расширение: ошибка валидации/исполнения


@dataclass
class TaskState:
    task_id: str
    objective: str

    stage: TaskStage = TaskStage.PLANNING
    current_step: int = 0
    steps: list[str] = field(default_factory=list)

    expected_action: str | None = None
    results: list[Any] = field(default_factory=list)

    previous_stage: TaskStage | None = None   # куда вернуться после паузы
    error: str | None = None
```

Ответ на три вопроса задания в любой момент: `stage` (этап), `current_step` + `steps`
(текущий шаг), `expected_action` (ожидаемое действие).

### 2.3 Карта переходов

Базовая схема (канон, не убирать):

```text
planning
   ↓
execution
   ↓
validation
   ├── успех → done
   └── ошибка → execution (ретрай) или failed
```

С паузой (пауза допустима на любом рабочем этапе):

```text
planning ─────┐
execution ────┼──→ paused ──→ продолжение предыдущего этапа (previous_stage)
validation ───┘
```

```python
ALLOWED_TRANSITIONS = {
    TaskStage.PLANNING:   {TaskStage.EXECUTION, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.EXECUTION:  {TaskStage.VALIDATION, TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.VALIDATION: {TaskStage.DONE, TaskStage.EXECUTION, TaskStage.PLANNING,
                           TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PAUSED:     set(),   # выход только через resume_task() → previous_stage
    TaskStage.DONE:       set(),   # терминальная
    TaskStage.FAILED:     {TaskStage.PLANNING},   # восстановление — явный /task retry
}

def transition(state: TaskState, target: TaskStage) -> bool:
    """Единственная точка смены этапа: проверка ALLOWED_TRANSITIONS + лог.
    Запрещённый переход → False + ворнинг в лог («[Автомат] переход запрещён: X → Y»)."""
```

Пауза и продолжение — отдельные функции (не через `transition`), идемпотентные:

```python
def pause_task(state: TaskState) -> TaskState:
    if state.stage == TaskStage.PAUSED:
        return state                      # повторная пауза — no-op
    state.previous_stage = state.stage    # paused — НЕ потеря состояния
    state.stage = TaskStage.PAUSED
    state.expected_action = "Ожидать команды продолжения"
    return state

def resume_task(state: TaskState) -> TaskState:
    if state.stage != TaskStage.PAUSED:
        return state                      # resume не на паузе — no-op (проверяется тестом)
    state.stage = state.previous_stage or TaskStage.EXECUTION
    state.previous_stage = None
    return state                          # current_step и expected_action не тронуты
```

Если агент остановлен во время `execution` на шаге 2, после resume он возвращается именно
к `execution`, шагу 2 — планирование заново не строится.

### 2.4 Цикл исполнения (`run_task` — один проход автомата)

```python
def run_task(state: TaskState, executor, validator) -> TaskState:
    if state.stage == TaskStage.PLANNING:
        # План составляет LLM (или MockClient); код только принимает список шагов.
        state.steps = executor.plan(state.objective)
        state.current_step = 0
        state.expected_action = "Перейти к выполнению"
        transition(state, TaskStage.EXECUTION)

    elif state.stage == TaskStage.EXECUTION:
        if state.current_step >= len(state.steps):
            state.expected_action = "Проверить результаты"
            transition(state, TaskStage.VALIDATION)
            return state
        step = state.steps[state.current_step]
        state.expected_action = step
        result = executor.execute(step)          # здесь агент вызывает нужный инструмент/LLM
        state.results.append(result)
        state.current_step += 1                  # завершённые шаги НЕ повторяются

    elif state.stage == TaskStage.VALIDATION:
        if validator(state.results):
            state.expected_action = None
            transition(state, TaskStage.DONE)
        else:
            state.error = "Проверка результата не пройдена"
            transition(state, TaskStage.FAILED)  # либо EXECUTION — ограниченный ретрай

    return state
```

- `executor` / `validator` — инжектируемые зависимости: живая LLM (`RouterAIClient`) или
  детерминированная заглушка (`MockClient`, функции-заглушки из задания) — автомат
  тестируется без сети.
- Каждый проход = один атомарный шаг; REPL-команда `/step` делает ровно один проход,
  `/run` — крутит до `done`/`failed`/`paused` с защитой от бесконечного цикла (лимит проходов).
- Любая смена состояния пишется в лог: «[Автомат] planning → execution (шаг 0/3: …)».

### 2.5 Персистентность состояния (`task_state.json`)

```python
# core/state_machine.py — save_state/load_state (JSON, канон задания)
def save_state(state: TaskState, filename: str) -> None:
    data = asdict(state)
    data["stage"] = state.stage.value
    if state.previous_stage:
        data["previous_stage"] = state.previous_stage.value
    ...  # json.dump, ensure_ascii=False, indent=2

def load_state(filename: str) -> TaskState:
    ...  # json.load → TaskStage(...) → TaskState(**data)
```

```python
# storage/store.py — фасад знает путь (агент — нет)
def task_state_path(self, user_id, task_name) -> str   # users/<id>/tasks/<task>/task_state.json
def read_task_state(self, user_id, task_name) -> dict | None   # None — состояния ещё нет
def write_task_state(self, user_id, task_name, data: dict) -> str
```

Снимок состояния на диске (пример из задания — пауза посреди execution):

```json
{
  "task_id": "task-001",
  "objective": "Найди три Python-фреймворка и сравни их",
  "stage": "paused",
  "previous_stage": "execution",
  "current_step": 1,
  "steps": ["Найти три фреймворка", "Собрать информацию", "Сравнить фреймворки"],
  "expected_action": "Ожидать команды продолжения",
  "results": ["Найдены Django, Flask и FastAPI"],
  "error": null
}
```

Правила:
- сейв — после **каждого** перехода/шага и при `/exit` (а также `EOFError`/`KeyboardInterrupt`);
- лоад — при старте, при `load_state(user_id)` и при `/task <имя>` (переключение задачи
  подтягивает её собственное состояние);
- битый/отсутствующий `task_state.json` не роняет приложение — задача стартует с
  `PLANNING` (конвенция `store.py`: чтение всегда возвращает схему по умолчанию);
- `working_memory.json.current_state` остаётся **зеркалом** стадии (обратная совместимость
  с днями 11–12); авторитет — `task_state.json`.

### 2.6 Иерархия хранения (канон + task_state.json)

```
users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite)
├── profiles/                    # зеркала всех профилей (день 12, без изменений)
├── long_term_memory.json        # {profile_ref, tasks[], decisions[], knowledge[]}
└── tasks/<task_name>/
    ├── task_state.json          # ← НОВОЕ: снимок TaskState (автомат задачи)
    ├── working_memory.json      # состояние задачи (+ current_state — зеркало стадии)
    ├── sessions_resume.md       # резюме сессий (только данные о задаче)
    └── sessions/<session_id>/
        └── session.json         # краткосрочная память: сообщения с parent_id
```

Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — формализованное состояние
**жизненного цикла** (этап/шаг/действие). Три разные сущности, три файла.

### 2.7 Инжект стейта в промт (уровень 1 — build-prompt)

Порядок блоков не меняется (`BLOCK_ORDER` дня 11–12); состояние задачи входит в блок
`working` и подмешивается к **каждому** запросу задачи:

```text
[system: роль]                    ← + правило «работай в рамках текущего шага, не перепрыгивая этапы»
[system: профиль]                 ← активный профиль (день 12, без изменений)
[system: долговременная память]
[system: рабочая память задачи]   ← + «Этап: execution (шаг 2/3): Собрать информацию.
                                       Ожидаемое действие: …; пауза: предыдущий этап …»
[system: summary общего префикса]
[messages: краткосрочная память]
[user: текущий запрос]
[резерв: output + tool]
```

`WorkingMemory.as_prompt_block()` дополняется строками из `task_state.json` (этап, шаг N/M,
ожидаемое действие, ошибка) — LLM видит стадию и «отождествляет себя с ней», а код при
этом не даёт выйти за рамки разрешённых переходов (двойная защита: правило в промте +
запрет в коде).

### 2.8 Оркестратор `Agent` (жизненный цикл задачи)

```python
# core/agent.py — дополнение к контракту дня 12 (профили/роутер не меняются)
# В __init__: self.task_state: TaskState | None = None
def start_task(self, objective: str) -> TaskState
    # новая задача: task_id = safe_name(objective)/«Основная_задача», stage=PLANNING,
    # отметка в working/long_term (как switch_task дня 11), сейв task_state.json
def step_task(self) -> TaskState        # один проход run_task + сейв + лог перехода
def run_to_end(self, max_passes=50)     # /run: до done/failed/paused
def pause(self) -> bool                 # pause_task + сейв + лог; не на рабочем этапе → ворнинг
def resume(self) -> bool                # resume_task + сейв + лог «продолжение с шага N»
def load_task_state(self) -> None       # при load_state(user_id) и switch_task()
```

```
старт → идентификация user_id → активный профиль → load_state()
        └── + load_task_state(): есть task_state.json → задача «с того же места»
цикл:
  обычное сообщение → [auto_route] → remember(short_term) → build_context
        (в блоке working — этап/шаг/ожидаемое действие) → LLM → ответ
  /plan <цель>   → start_task → planning (LLM строит steps)
  /step          → один проход автомата (execution: шаг → result → current_step+1)
  /run           → крутить до done/failed
  /pause         → paused (previous_stage сохранён) — на любом рабочем этапе
  /resume        → возврат в previous_stage, продолжение с current_step — БЕЗ
                   повторного плана и БЕЗ повторных объяснений задачи
  /task <имя>    → переключение задачи + загрузка её task_state.json
exit → save_state() + сейв task_state.json (resume переживает перезапуск процесса)
```

«Продолжение без повторных объяснений»: после `/resume` (или перезапуска программы) агент
(1) загружает сохранённый `TaskState`, (2) восстанавливает этап, (3) продолжает с
`current_step`, (4) не строит план заново, (5) не просит пользователя ещё раз объяснить
задачу — всё уже лежит в состоянии.

### 2.9 CLI-команды (рабочие)

| Команда | Назначение |
|---|---|
| `/state` | ← РАСШИРЕНА: этап, шаг N/M, ожидаемое действие, previous_stage, error + карта разрешённых переходов |
| `/plan <цель>` | ← НОВОЕ: начать задачу (planning: LLM строит список шагов) |
| `/step` | ← НОВОЕ: один проход автомата (текущий шаг execution / переход в validation) |
| `/run` | ← НОВОЕ: выполнять до done/failed (лимит проходов) |
| `/pause` | ← НОВОЕ: пауза на любом этапе (planning/execution/validation) |
| `/resume` | ← НОВОЕ: продолжение с того же этапа и шага, без повторных объяснений |
| `/task retry` | ← НОВОЕ: восстановление из failed → planning (явный, единственный выход) |
| `/memory`, `/profile`-семейство, `/tasks`, `/task <имя>`, `/deliver`, `/compare`, `/summary`, `/tokens`, `/cost`, `/help`, `/exit` | наследуются из дней 11–12 без изменений |

Флаги запуска — 11, наследуются: `--user`, `--profile`, `--deliver`, `--mock`, `--fresh`
(+ не восстанавливать и `task_state.json`), `--log`, `--token-log`, `--memory-dir`,
`--max-tokens`, `--price-in/--price-out`.

### 2.10 LLM-клиент, память, профили (без изменений)

```python
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...
class RouterAIClient(LLMClient): ...   # retry 429: 2→4→8 с, таймаут 30 с
class MockClient(LLMClient): ...       # детерминированная заглушка для тестов автомата
```

Модель памяти (4 слоя), `MemoryManager`, `ProfileRepository` (SQLite + зеркала),
`ProfileRouter`, `PromptBuilder` — контракты дней 11–12 сохраняются полностью; регрессия
запрещена (прежние 22 критерия приёмки остаются зелёными).

---

## 3. Служебное пространство `dev/` (проект про проект)

### 3.1 Дерево `dev/`

```
Nedela_3/den_13/dev/
├── Проверка.md                   # сценарий РУЧНОЙ проверки: 22 пункта дней 11–12 + строки 23–25 (автомат)
├── PLAN_naming.md                # план коррекции naming (артефакт дня 12, исторический)
├── meta_promt/                   # метапромты для создания отдельных частей
│   ├── ПРОМТ_memory.md / ПРОМТ_storage.md / ПРОМТ_llm.md / ПРОМТ_prompt.md
│   ├── ПРОМТ_agent.md / ПРОМТ_state.md / ПРОМТ_cli.md / ПРОМТ_readme.md
│   └── ПРОМТ_fsm.md              # ← НОВОЕ: Этап F — task state machine (контракты §2.2–2.8)
├── tests_debug/                  # тестирование и отладка
│   ├── check_acceptance.sh       # гейт приёмки (9 проверок, TMP в .tmp/acc_$$)
│   ├── unit_runner.py            # L2-раннер юнит-тестов (без pytest)
│   ├── smoke.py                  # L3-смоук: in-process + CLI subprocess
│   ├── scenario.py               # L4-сценарии задания (+ scenario_pause_resume)
│   ├── unit/                     # test_{storage,memory,llm,prompt,agent,state,person}.py
│   │                             #   + ← НОВОЕ: test_fsm.py (автомат: переходы/пауза/resume/JSON)
│   ├── scenario/                 # scen_1.md — сценарий ручной демонстрации куратору
│   ├── smoke/ , fixtures/        # каркас
│   └── .tmp/                     # единственное место прогонов и временных файлов (.gitignore)
└── logs_reports/                 # логирование и отчёты по этапам создания
    ├── stages/                   # stage_00_env … stage_10_final, stage_E_person.md
    │                             #   + ← НОВОЕ: stage_F_state.md
    ├── errors/                   # карточки ошибок: контекст, стек, решение, статус
    ├── run_log.md                # сводный журнал прогонов (команда → результат → EXIT)
    └── final_report.md           # итоговый отчёт «было/стало/проверено/спорное»
```

### 3.2 `START-PROMT.md` — каркас-алгоритм автономного создания

Наследуется из дня 12: суть дня → входные данные (переменные `$KOD/$DEV/$MP/$LOGS/$TST/$PY/
$DONOR/$MODEL`, запрет хардкода путей) → автономный режим (human-gate только на живой ключ)
→ каркас Этап 0→11 → параллельный запуск субагентов → журналирование → цикл отладки L1–L4
со стоп-условиями → критерии приёмки + гейт → запреты → восстановление контекста.

Для `den_13` программа работ дополняется: Этап E (персонализация, день 12 — уже выполнена)
→ **Этап F (task state machine по `ПРОМТ_fsm.md`)**: `core/state_machine.py` →
`storage/store.py` (task_state.json) → `memory/working.py` (блок промта) →
`core/agent.py` (жизненный цикл) → `Kod.py` (команды) → тесты → README/Проверка (строки
23–25) → `stage_F_state.md`.

### 3.3 `tests_debug/` — что именно протестировать (канон задания)

`unit/test_fsm.py` (все на заглушках, без живого ключа):

- **базовый тест из задания** `test_pause_and_resume`: execution, шаг 2 → pause →
  `stage == PAUSED`, `previous_stage == EXECUTION`, `current_step == 2` → resume →
  `stage == EXECUTION`, `current_step == 2`, `expected_action` восстановлен;
- пауза во время `planning` / `execution` / `validation` — resume возвращает в тот же этап;
- повторный `resume`, когда задача уже не на паузе — no-op (состояние не меняется);
- повторный `pause` на уже paused — no-op;
- разрешённые/запрещённые переходы (`transition()`): planning→execution ✓,
  planning→done ✗, done→* ✗, failed→planning ✓; 4 базовых стадии присутствуют (миграция
  старого `test_state.py`);
- сохранение состояния на диск и загрузка после «перезапуска» (save → load → поля равны,
  включая enum-значения);
- завершение задачи без повторного выполнения уже завершённых шагов: run_task дважды с
  паузой посередине — `results` не дублируются, `current_step` монотонен;
- validation: успех → done; ошибка → failed + `error` заполнен.

`scenario.py` + **`scenario_pause_resume`** (L4, сквозной): `/plan «Найди три Python-
фреймворка и сравни их»` → planning построил шаги → `/step` (шаг 0 выполнен) → `/pause` →
снимок `task_state.json` совпадает с каноном задания (stage=paused, previous_stage=
execution, current_step=1) → «перезапуск процесса» (новый Agent поверх того же
`--memory-dir`) → `/resume` → продолжение с шага 1 **без повторного плана и без повторных
объяснений** → `/run` → done; лог содержит строки «[Автомат] … → …».

`smoke.py` (L3) — полный цикл in-process + CLI subprocess (логи изолированы в `.tmp/`);
`check_acceptance.sh` — гейт приёмки (9 проверок), временный каталог `$TST/.tmp/acc_$$`,
`users/` проекта не трогается.

### 3.4 `logs_reports/` — логирование и отчёты по этапам

- `stages/stage_F_state.md` — по форме «было → стало → проверка → статус»: задел
  (Enum + next_state) → полный автомат (TaskStage/TaskState/pause/resume/save/load),
  результаты `test_fsm.py` и `scenario_pause_resume`.
- `errors/error_<timestamp>.md` — контекст этапа, тип ошибки, стек, решение, статус
  (✅ исправлено / ⚠️ обход / ❌ открыто).
- `run_log.md` — сводный журнал прогонов: команда → результат → exit-код; карта
  «этап → субагент → target → статус».
- `final_report.md` — итоговый отчёт: дерево проекта, результаты приёмки, «что сделано /
  что проверено / что осталось спорным», предложение коммита.

---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)
| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | персонализированный stateful-агент с **формализованным состоянием задачи** |
| `core/state_machine.py` | конечный автомат: TaskStage (6 этапов) + TaskState + ALLOWED_TRANSITIONS + pause/resume + save/load |
| `users/<id>/tasks/<task>/task_state.json` | персистентный снимок состояния (этап/шаг/действие/results/previous_stage/error) |
| `run.sh` / `run.desktop` | запуск (`.sh` исполняемый, `Exec` — абсолютный путь) |
| `README.md` | описание проекта + модель памяти + персонализация + **раздел «Состояние задачи»** |

### 4.2 Служебные артефакты (процесс)
| Артефакт | Назначение |
|---|---|
| `START-PROMT.md` | сценарий автономного создания и тестирования (+ Этап F) |
| `dev/Проверка.md` | единственный сценарий ручной проверки (22 пункта + строки 23–25 автомата) |
| `dev/meta_promt/*.md` | метапромты создания частей (включая `ПРОМТ_fsm.md`) |
| `dev/tests_debug/*` | L2/L3/L4 + гейт + `.tmp/` (единственное место временных файлов) |
| `dev/logs_reports/*` | отчёты по этапам (вкл. `stage_F_state.md`), ошибки, сводный лог, финальный отчёт |

> `Проверка.md`  живёт **только в `dev/`** — артефакты процесса
> создания/приёмки, а не продукт; в корне проекта их нет.

### 4.3 Критерии приёмки состояния задачи
| Пункт | Что проверяем | Как |
|---|---|---|
| 23 | Формализованное состояние: в любой момент явно записаны этап, текущий шаг, ожидаемое действие | `test_fsm.py` (dataclass-поля), `/state` (снимок в REPL), блок working в промте |
| 24 | Пауза на любом этапе + продолжение без повторных объяснений | `test_fsm.py` (pause/resume на planning/execution/validation, no-op случаи) + `scenario_pause_resume` (resume с того же шага, план не перестраивается) |
| 25 | Персистентность и жизненный цикл | save/load JSON; «перезапуск процесса» → продолжение с `current_step`; завершённые шаги не повторяются; validation → done/failed; переходы строго по `ALLOWED_TRANSITIONS` |

Регрессия: прежние 22 критерия (память + персонализация) остаются зелёными.

Гейт: `unit_runner.py` (все тесты, включая `test_fsm.py`) → `scenario.py` (7 сценариев) →
`check_acceptance.sh` 9 из 9 — всё без живого ключа (`API_KEY=test-key` / `MockClient`).

---

## 5. Порядок достижения итогового состояния

1. **Этап F — Task State Machine** — по `dev/meta_promt/ПРОМТ_fsm.md`, порядок по
   зависимостям: `core/state_machine.py` (TaskStage + TaskState + ALLOWED_TRANSITIONS +
   transition/pause/resume + save/load) → `storage/store.py` (task_state_path/read/write) →
   `memory/working.py` (этап/шаг/действие в блоке промта) → `core/agent.py`
   (start_task/step_task/run_to_end/pause/resume/load_task_state) → `Kod.py`
   (/plan /step /run /pause /resume /task retry, расширение /state) → `test_fsm.py` +
   миграция `test_state.py` + `scenario_pause_resume` → README (раздел «Состояние задачи»)
   + Проверка (строки 23–25) → `stage_F_state.md`.
2. **Финал** — прогон всех проверок (L2→L3→L4→гейт), `final_report.md`, предложение коммита (коммит — только по явной команде пользователя).

---

## 6. Итог

После завершения `den_13` получается:

- **Агент с формализованным состоянием задачи**: поверх модели памяти (4 слоя) и
  персонализации (мультипрофиль + роутер + пайплайн скиллов) — конечный автомат задачи
  (planning → execution → validation → done, расширен paused/failed): в каждый момент явно
  записаны этап, текущий шаг и ожидаемое действие; переходы — только по
  `ALLOWED_TRANSITIONS` (проверка кодом); пауза на любом этапе сохраняет `previous_stage`
  и позицию шага; продолжение (команда или перезапуск процесса) возвращает ровно в ту же
  точку — без повторного плана и без повторных объяснений; состояние переживает перезапуск
  (`task_state.json`); LLM составляет план и наполняет шаги, а Python-код управляет
  жизненным циклом — поведение агента предсказуемо и тестируемо без живого ключа.
- **Служебное пространство `dev/`**: воспроизводимое автономное создание — каркас
  (`START-PROMT.md` + Этап F), метапромты частей (включая `ПРОМТ_fsm.md`), тестовый контур
  L2–L4 + гейт (`test_fsm.py`, `scenario_pause_resume`, временные файлы только в `.tmp/`),
  полный аудит этапов (`stage_F_state.md`, ошибки, сводный лог, финальный отчёт).

Такой фундамент позволяет следующим дням недели 3 нарастить фильтр инвариантов
(PolicyEngine — задел в `memory/base.py`), исполнение пайплайна скиллов (реальную
оркестрацию) и объединение «кубиков» (память → персонализация → автомат) в единую систему
без переписывания базы.
