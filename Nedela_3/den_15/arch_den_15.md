# arch_den_15.md — целевая архитектура проекта `den_15` «Контролируемые переходы состояний»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_15`. Базируется на `arch_den_14.md` (инварианты поверх персонализации, модели
> памяти и формализованного состояния задачи) и добавляет **строгую машину состояний
> жизненного цикла задачи**: конечный набор допустимых состояний, явная матрица разрешённых
> переходов и **программная блокировка любого «перепрыгивания» этапа** — переход проверяется
> кодом до применения, а не текстом промта.
> Источники: `Суть_N3.md`, `Задание_Д15.txt` (неизменяемый первоисточник), `arch_den_14.md`.

---

## 0. Назначение документа

Документ фиксирует два слоя итогового состояния:

1. **Рабочая архитектура** — персонализированный stateful-агент с явной моделью памяти
   (4 слоя), мультипрофильностью, формализованным состоянием задачи и слоем инвариантов,
   унаследованный от `den_14` без изменения контрактов, **плюс строгая машина состояний (FSM)**
   жизненного цикла задачи: `TaskState` (конечный enum допустимых состояний) +
   `ALLOWED_TRANSITIONS` (явная матрица переходов) + `try_transition`/`InvalidTransitionError`
   (программная блокировка недопустимого перехода) + `TransitionLog` (аудит всех попыток).
2. **Служебное пространство `dev/`** — «проект про проект»: всё, чем агент автономно
   создаёт, тестирует и отлаживает проект, с полным аудитом каждого этапа.

Главная идея задания (канон `Задание_Д15.txt`): **жизненный цикл задачи — это строгая машина
состояний**. У задачи есть конечный набор допустимых состояний и список **разрешённых**
переходов; ассистент **физически не может** «перепрыгнуть» этап. Даже если пользователь
просит «давайте сразу сделаем реализацию, без плана», а LLM в рассуждении предлагает
«перейдём в `implementation` прямо сейчас» — переход отклоняется **на уровне кода**
(`try_transition` → `InvalidTransitionError`), состояние **не меняется**, а ассистент
объясняет правило процесса и предлагает корректную последовательность.

---

## 1. Ключевая идея и принципы

### 1.1 Ключевая идея
`den_15` превращает процесс выполнения задачи в **формальный workflow с контролируемыми
этапами**, где LLM работает внутри жёстко заданного жизненного цикла, а не хаотично скачет
по этапам. Появляется (усиливается) сущность — **`StateMachine`** (строгая FSM задачи):

1. **Конечный набор допустимых состояний** — `TaskState` (enum): `new`, `planning`,
   `plan_approved`, `implementation`, `validation`, `done`, `paused`. Любое другое состояние
   недопустимо.
2. **Явная матрица разрешённых переходов** — `ALLOWED_TRANSITIONS` (единственный источник
   истины). Пример: `planning → plan_approved`, но **не** `planning → implementation`
   (реализацию нельзя начать до утверждённого плана).
3. **Проверка кодом до применения** — `can_transition(from, to)` + `try_transition(...)`,
   которая при недопустимом переходе бросает `InvalidTransitionError`; состояние задачи при
   этом **не меняется**, а попытка попадает в `TransitionLog`.

Формула ценности дня: **недопустимый переход не выполняется молча** — агент остаётся в
текущем состоянии, называет сработавшее правило и предлагает корректный следующий шаг.

### 1.2 Принципы
- **Жизненный цикл — это код, а не текст** (канон `Суть_N3.md`): промт рекомендует, код
  запрещает. Правило «не перепрыгивай этап» дублируется: и в промте (блок состояния задачи),
  и в `try_transition` (жёсткий запрет). Двойная защита.
- **Единый источник истины для переходов**: матрица `ALLOWED_TRANSITIONS` — одно место, где
  описано, что куда можно; и проверка, и промт, и CLI читают её.
- **Проверка до изменения состояния**: `try_transition` вызывается перед любым изменением
  стадии задачи (перед запуском реализации, перед фиксацией `done`, перед отправкой результата
  пользователю). Недопустимый переход → исключение → состояние неизменно.
- **Ассистент не перепрыгивает этап**: при попытке (от пользователя или от LLM) агент
  (1) остаётся в текущем состоянии, (2) объясняет, какое правило сработало, (3) предлагает
  корректную последовательность. «Нельзя» без объяснения — плохая реакция.
- **Пауза и возобновление не ломают FSM**: `paused` доступна из любого активного состояния;
  `resume()` возвращает **ровно в то состояние, из которого ушли в паузу** (`prev_state`),
  а разрешённые переходы после возобновления остаются теми же.
- **Персистентность**: снимок FSM (`state`, `prev_state`, `TransitionLog`) хранится в
  `task_state.json` и переживает перезапуск процесса → «продолжение после паузы» корректно.
