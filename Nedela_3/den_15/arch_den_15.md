# arch_den_15.md — итоговая целевая архитектура проекта `den_15` «Контролируемые переходы состояний»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_15`. Базируется на `Nedela_3/den_14/arch_den_14.md` (персонализированный
> stateful-агент: 4 слоя памяти + мультипрофильность + task state machine + слой инвариантов)
> и модернизирует его **автомат задачи до строгой машины состояний с контролируемыми
> переходами**: явный набор допустимых состояний, явная карта разрешённых переходов,
> программный запрет «перепрыгивания» этапов (`try_transition` → `InvalidTransitionError`),
> журнал попыток и отказов, корректное продолжение после паузы.
> Источники: `Суть_N3.md`, `Задание_Д15.txt` (неизменяемый первоисточник).

---

## 0. Назначение документа

Документ фиксирует три слоя итогового состояния:

1. **Рабочая архитектура** — персонализированный stateful-агент с явной моделью памяти
   (4 слоя), мультипрофильностью, слоем инвариантов и **строгим автоматом задачи**
   (контролируемый жизненный цикл), унаследованный от `den_14` без изменений контрактов
   памяти/профилей/инвариантов, **плюс модернизация `core/state_machine.py`**: состояния
   `NEW`/`PLAN_APPROVED`, API `can_transition`/`try_transition`/`InvalidTransitionError`,
   утверждение плана как отдельная стадия, журнал переходов.
2. **Служебное пространство `dev/`** — «проект про проект»: миграция `den_14` →
   `arch_den_15.md` по процессной модели «план-эталон → рабочие планы этапов → журнал»,
> с полным аудитом каждого этапа.

Главная идея задания (канон `Задание_Д15.txt`): **жизненный цикл задачи — строгая машина
состояний**: чёткий список допустимых состояний и **разрешённых переходов** между ними,
где ассистент **физически не может «перепрыгнуть» этап** — запрет работает на уровне
кода, а не только текста. Даже если пользователь просит «сразу к реализации» или LLM
предлагает «перейдём в implementation прямо сейчас» — код отклоняет попытку перехода,
состояние не меняется, ассистент остаётся в текущем состоянии, объясняет правило и
предлагает корректную последовательность действий.

Формула ценности дня: **недопустимый переход не выполняется молча** — попытка
фиксируется в журнале переходов, состояние остаётся прежним, ассистент называет
сработавшее правило («нельзя делать реализацию до утверждённого плана») и предлагает
правильный следующий шаг («сначала утвердите план — /approve»).

---

## 1. Ключевая идея и принципы

### 1.1 Ключевая идея
`den_15` — переход от «автомата задачи» (день 13: этапы + переходы + пауза/resume) к
**агенту с контролируемым жизненным циклом задачи**. Появляются четыре новых элемента:

1. **Полный набор допустимых состояний** — `TaskStage` расширяется до 8: 4 базовых
   канона недели (`planning → execution → validation → done`, у куратора — не убирать)
   детализируются до **`new → planning → plan_approved → implementation → validation →
   done`** + расширения `paused`/`failed` (день 13, не замены). Любое состояние вне
   набора — недопустимое.
2. **Явная карта разрешённых переходов** — `ALLOWED_TRANSITIONS` (матрица «из → во»);
   переход существует **только если он есть в карте**; всё остальное запрещено по
   умолчанию (whitelist, а не blacklist).
3. **Программный контроль перехода** — API канона задания: `can_transition(from, to)`
   → `bool` и `try_transition(state, proposed)` → новое состояние **или**
   `InvalidTransitionError`; недопустимый переход **не меняет состояние** и
   **логируется** (попытка + отказ).
4. **Утверждение плана — отдельная стадия** — «нельзя делать реализацию до утверждённого
   плана» реализуется не текстом, а топологией графа: из `planning` нет перехода в
   `implementation`; единственный путь — через `plan_approved` (команда `/approve`).

Формула ценности: **процесс выполнения задачи становится формальным workflow** — LLM
работает внутри жёстко заданного жизненного цикла, а не «хаотично скачет по этапам»;
детерминизм недетерминированной нейронке даёт код карты переходов.

### 1.2 Принципы
- **Whitelist переходов**: разрешено только то, что явно перечислено в
  `ALLOWED_TRANSITIONS`; запрет — по умолчанию. Новые запреты не нужно придумывать —
  их даёт отсутствие дуги в графе.
- **Жёсткий запрет — только кодом** (канон `Суть_N3.md`, преемственность дней 13–14):
  промт рекомендует («работай в рамках текущего этапа, не перепрыгивай»), код запрещает
  (`try_transition` → `InvalidTransitionError`). Двойная защита: правило в промте +
  запрет в карте переходов.
- **Состояние не меняется при отказе**: недопустимый переход — no-op для `TaskState`
  (этап, шаг, ожидаемое действие — прежние); меняется только журнал (запись о попытке
  и отказе) и ответ пользователю (отказ с объяснением).
- **Отказ объясняет, а не запрещает молча** (преемственность дня 14): отказ называет
  (1) какой переход попытался выполнить пользователь, (2) какое правило сработало
  («нельзя делать реализацию до утверждённого плана» / «нельзя финал без валидации»),
  (3) корректный следующий шаг. «Нельзя» без объяснения — плохая реакция.
- **Пауза — не лазейка для перепрыгивания**: из `paused` возврат **только** в
  `previous_stage` (то состояние, где были); прямые переходы `paused → implementation`
  запрещены — иначе пауза стала бы способом обойти утверждение плана или валидацию.
  Это **строже** примера карты из задания (`paused → *`), но точнее реализует его
  семантику «возврат в то же состояние, где были».
- **Расширение стадий, не сужение** (канон `Суть_N3.md`): 4 базовых этапа куратора не
  удаляются — `execution` детализируется в `plan_approved + implementation`; `paused`/
  `failed` (расширения дня 13) сохраняются.
- **Канон имён состояний — из задания**: `new`, `planning`, `plan_approved`,
  `implementation`, `validation`, `done`, `paused` (+ `failed` — расширение). Имя
  `execution` дня 13 **переименовывается** в `implementation`; старые снимки
  `task_state.json` мигрируются при загрузке (`"execution"` → `implementation`).
- **Переходы и инварианты — разные сущности контроля** (преемственность дня 14):
  `InvariantChecker` проверяет **действия** (`ProposedAction`: технологии, зависимости,
  схема БД); `state_machine` проверяет **переходы** (этапы жизненного цикла). Оба
  работают по одному принципу «код запрещает», но не сливаются: разные модели, разные
  проверки, разные отказы.
- **Детерминизм без LLM**: карта переходов, `can_transition`/`try_transition`, отказы,
  пауза/resume полностью тестируются на заглушках — живой ключ не нужен.
- **Наследие дней 11–14 без регрессии**: модель памяти (4 слоя), персонализация
  (мультипрофиль + роутер), инварианты (`ConstraintSet`/`InvariantChecker`), LLM-клиент
  — контракты сохраняются полностью; модернизируется только `core/state_machine.py`,
  его callers в `core/agent.py`/`Kod.py` и тесты автомата.