- **Аудит**: каждая попытка перехода (и разрешённая, и отклонённая) пишется в `TransitionLog`
  с отметкой `allowed` и причиной отказа — поведение воспроизводимо и объяснимо.
- **4 базовые стадии не убираем** (канон `Суть_N3.md`): `planning → execution → validation →
  done` представлены подграфом FSM (`planning/plan_approved → implementation → validation →
  done`); стадии можно расширять, но не сужать.
- **Наследие дней 11–14 без регрессии**: модель памяти (4 слоя), персонализация
  (мультипрофиль + роутер), инварианты (`ConstraintSet` + `InvariantChecker` + отказ с
  объяснением) сохраняются полностью; FSM — **аддитивное** усиление слоя состояния задачи.
- **Полиморфизм через интерфейсы, инкапсуляция через фасады** — наследуются из дней 11–14
  (`MemoryLayer`, `LLMClient`, `Store`, `InvariantChecker`); `StateMachine` инжектится в
  агента, хранилище пути знает `Store`, агент — нет.

---

## 2. Рабочая структура проекта

### 2.1 Дерево модулей


Nedela_3/den_15/
├── Kod.py                       # точка входа: DI-композиция + REPL (+ команды переходов)
├── core/
│   ├── __init__.py
│   ├── agent.py                 # оркестратор: + request_transition / реакция на запрет
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient (без изменений)
│   ├── profile_router.py        # ProfileRouter (без изменений от дня 12)
│   ├── prompt_builder.py        # BLOCK_ORDER + deliver + budget (+ блок task_state)
│   ├── state_machine.py         # ← УСИЛЕНО: TaskState + ALLOWED_TRANSITIONS + can_transition
│   │                            #   + try_transition + InvalidTransitionError + TransitionLog
│   │                            #   + StateMachine (pause/resume, snapshot/from_snapshot)
│   └── invariants.py            # Invariant + ConstraintSet + InvariantChecker (без изменений)
├── memory/
│   ├── __init__.py
│   ├── base.py                  # MemoryLayer (ABC) + MemoryContext + PolicyEngine (без изменений)
│   ├── short_term.py            # ShortTermMemory — неизменяемые сообщения (parent_id)
│   ├── working.py               # WorkingMemory — состояние задачи (+ зеркало стадии)
│   ├── long_term.py             # LongTermMemory — статусы задач (done/failed) в decisions
│   ├── profile.py               # Profile — style + constraints + context + skills
│   └── manager.py               # MemoryManager — явная маршрутизация «что куда»
├── storage/
│   ├── __init__.py
│   ├── store.py                 # фасад: + read/write task_state.json (снимок FSM)
│   └── db.py                    # ProfileRepository (без изменений от дня 12)
├── users/                       # рантайм-хранилище (создаётся при работе)
├── run.sh                       # +x: cd dirname + source ../../.venv/bin/activate + python
├── run.desktop                  # Exec = абсолютный путь к .sh
├── README.md                    # + раздел «Контролируемые переходы состояний»
├── arch_den_15.md                # текущая архитектура проекта den_15 (этот файл)
├── Den_log.md                   # журнал: + строки переходов ([FSM] …)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
├── Задание_Д15.txt              # постановка куратора (неизменяемый первоисточник)
└── dev/                         # ← служебное пространство (раздел 3), в т.ч. Проверка.md


### 2.2 Модель состояний (`core/state_machine.py`)

Канон `Задание_Д15.txt` — конечный enum допустимых состояний. Имена — как в задании.

python
# core/state_machine.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum


class TaskState(str, Enum):
    NEW = "new"                     # задача создана, но ещё не начата
    PLANNING = "planning"           # идёт планирование
    PLAN_APPROVED = "plan_approved" # план утверждён
    IMPLEMENTATION = "implementation"  # идёт реализация
    VALIDATION = "validation"       # проверка / тестирование
    DONE = "done"                   # задача завершена
    PAUSED = "paused"               # пауза (сохраняет prev_state)


`TaskState` — **единственный** набор допустимых состояний задачи. Любое состояние вне enum
считается недопустимым и отклоняется ещё на входе (парсинг CLI/промта).

Соответствие 4 базовым стадиям лекции (`Суть_N3.md`, «не убирать»):

| Базовая стадия | Состояния FSM |
|---|---|
| planning | `new → planning → plan_approved` |
| execution | `implementation` |
| validation | `validation` |
| done | `done` |

### 2.3 Матрица разрешённых переходов (`ALLOWED_TRANSITIONS`)

Явный список переходов — **единственный источник истины**. Канон `Задание_Д15.txt`:

python
ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.NEW:            {TaskState.PLANNING, TaskState.PAUSED},
    TaskState.PLANNING:       {TaskState.PLAN_APPROVED, TaskState.PAUSED},
    TaskState.PLAN_APPROVED:  {TaskState.IMPLEMENTATION, TaskState.PAUSED},
    TaskState.IMPLEMENTATION: {TaskState.VALIDATION, TaskState.PAUSED},
    TaskState.VALIDATION:     {TaskState.DONE, TaskState.PAUSED},
    TaskState.DONE:           set(),        # из done никуда не переходим (терминальное)
    TaskState.PAUSED:         {TaskState.NEW, TaskState.PLANNING, TaskState.PLAN_APPROVED,
                               TaskState.IMPLEMENTATION, TaskState.VALIDATION},
}


Функция проверки:

python
def can_transition(from_state: TaskState, to_state: TaskState) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


Явно **запрещённые** переходы (примеры из задания, проверяются тестами):

| Запрещённый переход | Почему |
|---|---|
| `new → implementation` | нельзя делать реализацию до утверждённого плана |
| `planning → implementation` | нужен промежуточный `plan_approved` |
| `planning → done` | нельзя завершить без реализации и валидации |
| `implementation → done` | нельзя финал без валидации |
| `done → *` | `done` — терминальное состояние |
| `* → done` кроме `validation → done` | финал только после валидации |

> **Опциональное расширение** (по умолчанию выключено, чтобы строго соответствовать примеру
> задания): `VALIDATION → IMPLEMENTATION` (возврат на доработку при провале валидации).
> Лекция допускает возвраты (`validation → execution`), но канонический пример `Д15` их не
> включает; включается флагом `--rework`.

### 2.4 Контролируемый переход (`try_transition` + `InvalidTransitionError`)

python
class InvalidTransitionError(Exception):
    def __init__(self, current: TaskState, proposed: TaskState):
        self.current = current
        self.proposed = proposed
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))
        super().__init__(
            f"Переход {current.value} → {proposed.value} запрещён. "
            f"Разрешено из {current.value}: {allowed or 'нет (терминальное состояние)'}."
        )


def try_transition(current: TaskState, proposed: TaskState) -> TaskState:
    if not can_transition(current, proposed):
        # не меняем состояние — только сигнал об ошибке
        raise InvalidTransitionError(current, proposed)
    return proposed


Любой переход проходит через `try_transition`. Если `can_transition` вернула `False`,
переход **не выполняется**: состояние остаётся прежним, а вызывающий код получает
`InvalidTransitionError` с указанием текущего состояния и списка разрешённых.

### 2.5 Аудит переходов (`TransitionLog`)

Каждая попытка (и разрешённая, и отклонённая) фиксируется — требование задания
«в логе/истории остаётся запись о попытке и отказе».

python
@dataclass
class TransitionRecord:
    ts: str          # ISO-таймстамп
    frm: str         # состояние до
    to: str          # предлагаемое состояние
    allowed: bool    # разрешён ли переход
    reason: str = "" # причина отказа (текст InvalidTransitionError) / метка ("resume")


`StateMachine` хранит `list[TransitionRecord]`, а также `state` (текущее) и `prev_state`
(состояние до паузы).

### 2.6 Строгая FSM (`StateMachine`)

python
class StateMachine:
    """Строгая машина состояний жизненного цикла задачи.
    Единственное место, где меняется состояние; любой переход проходит can_transition."""

    def __init__(self, state: TaskState = TaskState.NEW,
                 prev_state: TaskState | None = None):
        self._state = state
        self._prev_state = prev_state          # состояние до паузы
        self._log: list[TransitionRecord] = []

    @property
    def state(self) -> TaskState: ...
    def allowed_next(self) -> set[TaskState]:
        return set(ALLOWED_TRANSITIONS.get(self._state, set()))

    def transition(self, proposed: TaskState) -> TaskState:
        now = datetime.now().isoformat(timespec="seconds")
        try:
            new_state = try_transition(self._state, proposed)
        except InvalidTransitionError as e:
            self._log.append(TransitionRecord(now, self._state.value, proposed.value, False, str(e)))
            raise
        if proposed is TaskState.PAUSED:
            self._prev_state = self._state       # запоминаем, куда вернёмся
        self._log.append(TransitionRecord(now, self._state.value, proposed.value, True))
        self._state = new_state
        return self._state

    def pause(self) -> TaskState: ...
    def resume(self) -> TaskState:
        # возврат ровно в prev_state (то состояние, из которого ушли в паузу)
        ...

    def snapshot(self) -> dict: ...              # {state, prev_state, log}
    @classmethod
    def from_snapshot(cls, data: dict) -> "StateMachine": ...