---

## 2. Рабочая структура проекта

### 2.1 Дерево модулей

```
Nedela_3/den_15/
├── Kod.py                       # точка входа: DI-композиция + REPL (+ /approve, /goto, /transitions)
├── core/
│   ├── __init__.py
│   ├── agent.py                 # оркестратор: + approve_plan / attempt_transition (отказ с объяснением)
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient (без изменений)
│   ├── profile_router.py        # ProfileRouter (без изменений от дня 12)
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + deliver + budget (без изменений)
│   ├── state_machine.py         # ← МОДЕРНИЗИРУЕТСЯ: TaskStage (8) + ALLOWED_TRANSITIONS +
│   │                            #   can_transition / try_transition / InvalidTransitionError +
│   │                            #   transition_log + approve / pause / resume
│   └── invariants.py            # Invariant + ConstraintSet + InvariantChecker (без изменений)
├── memory/
│   ├── __init__.py
│   ├── base.py                  # MemoryLayer (ABC) + MemoryContext + PolicyEngine (без изменений)
│   ├── short_term.py            # ShortTermMemory — window + recent() (без изменений)
│   ├── working.py               # WorkingMemory — состояние задачи (+ зеркало stage)
│   ├── long_term.py             # LongTermMemory (без изменений)
│   ├── profile.py               # Profile (без изменений)
│   └── manager.py               # MemoryManager (без изменений)
├── storage/
│   ├── __init__.py
│   ├── store.py                 # фасад: task_state_path/read/write (+ миграция "execution")
│   └── db.py                    # ProfileRepository (без изменений)
├── users/                       # рантайм-хранилище (создаётся при работе)
├── run.sh                       # +x: cd dirname + source ../../.venv/bin/activate + python
├── run.desktop                  # Exec = абсолютный путь к .sh
├── README.md                    # + раздел «Контролируемые переходы состояний»
├── arch_den_15.md               # текущая архитектура проекта den_15
├── Den_log.md                   # журнал: + строки отказов переходов (рантайм-артефакт)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
├── Задание_Д15.txt              # постановка куратора (неизменяемый первоисточник)
└── dev/                         # ← служебное пространство (раздел 3), в т.ч. Проверка.md
```

Изменения относительно `den_14` — только три файла продукта (`core/state_machine.py`,
`core/agent.py`, `Kod.py`) + зеркальные правки `storage/store.py` (миграция снимков) и
`memory/working.py` (зеркало `stage`); остальное наследуется как есть.

### 2.2 Модель состояний (`TaskStage` — 8 состояний)

Канон `Задание_Д15.txt`: конечный набор допустимых состояний; любое другое —
недопустимое. 4 базовых этапа куратора (`Суть_N3.md` §4.8: planning → execution →
validation → done, «не убирать») **детализируются**, а не заменяются: `execution`
расщепляется на `plan_approved` + `implementation`; добавляется входная стадия `new`;
расширения дня 13 (`paused`/`failed`) сохраняются.

```python
# core/state_machine.py
from enum import Enum

class TaskStage(Enum):
    NEW = "new"                    # задача создана, но ещё не начата
    PLANNING = "planning"          # идёт планирование (план строится/построен, не утверждён)
    PLAN_APPROVED = "plan_approved"  # ← НОВОЕ: план утверждён пользователем
    IMPLEMENTATION = "implementation"  # идёт реализация (бывший execution, канон задания)
    VALIDATION = "validation"      # проверка/тестирование
    DONE = "done"                  # задача завершена (терминальная)
    PAUSED = "paused"              # пауза (возврат в previous_stage)
    FAILED = "failed"              # ошибка (восстановление — /task retry)
```

`TaskState` — dataclass из 10 полей (9 прежних + журнал переходов):

| Поле | Тип | Назначение |
|---|---|---|
| `task_id` | `str` | идентификатор задачи (`safe_name(objective)`) |
| `objective` | `str` | цель задачи (текст из `/plan <цель>`) |
| `stage` | `TaskStage` | текущий этап (по умолчанию `NEW`) |
| `current_step` | `int` | индекс текущего шага (0-based) |
| `steps` | `list[str]` | план из LLM/заглушки |
| `expected_action` | `str \| None` | какое действие ожидается дальше |
| `results` | `list[Any]` | результаты выполненных шагов |
| `previous_stage` | `TaskStage \| None` | куда вернуться после паузы |
| `error` | `str \| None` | текст ошибки (при `FAILED`) |
| `transition_log` | `list[dict]` | ← НОВОЕ: журнал переходов (успехи + отказы, §2.7) |

Семантика ожидаемых действий по стадиям (что «ждёт» автомат от пользователя/LLM):

| Стадия | `expected_action` | Кто двигает дальше |
|---|---|---|
| `new` | «сформировать план (/plan <цель>)» | пользователь |
| `planning` | «утвердить план (/approve)» | пользователь |
| `plan_approved` | «начать реализацию (/step или /run)» | пользователь |
| `implementation` | текст текущего шага | автомат (`run_task`) |
| `validation` | «провести валидацию» | автомат (`validator`) |
| `done` | `None` | — (терминальная) |
| `paused` | сохраняется из `previous_stage`-контекста | пользователь (`/resume`) |
| `failed` | «восстановить задачу (/task retry)» | пользователь |

### 2.3 Карта переходов и API контроля (канон задания)

Явная матрица «из → во» (whitelist; всё, чего нет в карте, — запрещено):

```python
# core/state_machine.py
ALLOWED_TRANSITIONS: dict[TaskStage, set[TaskStage]] = {
    NEW:            {PLANNING, PAUSED, FAILED},
    PLANNING:       {PLAN_APPROVED, PAUSED, FAILED},          # НЕТ implementation — план сначала утвердить
    PLAN_APPROVED:  {IMPLEMENTATION, PLANNING, PAUSED, FAILED},  # PLANNING — пересборка плана
    IMPLEMENTATION: {VALIDATION, PLANNING, PAUSED, FAILED},
    VALIDATION:     {DONE, IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    PAUSED:         set(),        # выход только через resume_task() → previous_stage (не через transition)
    DONE:           set(),        # терминальная
    FAILED:         {PLANNING},   # восстановление — явный /task retry
}
```

API контроля — имена из `Задание_Д15.txt`:

```python
def can_transition(from_state: TaskStage, to_state: TaskStage) -> bool:
    """Разрешён ли переход. Единственный источник истины — ALLOWED_TRANSITIONS."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


class InvalidTransitionError(Exception):
    """Недопустимый переход: state не меняется, попытка логируется.
    Сообщение объясняет правило и корректный следующий шаг."""
    def __init__(self, current: TaskStage, proposed: TaskStage):
        self.current = current
        self.proposed = proposed
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))
        super().__init__(
            f"Переход {current.value} → {proposed.value} запрещён. "
            f"Разрешено из {current.value}: {', '.join(allowed) or '—'}."
        )


def try_transition(state: TaskState, proposed: TaskStage) -> TaskState:
    """Единственная точка смены этапа. Недопустимый переход → InvalidTransitionError,
    состояние НЕ меняется; допустимый — меняет stage и пишет в transition_log."""
    if not can_transition(state.stage, proposed):
        raise InvalidTransitionError(state.stage, proposed)
    _log_transition(state, state.stage, proposed, allowed=True)
    state.stage = proposed
    return state
```