- `pause()` = `transition(PAUSED)`; доступна из любого активного состояния (`new`…`validation`),
  но не из `done` (терминальное).
- `resume()` возвращает **ровно `prev_state`** (не «любое из списка»); `prev_state` очищается.
  Попытка `resume()` не из `paused` → `InvalidTransitionError`.
- `snapshot()`/`from_snapshot()` — сериализация для `task_state.json`.

### 2.7 Персистентность (`task_state.json`)

Снимок FSM хранится отдельно от истории диалога и от инвариантов; переживает перезапуск.

python
# storage/store.py — фасад знает путь (агент — нет)
def task_state_path(self, user_id, task_name) -> str          # users/<id>/tasks/<task>/task_state.json
def read_task_state(self, user_id, task_name) -> dict | None  # None — снимка ещё нет
def write_task_state(self, user_id, task_name, data: dict) -> str


Снимок на диске:


{
  "state": "implementation",
  "prev_state": null,
  "log": [
    {"ts": "2026-09-21T10:00:01", "frm": "new", "to": "planning", "allowed": true, "reason": ""},
    {"ts": "2026-09-21T10:03:12", "frm": "planning", "to": "plan_approved", "allowed": true, "reason": ""},
    {"ts": "2026-09-21T10:05:40", "frm": "plan_approved", "to": "implementation", "allowed": true, "reason": ""},
    {"ts": "2026-09-21T10:07:02", "frm": "implementation", "to": "done", "allowed": false,
     "reason": "Переход implementation → done запрещён. Разрешено из implementation: paused, validation."}
  ]
}


Правила:
- сейв — при каждом успешном переходе и при `/exit`;
- лоад — при старте, при `load_state(user_id)` и при `/task <имя>` (переключение задачи
  подтягивает её собственную FSM);
- битый/отсутствующий `task_state.json` не роняет приложение — задача стартует в `new`;
- **очистка истории диалога не сбрасывает FSM** (разные файлы).

### 2.8 Иерархия хранения (канон + task_state.json)


users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite)
├── profiles/                    # зеркала всех профилей (день 12, без изменений)
├── long_term_memory.json        # {profile_ref, tasks[], decisions[], knowledge[]}
└── tasks/<task_name>/
    ├── invariants.json          # ConstraintSet (неизменяемые правила задачи, день 14)
    ├── task_state.json          # ← снимок FSM: state + prev_state + TransitionLog
    ├── working_memory.json      # состояние задачи (+ зеркало стадии)
    ├── sessions_resume.md       # резюме сессий (только данные о задаче)
    └── sessions/<session_id>/
        └── session.json         # краткосрочная память: сообщения с parent_id


Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — **формализованный жизненный
цикл**; `invariants.json` — **неизменяемые правила**. Четыре разные сущности, четыре файла.

### 2.9 Инжект состояния в промт (уровень 1 — build-prompt)

Порядок блоков расширяется одним блоком `task_state` (после `invariants`, до `working`):

text
[system: роль]                    ← + правило «работай в рамках текущего состояния задачи»
[system: профиль]                 ← активный профиль (день 12, без изменений)
[system: инварианты]              ← активные правила (день 14, без изменений)
[system: состояние задачи]        ← ← НОВОЕ: текущее состояние + разрешённые переходы + запреты
[system: долговременная память]
[system: рабочая память задачи]   ← этап/шаг/ожидаемое действие
[system: summary общего префикса]
[messages: краткосрочная память]
[user: текущий запрос]
[резерв: output + tool]


Блок состояния формируется из `StateMachine` и матрицы:

text
Текущее состояние задачи: implementation.
Разрешённые переходы: validation, paused.
Запрещено перепрыгивать этапы:
- нельзя перейти в implementation без plan_approved;
- нельзя перейти в done без validation.
Работай строго в рамках текущего состояния; предлагай только разрешённый следующий шаг.


`BLOCK_ORDER` дней 11–14 дополняется именем `task_state`; блок добавляется **только если имя
есть в `deliver`** (дозированная доставка сохраняется). Это помогает модели видеть ограничения,
но **окончательное решение принимает `try_transition`** (двойная защита: правило в промте +
запрет в коде).

### 2.10 Рабочий цикл с контролем переходов

text
Запрос пользователя / ответ LLM
        ↓
Предложение перехода (ProposedState)
        ↓
can_transition / try_transition (Python-код)
        ↓
применить переход  ИЛИ  InvalidTransitionError → остаться + объяснить


python
# core/agent.py — фрагмент цикла
def request_transition(self, proposed: TaskState) -> str:
    try:
        self.fsm.transition(proposed)          # проверка + применение + запись в лог
    except InvalidTransitionError as e:
        self._log(f"[FSM] переход отклонён: {e}")
        self._save_task_state()                # состояние НЕ менялось; лог сохранён
        return self._transition_refusal(e)     # реакция ассистента
    self._save_task_state()
    return f"Состояние задачи: {self.fsm.state.value}."