Прежняя `transition(state, target) -> bool` сохраняется как обёртка над
`try_transition` (ловит `InvalidTransitionError`, пишет в лог отказ, возвращает
`False`) — обратная совместимость callers дня 13/14; новый код использует
`try_transition` напрямую, когда нужен отказ с объяснением.

### 2.4 Запрещённые переходы (канон задания — следствие карты)

Запреты из задания реализуются **отсутствием дуги в графе** (не `if`-ами):

| Запрет задания | Дуги нет | Следствие |
|---|---|---|
| «нельзя делать реализацию до утверждённого плана» | `new → implementation`, `planning → implementation` | единственный путь в реализацию — через `plan_approved` |
| «нельзя делать финал без валидации» | `planning → done`, `plan_approved → done`, `implementation → done` | единственный путь в `done` — через `validation` |
| «нельзя перепрыгнуть этап» (общее) | любые дуги вне `ALLOWED_TRANSITIONS` | `try_transition` → `InvalidTransitionError`, состояние не меняется |
| пауза — не обход контроля | `paused → implementation`, `paused → done`, … | из `paused` только `resume_task()` → `previous_stage` |

Демонстрационные попытки (для проверок задания): `/goto implementation` из `planning`
→ отказ «нельзя делать реализацию до утверждённого плана»; `/goto done` из
`implementation` → отказ «нельзя завершать без валидации»; `/goto new` из `done` →
отказ «терминальная стадия».

### 2.5 Утверждение плана (новый контрольный пункт жизненного цикла)

Ключевое изменение потока дня 13: `/plan` **больше не ведёт сразу в реализацию**.

```text
/plan <цель>   → new → planning: executor.plan() строит steps[]
                 → автомат ОСТАНАВЛИВАЕТСЯ в planning (план построен, не утверждён)
/approve       → planning → plan_approved (переход только по явной команде пользователя)
/step | /run   → plan_approved → implementation: выполнение шагов (current_step)
                 шаги кончились → validation → validator → done | failed
```

- `/approve` — отдельная идемпотентная команда (как `/pause`/`/resume`, не через
  `run_task`): утверждает план, если стадия `planning`; из других стадий — отказ с
  объяснением (например, из `plan_approved`: «план уже утверждён»).
- `/run` из `planning` **не может перепрыгнуть утверждение**: проходы автомата
  останавливаются в `planning` (план построен, `expected_action = «утвердить план
  (/approve)»`) — контрольный пункт проходит только человек.
- Пересборка плана: `plan_approved → planning` разрешён (пользователь передумал) —
  `/plan <новая цель>` в активной задаче перестраивает `steps[]` и возвращает в
  `planning` (снова требуется `/approve`).
- `retry_task()` (`failed → planning`) сохраняет семантику дня 13: очистка
  `steps/results/error`, новая сборка плана, снова утверждение.

### 2.6 Отказ с объяснением (реакция ассистента)

Канон задания: ассистент «явно сообщает, что переход невозможен; указывает, какое
правило сработало; предлагает корректный следующий шаг». Шаблоны отказов — в
`state_machine.py` (детерминированно, без LLM), правило → текст:

```python
REFUSAL_RULES = {
    (PLANNING, IMPLEMENTATION): (
        "Нельзя делать реализацию до утверждённого плана. "
        "Сначала утвердите план: /approve"
    ),
    (PLAN_APPROVED, DONE): (
        "Нельзя завершать задачу без реализации и валидации. "
        "Сначала выполните шаги (/run) и пройдите валидацию"
    ),
    (IMPLEMENTATION, DONE): (
        "Нельзя делать финал без валидации. "
        "Сначала завершите шаги — автомат сам перейдёт в validation"
    ),
    (NEW, IMPLEMENTATION): (
        "Нельзя делать реализацию до утверждённого плана. "
        "Сначала сформируйте план: /plan <цель>, затем утвердите: /approve"
    ),
    # ... остальные пары — общий шаблон по InvalidTransitionError
}
```

Общий шаблон (для пар без специального правила): «Переход X → Y не разрешён картой
переходов. Разрешено из X: […]. Ближайший корректный шаг: <expected_action>».

Реакция ассистента на попытку перепрыгнуть (CLI `/goto` и запросы вида «сразу к
реализации»):

```text
Вы: /goto implementation
[Автомат] Попытка перехода planning → implementation: ОТКАЗАНО
[Автомат] Правило: нельзя делать реализацию до утверждённого плана.
[Автомат] Корректный шаг: утвердить план (/approve). Состояние: planning (не изменено).
```

Состояние **фактически не меняется** (проверяемо `/state` до и после), в журнале
остаётся запись о попытке и отказе (§2.7).

### 2.7 Журнал переходов (`transition_log`)

Канон задания: «в логе/истории остаётся запись о попытке и отказе». Журнал — поле
`TaskState.transition_log` (переживает перезапуск вместе со снимком) + зеркало в
`Den_log.md`:

```python
def _log_transition(state: TaskState, frm: TaskStage, to: TaskStage,
                    allowed: bool, reason: str = "") -> None:
    state.transition_log.append({
        "from": frm.value,
        "to": to.value,
        "allowed": allowed,          # False — попытка отклонена, состояние не менялось
        "reason": reason,            # текст правила при отказе ("" при успехе)
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
```

Снимок на диске (`task_state.json`, фрагмент):

```json
{
  "task_id": "REST_API_Django",
  "objective": "Сделать REST API на Django",
  "stage": "plan_approved",
  "current_step": 0,
  "steps": ["Создать проект", "Описать модели", "Настроить роуты"],
  "expected_action": "начать реализацию (/step или /run)",
  "results": [],
  "transition_log": [
    {"from": "new", "to": "planning", "allowed": true, "reason": "", "at": "2026-09-22 10:00:01"},
    {"from": "planning", "to": "implementation", "allowed": false,
     "reason": "нельзя делать реализацию до утверждённого плана", "at": "2026-09-22 10:00:31"},
    {"from": "planning", "to": "plan_approved", "allowed": true, "reason": "", "at": "2026-09-22 10:00:44"}
  ]
}
```

Правила: запись — при **каждой** попытке перехода (успешной и отклонённой); журнал
append-only (не переписывается); рост не ограничивается (при необходимости сжатия —
следующие дни); `/transitions` показывает журнал + карту.

### 2.8 Персистентность и миграция снимков

Сейв/лоад — как в дне 13/14 (после каждого перехода/шага и при `/exit`; лоад при старте,
`load_state`, `/task <имя>`), плюс:

- **Миграция имён стадий при загрузке**: снимок дня 13/14 со `"stage": "execution"` →
  `IMPLEMENTATION` (алиас в `TaskState.from_dict`); снимки без `transition_log` →
  `[]`; снимки без `plan_approved`-семантики — совместимы: `planning` дня 13/14 теперь
  означает «план построен, ожидает утверждения» → пользователю достаточно `/approve`.
- **Битый/отсутствующий** `task_state.json` не роняет приложение — задача стартует с
  `NEW` (не `PLANNING`, как в дне 13: входная стадия теперь явная).
- `--fresh` игнорирует снимок (задача с `NEW`).
- Зеркало `current_state` в `working_memory.json` синхронизируется с новым именем
  стадии (`implementation`).

### 2.9 Пауза и продолжение (корректность после паузы — канон задания)

Сценарий проверки из задания: `implementation` → `paused` → перезапуск процесса →
продолжение загружает `implementation`, доступные переходы те же
(`implementation → validation | planning | paused | failed`), агент не «сбрасывается»
в начало и не перескакивает этапы.

Механика (наследие дня 13, расширено на новые стадии):

- `pause_task()` — идемпотентная функция (не через `transition`): сохраняет
  `previous_stage`, ставит `stage = PAUSED`; разрешена из `NEW`/`PLANNING`/
  `PLAN_APPROVED`/`IMPLEMENTATION`/`VALIDATION` (из `DONE`/`FAILED` — отказ с
  объяснением: терминальные/восстановительные стадии не паузятся).
- `resume_task()` — возврат в `previous_stage` (fallback `IMPLEMENTATION`), **не
  трогая** `current_step`/`expected_action`/`steps`/`results`; после перезапуска
  процесса — `load_task_state()` восстанавливает снимок, включая `previous_stage`.
- **Пауза не меняет топологию**: из `paused` нельзя попасть в `implementation`, минуя
  `plan_approved` — возврат только в то состояние, где были (§1.2, «пауза — не
  лазейка»).
- «Продолжение без повторных объяснений» (день 13): план не перестраивается,
  выполненные шаги не повторяются, задача не переспрашивается.

### 2.10 Инжект стейта в промт (уровень 1 — build-prompt)

Порядок блоков не меняется (`BLOCK_ORDER` дня 14); состояние задачи входит в блок
`working` и подмешивается к каждому запросу:

```text
[working]
…
Этап: plan_approved (план утверждён, шаг 0/3)
Ожидаемое действие: начать реализацию (/step или /run)
Пауза (вернуться к: implementation)   ← только при stage = paused
Ошибка: …                             ← только при заполненном error
Стадия задачи: plan_approved          ← зеркало (обратная совместимость)
```

В роль (`[system: роль]`) добавляется правило двойной защиты: **«работай в рамках
текущего этапа задачи, не перепрыгивай этапы; переходы контролирует код»**. LLM видит
стадию и «отождествляет себя с ней», а код не даёт выйти за рамки разрешённых
переходов — та же двойная защита, что у инвариантов дня 14.

### 2.11 Оркестратор `Agent` (контроль переходов в жизненном цикле)

```python
# core/agent.py — дополнение к контракту дня 14 (память/профили/инварианты не меняются)
def approve_plan(self) -> str            # /approve: planning → plan_approved (отказ с объяснением из других стадий)
def attempt_transition(self, target: str) -> str   # /goto <этап>: try_transition + отказ с правилом (демо контроля)
def transitions_report(self) -> str      # /transitions: карта + transition_log
# start_task / step_task / run_to_end / pause_task / resume_task / retry_task —
# адаптируются под новый поток (new → planning → [approve] → plan_approved →
# implementation → validation → done|failed), pause/resume — на новые стадии
```

```
старт → идентификация user_id → активный профиль → load_state()
        └── + load_task_state(): есть task_state.json → задача продолжается
            «с того же места» (миграция "execution" → implementation при необходимости)
цикл:
  /plan <цель>  → start_task(): new → planning (план построен, ожидает утверждения)
  /approve      → approve_plan(): planning → plan_approved (явное утверждение человеком)
  /step         → step_task(): один проход run_task
                  (plan_approved → implementation: первый шаг; implementation: шаг;
                   шаги кончились → validation; validation → done | failed)
  /run          → run_to_end(max_passes=50): до done/failed/paused;
                  из planning — останавливается (утверждение — только человек)
  /goto <этап>  → attempt_transition(): try_transition; отказ → правило + корректный
                  шаг, состояние не меняется, попытка в transition_log
  /pause        → pause_task(): previous_stage сохранён (на любой рабочей стадии)
  /resume       → resume_task(): возврат в previous_stage с current_step
  /task retry   → retry_task(): failed → planning (steps/results/error очищены,
                  снова требуется /approve)
выход:  save_state() + сейв task_state.json (включая transition_log)
```

### 2.12 CLI-команды (рабочие)

| Команда | Назначение |
|---|---|
| `/approve` | ← НОВОЕ: утвердить план (`planning → plan_approved`); из других стадий — отказ с объяснением |
| `/goto <этап>` | ← НОВОЕ: попытка явного перехода (демо контроля: недопустимый → отказ с правилом, состояние не меняется; допустимый — выполняется) |
| `/transitions` | ← НОВОЕ: карта `ALLOWED_TRANSITIONS` + журнал `transition_log` (успехи и отказы) |
| `/plan <цель>` | ИЗМЕНЕНО: `new → planning`, автомат останавливается на утверждении (не ведёт сразу в реализацию) |
| `/step`, `/run`, `/pause`, `/resume`, `/task retry` | адаптированы под новый поток (семантика дня 13 сохранена) |
| `/state` | РАСШИРЕНО: снимок + разрешённые переходы из текущей стадии + счётчик отказов в `transition_log` |
| `/memory`, `/profile`-семейство, `/tasks`, `/task <имя>`, `/deliver`, `/compare`, `/summary`, `/tokens`, `/cost`, `/invariants`, `/invariant add\|set\|on\|off`, `/check`, `/help`, `/exit` | наследуются из дней 11–14 без изменений |

Флаги запуска — 12, без изменений (`--user`, `--profile`, `--deliver`, `--mock`,
`--fresh`, `--log`, `--token-log`, `--memory-dir`, `--max-tokens`, `--price-in`/
`--price-out`, `--budget`).

### 2.13 Память, профили, инварианты, LLM (без изменений)

Модель памяти (4 слоя, `MemoryManager`, `LAYER_ORDER`), `ProfileRepository` (SQLite +
зеркала), `ProfileRouter`, `PromptBuilder` (`BLOCK_ORDER`/`DELIVERABLE`/`budget`),
`core/invariants.py` (`Invariant`/`ConstraintSet`/`ProposedAction`/
`InvariantChecker`/`RuleBasedChecker`), `LLMClient`/`RouterAIClient`/`MockClient` —
контракты дней 11–14 сохраняются полностью; регрессия запрещена (прежние 30 критериев
приёмки остаются зелёными). Единственное касание наследия вне автомата: зеркало
`current_state` в `working_memory.py` и миграция имени стадии в `storage/store.py`
(§2.8).

---

## 3. Служебное пространство `dev/` (проект про проект)

### 3.1 Дерево `dev/`