Проверка выполняется **перед** любым изменением стадии задачи (перед запуском реализации,
перед фиксацией `done`, перед отправкой результата пользователю). Недопустимый переход
инструмент не запускает и состояние не меняет.

### 2.11 Реакция ассистента на запрещённый переход (канон задания)

Правильная реакция (попытка `new → implementation`):

text
Переход в «implementation» невозможен: сейчас задача в состоянии «new».

Причина: по правилам жизненного цикла этап нельзя перепрыгнуть —
реализацию нельзя начать до утверждённого плана (нужен переход new → planning → plan_approved).

Разрешённые следующие состояния: planning, paused.
Предлагаю сначала перейти в «planning».


Отказ обязан: (1) назвать текущее состояние, (2) назвать сработавшее правило, (3) перечислить
разрешённые переходы, (4) предложить корректный следующий шаг. Плохие реакции: молчаливое
выполнение («Хорошо, сразу реализуем») и сухой запрет («Нельзя»).

python
def _transition_refusal(self, e: InvalidTransitionError) -> str:
    allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(e.current, set()))
    nxt = allowed[0] if allowed else "—"
    return (
        f"Переход в «{e.proposed.value}» невозможен: сейчас задача в состоянии «{e.current.value}».\n"
        f"Причина: по правилам жизненного цикла этап нельзя перепрыгнуть.\n"
        f"Разрешённые следующие состояния: {', '.join(allowed) or '—'}.\n"
        f"Предлагаю сначала перейти в «{nxt}»."
    )


### 2.12 Пауза и возобновление (корректность продолжения)

Сценарий задания «корректность продолжения после паузы»:

1. задача в состоянии `implementation`;
2. переход в `paused` (сохраняется `prev_state = implementation`);
3. сессия завершается / процесс перезапускается (`task_state.json` уже на диске);
4. при продолжении: загружается последнее состояние; `resume()` возвращает **ровно
   `implementation`**; `allowed_next()` остаётся тем же (`validation`, `paused`); ассистент
   не «сбрасывается» в начало и не перескакивает этапы.

python
# загрузка при старте
data = store.read_task_state(user_id, task_name)
self.fsm = StateMachine.from_snapshot(data) if data else StateMachine()
# продолжение
if self.fsm.state is TaskState.PAUSED:
    self.fsm.resume()      # → prev_state (implementation), prev_state очищен


### 2.13 Оркестратор `Agent` (FSM в жизненном цикле)

python
# core/agent.py — дополнение к контракту дня 14 (память/профили/инварианты не меняются)
# В __init__: self.fsm: StateMachine
def load_fsm(self) -> None                        # при load_state(user_id) и switch_task()
def save_fsm(self) -> None                        # snapshot → task_state.json
def request_transition(self, proposed) -> str     # проверка → применить/отказать
def pause(self) -> str                            # fsm.pause()
def resume(self) -> str                           # fsm.resume()
def allowed_next(self) -> set[TaskState]          # fsm.allowed_next()
def transition_log(self) -> list[TransitionRecord]



старт → идентификация user_id → активный профиль → load_state()
        └── + load_fsm(): есть task_state.json → состояние/лог загружены
цикл:
  обычное сообщение → [auto_route] → remember(short_term) → build_context
        (в блоке task_state — состояние + разрешённые переходы + запреты) → LLM
        → предложение перехода → request_transition → применён ИЛИ отказ с объяснением
  /state            → текущее состояние + разрешённые следующие
  /next             → список разрешённых переходов
  /transition <s>   → попытка перехода (проверяется кодом)
  /pause            → пауза (запоминает prev_state)
  /resume           → возврат ровно в prev_state
  /history          → журнал переходов (allowed/rejected)
  /fsm              → матрица разрешённых переходов
exit → save_state() + save_fsm()


### 2.14 CLI-команды (рабочие)

| Команда | Назначение |
|---|---|
| `/state` | ← УСИЛЕНО: текущее состояние + разрешённые следующие |
| `/next` | ← НОВОЕ: список разрешённых переходов из текущего состояния |
| `/transition <state>` | ← НОВОЕ: попытка перехода (проверяется `try_transition`) |
| `/pause` | ← НОВОЕ/усилено: пауза (сохраняет `prev_state`) |
| `/resume` | ← НОВОЕ/усилено: возврат ровно в `prev_state` |
| `/history` | ← НОВОЕ: журнал переходов (`allowed`/`rejected` + причина) |
| `/fsm` | ← НОВОЕ: матрица разрешённых переходов |
| `/invariants`, `/invariant add\|set\|on\|off`, `/check` | наследуются из дня 14 без изменений |
| `/plan`, `/step`, `/run`, `/task retry` | наследуются из дня 13 (теперь под контролем FSM) |
| `/memory`, `/profile`-семейство, `/tasks`, `/task <имя>`, `/deliver`, `/compare`, `/summary`, `/tokens`, `/cost`, `/help`, `/exit` | наследуются из дней 11–14 без изменений |