```
Nedela_3/den_15/dev/
├── migr_plan.md                  # План-эталон миграции den_14 → arch_den_15.md (текущий файл)
├── migr_plan_0.md                # первый этап миграции (конец этапа — автоматический гейт в следующий)
├── migr_plan_1.md                # …
├── migr_plan_N.md                # …
├── migr_log.md                   # журнал миграции den_14 → arch_den_15.md
├── meta_promt/                   # метапромты (вспомогательные промты пользователя)
├── tests_debug/                  # тестирование и отладка
│   ├── check_acceptance.sh       # гейт приёмки (15 проверок, TMP в .tmp/acc_$)
│   ├── unit_runner.py            # L2-раннер юнит-тестов (без pytest)
│   ├── smoke.py                  # L3-смоук: in-process + CLI subprocess
│   ├── scenario.py               # L4-сценарии задания (+ scenario_controlled_transitions)
│   ├── unit/                     # test_{storage,memory,llm,prompt,agent,state,person,fsm,
│   │                             #   invariants}.py + ← НОВОЕ: test_transitions.py
│   ├── scenario/                 # scen_1.md — сценарий ручной демонстрации (переписан под День 15)
│   └── .tmp/                     # единственное место прогонов и временных файлов (.gitignore)
└── logs_reports/                 # логирование и отчёты по этапам
    ├── stages/                   # stage_F_state.md (факт Дня 13) — наследуется
    ├── errors/                   # карточки ошибок: контекст, стек, решение, статус
    └── archive/                  # исторические артефакты Дня 11/12 + указатель (наследуется)
```

> Миграция на `arch_den_15.md` описывается в `dev/migr_plan.md`; на его основе создаются
> подробные исполняемые планы-алгоритмы каждого этапа (`migr_plan_0.md`,
> `migr_plan_1.md`, …, `migr_plan_N.md`) — конец одного этапа является автоматическим
> гейтом в следующий этап. Журнал миграции ведётся в `dev/migr_log.md`. Процессная
> модель — та же, что у дней 13–14 (план-эталон → рабочие планы → журнал; перечитывание
> эталона после каждого этапа; красный гейт → карточка в `errors/`; коммит — только по
> явной команде пользователя).

### 3.2 `tests_debug/` — что именно протестировать (канон задания)

`unit/test_transitions.py` (новый; всё на заглушках, без живого ключа):

- **базовые тесты из задания**:
  - `test_can_transition_allowed`: `can_transition(PLANNING, PLAN_APPROVED)` → `True`;
    `can_transition(PLAN_APPROVED, IMPLEMENTATION)` → `True`;
    `can_transition(IMPLEMENTATION, VALIDATION)` → `True`;
  - `test_can_transition_forbidden`: `can_transition(NEW, IMPLEMENTATION)` → `False`;
    `can_transition(PLANNING, IMPLEMENTATION)` → `False`;
    `can_transition(IMPLEMENTATION, DONE)` → `False`;
    `can_transition(PLANNING, DONE)` → `False`; `can_transition(DONE, NEW)` → `False`;
- **`try_transition` не меняет состояние при отказе**: `try_transition(state(planning),
  IMPLEMENTATION)` → `InvalidTransitionError`; `state.stage` остался `PLANNING`,
  `current_step`/`steps`/`results` не тронуты;
- **`InvalidTransitionError` объясняет правило**: сообщение содержит «запрещён»,
  текущую/целевую стадии и список разрешённых;
- **полный поток**: `new → planning` (план построен, автомат остановился) →
  `/approve`-переход `planning → plan_approved` → `plan_approved → implementation`
  (первый шаг) → шаги → `validation` → `done`; `results` без дублей;
- **`/run` не перепрыгивает утверждение**: `run_to_end` из `planning` останавливается
  в `planning` (переход в `implementation` не выполнялся — по `transition_log`);
- **попытка отклонена — запись в журнале**: после отказа в `transition_log` есть
  запись `{"allowed": false, "reason": …}`; после успеха — `{"allowed": true}`;
- **реакция ассистента**: текст отказа (`REFUSAL_RULES`) содержит правило («нельзя
  делать реализацию до утверждённого плана») и корректный шаг («/approve»);
- **пауза/продолжение**: `pause` из `implementation` → `previous_stage=IMPLEMENTATION`;
  `resume` → та же стадия/шаг; доступные переходы после resume — те же
  (`can_transition(IMPLEMENTATION, VALIDATION)` → `True`, в `DONE` → `False`);
- **перезапуск не сбрасывает и не перескакивает**: save → load → стадия/шаг/
  `transition_log` равны; `paused` после перезапуска → `resume` → `implementation`
  с тем же `current_step`;
- **миграция снимка**: `from_dict` со `"stage": "execution"` → `IMPLEMENTATION`;
  без `transition_log` → `[]`;
- **пауза — не лазейка**: `can_transition(PAUSED, IMPLEMENTATION)` → `False`;
  `can_transition(PAUSED, DONE)` → `False` (только `resume_task()` → `previous_stage`).

`test_fsm.py` (наследие дня 13) — адаптируется под новые имена/стадии без потери
покрытия (прежние проверки: переходы только по карте, pause/resume идемпотентность,
сейв/лоад round-trip, `max_passes`).

`scenario.py` + **`scenario_controlled_transitions`** (L4, сквозной, канон «Проверьте»
из задания): `/plan Сделать REST API` → план построен (planning) → `/goto
implementation` → **отказ** («нельзя делать реализацию до утверждённого плана»,
состояние не изменилось, запись в `transition_log`) → `/approve` → `/goto done` →
**отказ** («нельзя финал без валидации») → `/run` → done → `/goto new` → **отказ**
(терминальная). Вторая ветка: `/plan` → `/step` → `/pause` → перезапуск CLI-процесса →
`/resume` → `/run` → done (шаг не повторён, план не перестроен). Лог содержит строки
«[Автомат] … ОТКАЗАНО».

`smoke.py` (L3) — полный цикл in-process + CLI subprocess с новым потоком
(логи изолированы в `.tmp/`); `check_acceptance.sh` — гейт приёмки **15 проверок**
(12 прежних + 3 новых: недопустимый переход блокируется кодом и логируется; флоу
утверждения плана `/approve`; пауза → перезапуск → resume с теми же переходами),
временный каталог `$TST/.tmp/acc_$$`, `users/` проекта не трогается.

### 3.3 `logs_reports/` — логирование и отчёты по этапам

- `migr_log.md` — журнал миграции `den_14 → arch_den_15.md`: по форме «было → стало →
  проверка → статус» по каждому этапу (автомат дня 13/14 → строгая машина состояний
  дня 15), результаты `test_transitions.py` и `scenario_controlled_transitions`;
- `errors/error_<timestamp>.md` — карточки ошибок (контекст, тип, решение, статус);
  красный гейт этапа → обязательная карточка;
- `stages/`, `archive/` — наследуются из `den_14` без изменений (факты дней 11–13).

---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)
| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | персонализированный stateful-агент с инвариантами и **контролируемым жизненным циклом задачи** |
| `core/state_machine.py` | TaskStage (8) + ALLOWED_TRANSITIONS + can_transition + try_transition + InvalidTransitionError + REFUSAL_RULES + transition_log + approve/pause/resume |
| `users/<id>/tasks/<task>/task_state.json` | снимок TaskState (+ `transition_log`: успехи и отказы переходов) |
| `run.sh` / `run.desktop` | запуск (`.sh` исполняемый, `Exec` — абсолютный путь) |
| `README.md` | описание проекта + **раздел «Контролируемые переходы состояний»** |

### 4.2 Служебные артефакты (процесс)
| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | чек-лист приёмки: 30 прежних + **строки 31–35** (контролируемые переходы) |
| `dev/migr_plan.md` + `migr_plan_0..N.md` | план-эталон и рабочие планы миграции на `arch_den_15.md` |
| `dev/migr_log.md` | журнал миграции (записи этапов + «Итог миграции») |
| `dev/tests_debug/*` | L2/L3/L4 + гейт (15 проверок) + `.tmp/` (единственное место временных файлов) |
| `dev/logs_reports/*` | журнал миграции, ошибки, наследие `stages/`/`archive/` |

> `Проверка.md` живёт **только в `dev/`** — артефакт процесса, не продукт.

### 4.3 Критерии приёмки контролируемых переходов (строки 31–35)
| Пункт | Что проверяем | Как |
|---|---|---|
| 31 | У задачи есть явный набор допустимых состояний | `TaskStage` — 8 состояний (enum); любое вне набора — недопустимое (`test_transitions.py`) |
| 32 | Разрешённые переходы заданы явно | `ALLOWED_TRANSITIONS` + `can_transition` — whitelist; `/transitions` показывает карту |
| 33 | Недопустимый переход блокируется кодом | `try_transition` → `InvalidTransitionError`; состояние не меняется (`/state` до/после); попытка в `transition_log` (`allowed: false`) |
| 34 | Реакция ассистента на попытку перепрыгнуть | отказ называет правило («нельзя реализацию до утверждённого плана» / «нельзя финал без валидации») + корректный следующий шаг (`/approve`, `/run`) |
| 35 | Корректность продолжения после паузы | `pause` → перезапуск → `resume`: та же стадия/шаг, те же доступные переходы, план не перестроен, шаги не повторены (`scenario_controlled_transitions`) |

Регрессия: прежние 30 критериев (память + персонализация + состояние + инварианты)
остаются зелёными.

Гейт: `unit_runner.py` (все тесты, включая `test_transitions.py`) → `scenario.py`
(9 сценариев) → `check_acceptance.sh` 15 из 15 — всё без живого ключа
(`API_KEY=test-key` / `MockClient`).

---

## 5. Порядок достижения итогового состояния

1. **Миграция `den_14` → `arch_den_15.md`** — по `dev/migr_plan.md` (и исполняемым
   планам-алгоритмам этапов `dev/migr_plan_0.md`, `dev/migr_plan_1.md`, …,
   `dev/migr_plan_N.md`; конец одного этапа — автоматический гейт в следующий),
   порядок по зависимостям:
   `core/state_machine.py` (TaskStage 8 + карта + can_transition/try_transition/
   InvalidTransitionError + REFUSAL_RULES + transition_log + approve) →
   `storage/store.py` + `memory/working.py` (миграция снимков `"execution"` + зеркало
   стадии) → `core/agent.py` (approve_plan / attempt_transition / адаптация
   start/step/run/pause/resume/retry под новый поток) → `Kod.py` (`/approve`,
   `/goto`, `/transitions`; `/plan`/`/state` адаптация) → `test_transitions.py` +
   адаптация `test_fsm.py` + `scenario_controlled_transitions` + гейт 12→15 →
   README (раздел «Контролируемые переходы») + `Проверка.md` (строки 31–35) →
   `scen_1.md` под День 15 → запись этапа в `dev/migr_log.md`.
2. **Финал** — прогон всех проверок (L2→L3→L4→гейт 15/15), приёмка 35/35, запись итога
   в `dev/migr_log.md`, предложение коммита (коммит — только по явной команде
   пользователя).

---

## 6. Итог

После завершения `den_15` получается:

- **Ассистент с контролируемым жизненным циклом задачи**: поверх модели памяти
  (4 слоя), персонализации (мультипрофиль + роутер), автомата и инвариантов
  (дни 11–14) — **строгая машина состояний**: 8 допустимых состояний (`new`,
  `planning`, `plan_approved`, `implementation`, `validation`, `done`, `paused`,
  `failed`), явная карта `ALLOWED_TRANSITIONS` (whitelist), программный контроль
  `can_transition`/`try_transition`/`InvalidTransitionError`.
- **Перепрыгивание этапов невозможно**: «нельзя реализацию до утверждённого плана» и
  «нельзя финал без валидации» реализованы топологией графа (отсутствием дуг);
  `/run` не может обойти утверждение плана; пауза — не лазейка (возврат только в
  `previous_stage`).
- **Отказ с объяснением**: попытка недопустимого перехода не меняет состояние;
  ассистент называет сработавшее правило и предлагает корректный следующий шаг;
  каждая попытка (успех и отказ) фиксируется в `transition_log` и переживает
  перезапуск.
- **Корректное продолжение после паузы**: `pause` → перезапуск процесса → `resume`
  возвращает ту же стадию и шаг; доступные переходы те же; план не перестраивается,
  шаги не повторяются.
- **Обратная совместимость**: снимки дней 13/14 мигрируются при загрузке
  (`"execution"` → `implementation`); прежние 30 критериев приёмки — без регрессии;
  контракты памяти/профилей/инвариантов/LLM не тронуты.
- **Служебное пространство `dev/`**: план-эталон `migr_plan.md` + рабочие планы
  этапов + журнал `migr_log.md` (процессная модель дней 13–14), тестовый контур
  L2–L4 + гейт 15/15 без живого ключа, `Проверка.md` — 35 критериев.

Такой фундамент позволяет следующим дням недели 3 наращивать исполнение пайплайна
скиллов и объединение «кубиков» (память → персонализация → автомат → инварианты →
контролируемый жизненный цикл) в единую систему без переписывания базы.





## 7. Краткое описание архитектуры

### 7.1 Формула для самой краткой характеристики (1 строка):

  > Персонализированный stateful-агент с 4-слойной памятью, мультипрофилями инвариантами, поверх которого жизненный цикл задачи — формальный workflow: whitelist-граф переходов делает «перепрыгивание этапов» физически невозможным на уровне кода.