Флаги запуска — 11, наследуются: `--user`, `--profile`, `--deliver`, `--mock`, `--fresh`
(+ не восстанавливать `task_state.json`), `--log`, `--token-log`, `--memory-dir`,
`--max-tokens`, `--price-in/--price-out` (+ `--rework` для опционального `VALIDATION →
IMPLEMENTATION`).

### 2.15 LLM-клиент, память, профили, инварианты (без изменений)

python
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...
class RouterAIClient(LLMClient): ...   # retry 429: 2→4→8 с, таймаут 30 с
class MockClient(LLMClient): ...       # детерминированная заглушка для тестов


Модель памяти (4 слоя), `MemoryManager`, `ProfileRepository` (SQLite + зеркала),
`ProfileRouter`, `PromptBuilder`, `Invariant`/`ConstraintSet`/`InvariantChecker` (день 14) —
контракты дней 11–14 сохраняются полностью; регрессия запрещена (прежние 30 критериев
приёмки остаются зелёными). `state_machine.py` меняется **аддитивно**: добавляются строгая
матрица переходов, `try_transition`/`InvalidTransitionError`, `TransitionLog` и
`snapshot`/`from_snapshot`; сигнатуры `pause`/`resume` сохраняются.

---

## 3. Служебное пространство `dev/` (проект про проект)

### 3.1 Дерево `dev/`


Nedela_3/den_15/dev/
├── migr_plan.md                  # план-эталон миграции den_15 на arch_den_15.md (текущий файл)
├── migr_plan_0.md                # ← НОВОЕ: первый этап миграции (конец — автоматический гейт)
├── migr_plan_1.md                # ← НОВОЕ: второй этап миграции (конец — автоматический гейт)
├── migr_plan_N.md                # ← НОВОЕ: следующий этап миграции (конец — автоматический гейт)
├── migr_log.md                   # журнал миграции den_15 на новую архитектуру arch_den_15.md
├── meta_promt/                   # метапромты (вспомогательные промты пользователя)
├── tests_debug/                  # тестирование и отладка
│   ├── check_acceptance.sh       # гейт приёмки (проверки, TMP в .tmp/acc_$)
│   ├── unit_runner.py            # L2-раннер юнит-тестов (без pytest)
│   ├── smoke.py                  # L3-смоук: in-process + CLI subprocess
│   ├── scenario.py               # L4-сценарии задания (+ scenario_invalid_transition,
│   │                             #   + scenario_pause_resume)
│   ├── unit/                     # test_{storage,memory,llm,prompt,agent,state,person,fsm,invariants}.py
│   │                             #   + ← УСИЛЕНО: test_fsm.py (переходы/запреты/pause/resume)
│   ├── scenario/                 # scen_1.md — сценарий ручной демонстрации куратору
│   ├── smoke/ , fixtures/        # каркас
│   └── .tmp/                     # единственное место прогонов и временных файлов (.gitignore)
└── logs_reports/                 # логирование и отчёты по этапам создания
    ├── stages/                   # stage_00_env … stage_10_final, stage_F_state, stage_H_fsm
    ├── errors/                   # карточки ошибок: контекст, стек, решение, статус
    └── run_log.md                # сводный журнал прогонов (команда → результат → EXIT)


> Миграция на `arch_den_15.md` описана в `dev/migr_plan.md`; на его основе создаются подробные,
> исполняемые планы-алгоритмы каждого этапа миграции (`migr_plan_0.md`, `migr_plan_1.md`, …,
> `migr_plan_N.md`) — конец одного этапа является автоматическим гейтом в следующий этап.
> Журнал миграции ведётся в `dev/migr_log.md` (его функции и роль журнала заменяют прежние
> `stages/stage_H_fsm.md` и `final_report.md`).

### 3.2 `tests_debug/` — что именно протестировать (канон задания)

`unit/test_fsm.py` (все на заглушках, без живого ключа):

- **базовые тесты из задания**:
  - `test_allowed_chain`: `new → planning → plan_approved → implementation → validation → done`
    — каждый переход проходит, состояние меняется;
  - `test_forbidden_new_to_implementation`: `new → implementation` → `InvalidTransitionError`,
    состояние **не меняется**;
  - `test_forbidden_planning_to_done`: `planning → done` → ошибка;
  - `test_forbidden_implementation_to_done`: `implementation → done` → ошибка;
  - `test_forbidden_planning_to_implementation`: `planning → implementation` (без
    `plan_approved`) → ошибка;