### 7.2 Краткое и точное описание архитектуры den_15

  Одно предложение (суть):

  > den_15 — CLI stateful-агент (RouterAI, step-3.5-flash), в котором жизненный цикл задачи управляется не LLM, а строгой машиной состояний на Python: 8 допустимых стадий, явная whitelist-карта переходов,
  программный запрет перепрыгивания этапов и журнал всех попыток.

  Развёрнуто в 5 слоях (снизу вверх):

   1. Хранилище (storage/) — фасад Store над канонической иерархией JSON (users/<id>/tasks/<task>/…) + SQLite-репозиторий профилей с автоматической миграцией старых схем.
   2. Память (memory/) — 4 физически отдельных слоя (краткосрочная / рабочая / долговременая / профиль), запись только через MemoryManager.remember(), доставка в промт — дозированная (deliver + токен-бюджет).
   3. Ядро (core/) — оркестратор Agent, PromptBuilder (явные блоки), ProfileRouter (детерминированный выбор профиля), LLMClient (ABC + живой/мок), слой инвариантов InvariantChecker (проверка действий кодом).
   4. Машина состояний (core/state_machine.py) — сердце дня 15: TaskStage (8: new → planning → plan_approved → implementation → validation → done + paused/failed), ALLOWED_TRANSITIONS (whitelist),
      can_transition/try_transition/InvalidTransitionError, REFUSAL_RULES, transition_log. Запреты реализованы топологией графа (отсутствием дуг), а не if-ами: в implementation — только через plan_approved
      (/approve), в done — только через validation, из paused — только resume в previous_stage.
   5. CLI (Kod.py) — REPL с DI-композицией, 32 формы команд, 12 флагов.

  Ключевые принципы:

   - «Код запрещает, промт рекомендует» — двойная защита (правило в промте + запрет в карте переходов);
   - Недопустимый переход — no-op: состояние не меняется, попытка логируется, отказ объясняет правило и коректный шаг;
   - Переходы (state_machine) и инварианты (InvariantChecker) — разные сущности контроля: этапы vs действия;
   - Однонаправленные зависимости: Kod.py → core → memory → storage;
   - Всё детерминированное тестируется на заглушках без живого ключа (91 юнит-тест, гейт 15/15, приёмка 35/35).



### 7.3  Полная картина архитектуры с механикой частей

  Общая формула

  Персонализированный stateful-CLI-агент, собранный из четырёх «кубиков» дней 11–14 (память → персонализация → состояние → инварианты), поверх которых день 15 добавляет пятый: контролируемый жизненный цикл
  задачи. Зависимости однонаправленные: Kod.py → core/ → memory/ → storage/; слои памяти и ядро не трогают ФС напрямую — только через фасад Store.

  ---

  1. Хранилище (storage/) — «где всё лежит»

  `store.py` (фасад): единственный, кто знает пути. Каноническая иерархия:

    1 users/<user_id>/
    2 ├── profile.json             # зеркало default-профиля
    3 ├── profiles/<pid>.json      # зеркала всех профилей
    4 ├── long_term_memory.json    # ссылка на профиль + задачи + решения + знания
    5 └── tasks/<task_name>/
    6     ├── invariants.json       # неизменяемые правила (день 14)
    7     ├── task_state.json      # снимок TaskState + transition_log (день 15)
    8     ├── working_memory.json   # пересчитываемое состояние задачи
    9     ├── sessions_resume.md   # резюме сессий
   10     └── sessions/<sid>/session.json  # append-only история сообщений

  Механика устойчивости: битый/отсутствующий файл не роняет приложение — чтение всегда возвращает схему по умолчанию. При загрузке task_state.json работает миграция: "stage": "execution" (день 13/14) →
  implementation, отсутствие transition_log → [], отсутствие stage → NEW.

  `db.py` (SQLite): таблица profiles(user_id, profile_json, is_default, updated_at), PK (user_id, profile_id). При открытии старая схема дня 11 (user_id PRIMARY KEY) мигрируется одной транзакцией — данные не
  теряются. При недоступной БД чтение откатывается на JSON-зеркала profiles/.

  Ключевой принцип разделения: история (session.json), состояние памяти (working_memory.json), состояние жизненного цикла (task_state.json) и правила (invariants.json) — четыре разные сущности, четыре файла.
  Очистка истории не сбрасывает состояние и не трогает инварианты.

  ---

  2. Память (memory/) — «что агент помнит»

  Четыре слоя, каждый — отдельный класс и отдельное хранилище:


  Краткосрочная (ShortTermMemory, scope=session)
   - Механика записи: append-only — неизменяемые сообщения {id, parent_id, role, content}; parent_id — задел ветвления диалога (наследие дня 10).
   - Механика чтения: окно последних 10 сообщений (SHORT_TERM_WINDOW); в промт идёт отдельными сообщениями {role, content}, а не скленным текстом.

  Рабочая (WorkingMemory, scope=task)
   - Механика записи: MERGE — списки (decisions, facts, open_questions) дополняются, скаляры (description, current_state) перезаписываются.
   - Механика чтения: пересчитываемое состояние задачи → блок [working] промта (включая этап/шаг/ожидаемое действие).

  Долговременая (LongTermMemory, scope=user)
   - Механика записи: profile_ref — только сылка на профиль (сам профиль — отдельная сущность в SQLite); плюс tasks[] с source_session, decisions[] {text, status}, knowledge[].
   - Механика чтения: живёт между сессиями и задачами → блок [long_term] промта.

  Профиль (Profile, scope=user)
   - Механика записи: слияние по ключам — словари style/constraints/context мержатся, инвариант MERGE действует для активного профиля.
   - Механика чтения: активный профиль сессии → блок [profile] промта (стиль, ограничения, контекст, домен, пайплайн скилов).

  `MemoryManager` — единая точка входа:
   - remember(layer, ...) — запись с логом маршрута «какой слой ← что»;
   - recall() — чтение выбранных слоёв;
   - build_blocks() — текстовые блоки в порядке LAYER_ORDER = profile → long_term → working → short_term;
   - report() — снимок для /memory.

  Дозированная доставка:
   - в промт попадают только слои из deliver (по умолчанию полный канонический набор DELIVERABLE);
   - --deliver profile,working физически исключает long_term из блоков и из текста запроса;
   - токен-бюджет: необязательный блок пропускается, если used + tokens > budget; роль и текущий запрос не урезаются никогда.



  ---

  3. Персонализация (core/profile_router.py + профили) — «кто отвечает»

  Модель: на одного user_id — несколько профилей-«призм» (Химик / Психолог / Экономист). Профиль = {profile_id, name, domain, triggers[], style, constraints, context, skills[]}; skills — декларативный
  упорядоченный пайплайн инструкций (движок исполнения — задел следующих дней).

  Механика роутера (детерминированная, без LM): за каждое вхождение триггера в текст запроса (регистронезависимо) — +2, за вхождение domain — +1; победитель = максимум (>0); ничья или ноль → None (остаёмся на
  текущем). Решение логируется. Режим /profile auto on запускает роутер до сборки промта — один и тот же запрос при разных профилях даёт разный состав промта и разный ответ.

  ---

  4. Инварианты (core/invariants.py) — «что агенту запрещено делать» (день 14)

  Сущности: Invariant (правило: id, description, category, severity, active) → ConstraintSet (набор, хранится в invariants.json отдельно от диалога) → ProposedAction (предлагаемое действие: technology,
  adds_dependency, changes_database_schema, language) → InvariantChecker (ABC) / RuleBasedChecker (детерминированная реализация без LLM).

  Механика: перед выполнением действия запускается Python-проверка. Нарушение → инструмент не вызывается, пользователю — отказ из четырёх частей: (1) какое действие, (2) какой инвариант нарушен, (3) почему
  обязателен, (4) допустимая альтернатива. Изменение правила — только /invariant set <id> <текст> --yes (без --yes — PermissionError). Блок [invariants] входит в промт после профиля.

  Важно: инварианты проверяют действия, машина состояний — переходы. Разные модели, разные проверки, разные отказы; не сливаются.

  ---

  5. Машина состояний (core/state_machine.py) — сердце дня 15

  Состояния (TaskStage, 8): new → planning → plan_approved → implementation → validation → done + paused / failed. Канон недели (planning → execution → validation → done) не заменён, а детализирован: execution
  расщеплён на plan_approved + implementation, добавлен вход new.

  Карта переходов — whitelist-матрица; запрет реализуется отсутствием дуги, а не if-ом:

    1 ALLOWED_TRANSITIONS = {
    2     NEW:           {PLANNING, PAUSED, FAILED},
    3     PLANNING:     {PLAN_APPROVED, PAUSED, FAILED},  # НЕТ implementation!
    4     PLAN_APPROVED: {IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    5     IMPLEMENTATION:{VALIDATION, PLANNING, PAUSED, FAILED},
    6     VALIDATION:   {DONE, IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    7     PAUSED:       set(),   # выход только через resume_task() → previous_stage
    8     DONE:          set(),    # терминальная
    9     FAILED:        {PLANNING}, # восстановление — только /task retry
   10 }

  API контроля (единственная точка смены этапа):

   - can_transition(from, to) -> bool — истина только если дуга есть в карте;
   - try_transition(state, proposed) -> TaskState — допустимый: меняет stage + запись в журнал; недопустимый: InvalidTransitionError, состояние не меняется (no-op: этап, шаг, expected_action прежние), попытка
     логируется с allowed=False;
   - прежняя transition() -> bool сохранена как обёртка — обратная совместимость callers дней 13/14.

  Механика отказов (REFUSAL_RULES, детерминированно, без LLM): отказ называет три вещи — какой переход пытались, какое правило сработало («нельзя делать реализацию до утверждённого плана» / «нельзя финал без
  валидации» / «терминальная стадия»), корректный следующий шаг («сначала /approve»). Пары без специального правила — общий шаблон со списком разрешённых из текущей стадии.

  Журнал `transition_log` — 10-е поле TaskState: append-only записи {from, to, allowed, reason, at} при каждой попытке (успех и отказ); переживает перезапуск вместе со снимком; /transitions показывает карту +
  журнал + счётчик отказов.

  Контрольный пункт человека: /plan <цель> строит план и останавливается в planning; /approve — единственный переход в plan_approved; /run из planning не может перепрыгнуть утверждение (проходы останавливаются).
  Пересборка плана (plan_approved → planning) разрешена — снова нужен /approve.

  Пауза: pause_task() сохраняет previous_stage (идемпотентна, разрешена на 5 рабочих стадиях); resume_task() возвращает в previous_stage, не трогая current_step/steps/results. Из paused нет дуг — пауза не лазейка
  обойти утверждение или валидацию.

  ---

  6. Оркестратор и промт (core/agent.py, core/prompt_builder.py)

  `Agent` — stateful-оркестратор: идентификация/интервью пользователя, respond() (обычный обмен), switch_task/switch_profile, жизненный цикл (start_task / approve_plan / step_task / run_to_end / pause / resume /
  retry_task / attempt_transition / transitions_report), инварианты (propose_and_check), сейв/лоад состояния. Исполнители: LLMExecutor (план/шаги через LLM) / StubExecutor (заглушка) + default_validator.

  Сборка промта — явные блоки в жёстком порядке:

   1 [system: роль] → [profile] → [invariants] → [long_term] → [working] →
   2 [summary, опц.] → [messages: short_term (окно 10)] → [user: запрос] → [резерв под ответ]

  Состояние задачи инжектится в блок [working]: «Этап: plan_approved (шаг 0/3)», «Ожидаемое действие: …», при паузе — «вернуться к: …», при ошибке — текст. В роль добавлено правило двойной защиты: «работай в
  рамках текущего этапа, не перепрыгивай; переходы контролирует код».

  LLM за интерфейсом: LLMClient (ABC) → RouterAIClient (POST + Bearer, retry на 429 с задержками 2→4→8 сек, таймаут 30 сек, любой сбой → None, цикл не прерывается) и MockClient (детерминированная заглушка,
  отражающая видимые блоки — ею проверяется доставка без сети). Провайдер инжектится на старте; при --mock / отсутствии ключа / API_KEY=test-key автоматически MockClient.

  ---

  7. CLI (Kod.py) — точка входа

  DI-композиция build_agent() + REPL: 32 формы команд (/plan, /approve, /goto, /transitions, /step, /run, /pause, /resume, /task retry, /state, /memory, семейство /profile (6), семейство /invariant (3), /check,
  /deliver, /compare, /tokens, /cost…), 12 флагов (--user, --profile, --deliver, --mock, --fresh, --budget, --memory-dir…). Токен-учёт: локальная оценка ~1 токен / 4 символа + CSV-журнал стоимости.
  EOFError/KeyboardInterrupt тоже вызывают save_state() — состояние не теряется.

  ---

  8. Служебное пространство dev/ — «проект про проект»

  Процессная модель миграции den_14 → arch_den_15.md: план-эталон migr_plan.md → исполняемые планы этапов migr_plan_0..7.md (конец этапа — автоматический гейт в следующий) → журнал migr_log.md; красный гейт →
  карточка ошибки в errors/. Тестовый контур: L2 — собственый раннер unit_runner.py (pytest в venv нет) с 10 модулями, 91 OK; L3 — smoke.py (in-process + CLI subprocess); L4 — scenario.py, 9 сценариев; гейт
  check_acceptance.sh — 15/15 идемпотентно, всё в .tmp/ (в .gitignore), рабочие users/ не трогаются, живой ключ не нужен. Человеческая приёмка — Проверка.md, 35/35 (30 прежних без регрессии + строки 31–35
  контролируемых переходов).

  ---

  Сводная механика одного обмена

   1 запрос → [auto_route: роутер выбирает профиль ДО сборки промта]
   2       → remember_message("user") → build_context(profile_id)
   3        → PromptBuilder.build(ctx, deliver, budget)  # в [working] — этап/шаг/ожидаемое действие
   4        → llm.complete(messages) → ответ → remember_message("assistant") + строка в tokens.csv

  И сводная механика жизненного цикла:

   1 /plan → new→planning (план построен, СТОП) → /approve → plan_approved
   2      → /step|/run → implementation (шаги) → validation → done|failed
   3 любой /goto вне карты → InvalidTransitionError: состояние не изменилось,
   4 правило + коректный шаг, запись allowed:false в transition_log

  Инвариант всей системы: детерминизм недетерминированной LLM даёт код — карта переходов, роутер, инварианты и отказы полностью проверяются на заглушках без сети.