- **терминальность**: `test_done_is_terminal` — из `done` любой переход → ошибка;
- **пауза/возобновление**:
  - `test_pause_from_any_active_state` — `pause` проходит из `new`…`validation`;
  - `test_pause_forbidden_from_done` — из `done` → ошибка;
  - `test_resume_returns_to_prev_state` — `implementation → paused → resume → implementation`;
  - `test_resume_wrong_state` — `resume` не из `paused` → ошибка;
  - `test_no_jump_after_resume` — после `resume` `allowed_next()` те же, что до паузы;
- **неизменность состояния при отказе**: `test_state_not_changed_on_invalid` — после неудачной
  попытки `state` равен исходному;
- **аудит**: `test_transition_log_records_rejections` — в логе есть запись `allowed=False`
  с причиной;
- **реакция ассистента**: `test_assistant_reaction_names_rule` — текст отказа содержит текущее
  состояние и список разрешённых переходов;
- **персистентность**: `test_persistence_roundtrip` — `snapshot → from_snapshot` даёт равные
  `state`/`prev_state`/`log`; `test_resume_after_restart` — save → «новый процесс» → load →
  `resume` возвращает `prev_state`.

`scenario.py` + **`scenario_invalid_transition`** (L4, сквозной): задача в `new` → пользователь
«давай сразу реализацию» → агент **отклоняет** `new → implementation`, остаётся в `new`,
объясняет правило и предлагает `planning`; `/history` показывает запись `allowed=false`.
**`scenario_pause_resume`** (L4): довести до `implementation` → `/pause` → перезапуск →
`/resume` → состояние `implementation`, `/next` = `{validation, paused}`; лог содержит
`[FSM] …`.

`smoke.py` (L3) — полный цикл in-process + CLI subprocess (логи изолированы в `.tmp/`);
`check_acceptance.sh` — гейт приёмки (проверки, включая 31–36), временный каталог
`$TST/.tmp/acc_$$`, `users/` проекта не трогается.

### 3.3 `logs_reports/` — логирование и отчёты по этапам

- `migr_log.md` — журнал миграции: по форме «было → стало → проверка → статус» по каждому
  этапу (задел `state_machine.py` → строгая FSM `TaskState`/`ALLOWED_TRANSITIONS`/
  `try_transition`/`InvalidTransitionError`/`TransitionLog`/реакция на запрет), результаты
  `test_fsm.py`, `scenario_invalid_transition`, `scenario_pause_resume`; выполняет функции и
  роль журнала (заменяет прежние `stages/stage_H_fsm.md` и `final_report.md`).
- `errors/error_<timestamp>.md` — контекст этапа, тип ошибки, стек, решение, статус
  (✅ исправлено / ⚠️ обход / ❌ открыто).
- `run_log.md` — сводный журнал прогонов: команда → результат → exit-код; карта
  «этап → субагент → target → статус».

---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)
| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | персонализированный stateful-агент с инвариантами и **контролируемым жизненным циклом** |
| `core/state_machine.py` | `TaskState` + `ALLOWED_TRANSITIONS` + `can_transition` + `try_transition` + `InvalidTransitionError` + `TransitionLog` + `StateMachine` |
| `users/<id>/tasks/<task>/task_state.json` | персистентный снимок FSM (состояние + `prev_state` + журнал переходов) |
| `run.sh` / `run.desktop` | запуск (`.sh` исполняемый, `Exec` — абсолютный путь) |
| `README.md` | описание проекта + память + персонализация + инварианты + **раздел «Контролируемые переходы состояний»** |

### 4.2 Служебные артефакты (процесс)
| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | единственный сценарий ручной проверки (30 пунктов + строки 31–36 переходов) |
| `dev/tests_debug/*` | L2/L3/L4 + гейт + `.tmp/` (единственное место временных файлов) |
| `dev/logs_reports/*` | журнал миграции `migr_log.md`, ошибки, сводный лог |

> `Проверка.md` живёт **только в `dev/`** — артефакты процесса создания/приёмки, а не продукт;
> в корне проекта их нет.

### 4.3 Критерии приёмки переходов
| Пункт | Что проверяем | Как |
|---|---|---|
| 31 | У задачи — явный конечный набор состояний | `TaskState` (enum, 7 состояний); любое иное отклоняется (`test_fsm.py`) |
| 32 | Разрешённые переходы заданы явной матрицей | `ALLOWED_TRANSITIONS` — единый источник истины; `/fsm` печатает матрицу |
| 33 | Переход проверяется кодом до применения; недопустимый не меняет состояние | `try_transition` → `InvalidTransitionError`; `test_state_not_changed_on_invalid`; запись `allowed=false` в `TransitionLog` |
| 34 | Ассистент не перепрыгивает этап + корректная реакция | `scenario_invalid_transition`: `new → implementation`, `planning → done`, `implementation → done` отклонены; отказ называет состояние, правило и следующий шаг |
| 35 | Пауза/возобновление не ломают FSM | `resume()` → ровно `prev_state`; `allowed_next()` те же; `scenario_pause_resume` |
| 36 | Персистентность: состояние переживает перезапуск | `task_state.json`; `test_resume_after_restart`; после `resume` нет сброса в начало |

Регрессия: прежние 30 критериев (память + персонализация + инварианты) остаются зелёными.

Гейт: `unit_runner.py` (все тесты, включая `test_fsm.py`) → `scenario.py` (сценарии, включая
`scenario_invalid_transition`, `scenario_pause_resume`) → `check_acceptance.sh` — всё без
живого ключа (`API_KEY=test-key` / `MockClient`).

---

## 5. Порядок достижения итогового состояния

1. **Этап H — Контролируемые переходы** — по `dev/migr_plan.md` (и исполняемым планам-алгоритмам
   этапов `dev/migr_plan_0.md`, `dev/migr_plan_1.md`, …, `dev/migr_plan_N.md`; конец одного
   этапа — автоматический гейт в следующий), порядок по зависимостям: `core/state_machine.py`
   (`TaskState` + `ALLOWED_TRANSITIONS` + `can_transition` + `try_transition` +
   `InvalidTransitionError` + `TransitionRecord`/`TransitionLog` + `StateMachine`
   pause/resume/snapshot) → `storage/store.py` (`task_state_path/read/write`) →
   `core/prompt_builder.py` (блок `task_state` в `BLOCK_ORDER`) → `core/agent.py`
   (load_fsm/save_fsm/request_transition/реакция на запрет) → `Kod.py` (`/state`, `/next`,
   `/transition`, `/pause`, `/resume`, `/history`, `/fsm`) → `test_fsm.py` +
   `scenario_invalid_transition` + `scenario_pause_resume` → README (раздел «Контролируемые
   переходы состояний») + Проверка (строки 31–36) → запись этапа в `dev/migr_log.md`.
2. **Финал** — прогон всех проверок (L2→L3→L4→гейт), запись итога в `dev/migr_log.md`,
   предложение коммита (коммит — только по явной команде пользователя).

---

## 6. Итог

После завершения `den_15` получается:

- **Ассистент с контролируемым жизненным циклом задачи**: поверх модели памяти (4 слоя),
  персонализации (мультипрофиль + роутер) и слоя инвариантов (`ConstraintSet` +
  `InvariantChecker`) — **строгая машина состояний** (`StateMachine`): конечный набор
  допустимых состояний (`TaskState`, 7 значений) и явная матрица разрешённых переходов
  (`ALLOWED_TRANSITIONS`, единый источник истины).
- **Блокировка «перепрыгивания» этапа на уровне кода**: любой переход проходит `try_transition`;
  недопустимый бросает `InvalidTransitionError`, состояние **не меняется**, а попытка попадает
  в `TransitionLog` (`allowed=false` + причина). Промт рекомендует, код запрещает (двойная
  защита).
- **Корректная реакция ассистента**: при попытке запрещённого перехода агент остаётся в текущем
  состоянии, называет сработавшее правило и предлагает корректную последовательность
  (`planning`, а не `implementation`).
- **Корректное продолжение после паузы**: `paused` доступна из любого активного состояния,
  `resume()` возвращает ровно в `prev_state`; снимок FSM (`task_state.json`) переживает
  перезапуск, разрешённые переходы после возобновления не меняются, сброса в начало нет.
- **Персистентность и аудит**: состояние и журнал переходов хранятся отдельно от истории
  диалога и от инвариантов; очистка истории не сбрасывает жизненный цикл.
- **Служебное пространство `dev/`**: план миграции `migr_plan.md` — каркас миграции на
  `arch_den_15.md`, исполняемые планы-алгоритмы этапов (`migr_plan_0.md`, `migr_plan_1.md`, …,
  `migr_plan_N.md`; конец этапа — автоматический гейт в следующий), тестовый контур L2–L4 +
  гейт (`test_fsm.py`, `scenario_invalid_transition`, `scenario_pause_resume`, временные файлы
  только в `.tmp/`), полный аудит этапов в журнале миграции `migr_log.md`.

Такой фундамент позволяет следующим дням недели 3 нарастить исполнение пайплайна скиллов
(реальную оркестрацию) и объединение «кубиков» (память → персонализация → автомат →
инварианты → контролируемые переходы) в единую систему без переписывания базы.
