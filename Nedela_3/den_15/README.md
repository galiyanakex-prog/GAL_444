# День 15 — Контролируемые переходы состояний (Controlled State Transitions)

> **Неделя 3** — «Память и состояние агента: переход от stateless к stateful».
> День 15 — поверх явной модели памяти (День 11), персонализации (День 12), формализованного
> состояния задачи (День 13) и слоя инвариантов (День 14) жизненный цикл задачи превращён
> в **строгую машину состояний**: конечный набор допустимых состояний, явная матрица
> разрешённых переходов и **программная блокировка любого «перепрыгивания» этапа**.
> Даже если пользователь просит «давайте сразу реализацию, без плана», а LLM в рассуждении
> предлагает «перейдём в `implementation` прямо сейчас» — переход отклоняется **на уровне
> кода** (`try_transition` → `InvalidTransitionError`), состояние **не меняется**, а ассистент
> объясняет правило процесса и предлагает корректную последовательность.
> Формула ценности — **недопустимый переход не выполняется молча**: агент остаётся в текущем
> состоянии, называет сработавшее правило и предлагает допустимый следующий шаг.
> Формат результата — Код / Текст. Целевая архитектура — `arch_den_15.md`.

## Суть проекта

CLI-агент (RouterAI, модель `stepfun/step-3.5-flash`) с **явной моделью памяти**,
**настраиваемой персонализацией**, **формализованным состоянием задачи**, **набором
неизменяемых правил (инвариантов)** и **контролируемым жизненным циклом задачи**. Память
разделена на четыре физически отдельных слоя (краткосрочная / рабочая / долговременная /
профиль), запись идёт только явным вызовом `memory.remember(layer, ...)`, а набор слоёв,
попадающих в промт, — параметр `deliver: set[str]` (дозированная доставка).

Поверх модели памяти пользователь настраивает агента под себя и под задачу: на одного
`user_id` заводится **несколько профилей**-«призм» (пример куратора: Химик / Психолог /
Экономист для постов в ТГ; агент для покупок → сборка корзины). **Общий профиль-роутер**
детерминированно выбирает конкретный профиль по тексту запроса, **профиль = упорядоченный
пайплайн скиллов**, чьи инструкции подмешиваются в промт. Активный профиль привязан к сессии
и подключён к каждому запросу — один и тот же запрос при разных профилях даёт разный состав
промта и разный ответ.

Сверху — **набор инвариантов** (`ConstraintSet` + `InvariantChecker`, День 14): неизменяемые
правила хранятся отдельно от диалога (`invariants.json`), явно учитываются в рассуждениях
(блок `[system: инварианты]`) и **проверяются кодом** до выполнения действия; запрос,
конфликтующий с инвариантом, не выполняется молча — агент называет нарушенное правило,
объясняет причину и предлагает допустимую альтернативу.

Вершина — **строгая машина состояний жизненного цикла задачи** (`core/state_machine.py`):
LLM составляет план и наполняет шаги, но жизненным циклом управляет Python-код. У задачи
есть конечный набор допустимых состояний (`TaskState`: `new`, `planning`, `plan_approved`,
`implementation`, `validation`, `done`, `paused`) и **явная матрица разрешённых переходов**
(`ALLOWED_TRANSITIONS` — единственный источник истины). Любой переход проходит через
`try_transition`: недопустимый бросает `InvalidTransitionError`, состояние **не меняется**,
а попытка попадает в `TransitionLog`. Состояние сейвится в `task_state.json` после каждого
перехода и при выходе, поэтому пауза переживает перезапуск процесса.

Ключевая идея дня: **процесс выполнения задачи — это формальный workflow с контролируемыми
этапами, где LLM работает внутри жёстко заданного жизненного цикла, а не хаотично скачет по
этапам**. «Код запрещает, промт рекомендует»: правило «не перепрыгивай этап» дублируется —
и в промте (блок состояния задачи), и в `try_transition` (жёсткий запрет). Двойная защита.

## Что нового относительно Дня 14

- **Строгая машина состояний (`core/state_machine.py`, усиление)**: конечный enum
  `TaskState` (7 состояний) + явная матрица `ALLOWED_TRANSITIONS` (единый источник истины)
  + `can_transition()` + `try_transition()` + `InvalidTransitionError` (программная блокировка
  недопустимого перехода) + `TransitionRecord`/`TransitionLog` (аудит всех попыток);
- **Контролируемый переход**: любой переход проходит `try_transition`; при `can_transition
  == False` переход **не выполняется** — состояние остаётся прежним, вызывающий код получает
  `InvalidTransitionError` с текущим состоянием и списком разрешённых;
- **`StateMachine`**: единственное место, где меняется состояние; `transition()`,
  `allowed_next()`, `pause()`, `resume()` (возврат **ровно в `prev_state`**),
  `snapshot()`/`from_snapshot()` (сериализация для `task_state.json`);
- **`task_state.json` обновлён**: снимок теперь хранит `state` + `prev_state` + `TransitionLog`
  (журнал переходов с отметкой `allowed` и причиной отказа) — переживает перезапуск;
- **Инжект состояния в промт**: новый блок `task_state` (после `invariants`, до `working`) —
  текущее состояние + разрешённые переходы + список запретов; входит в `BLOCK_ORDER` и
  участвует в дозированной доставке (`deliver`);
- **Жизненный цикл в `Agent`**: `load_fsm()` / `save_fsm()` / `request_transition(proposed)` /
  `pause()` / `resume()` / `allowed_next()` / `transition_log()`; при запрете — реакция
  ассистента (`_transition_refusal`);
- **7 форм команд REPL**: `/state` (усилена), `/next`, `/transition <state>`, `/pause`,
  `/resume`, `/history`, `/fsm`; `/plan`, `/step`, `/run`, `/task retry` наследуются из Дня 13
  и теперь работают **под контролем FSM**;
- **Флаг `--rework`**: опциональное расширение `VALIDATION → IMPLEMENTATION` (возврат на
  доработку при провале валидации); по умолчанию выключен, чтобы строго соответствовать
  примеру задания;
- **Тестовый контур расширен**: L2 — усиленный `test_fsm.py` (переходы/запреты/pause/resume/
  персистентность); L4 — `scenario_invalid_transition` + усиленный `scenario_pause_resume`;
  приёмка — **36 критериев** (30 прежних + 31–36);
- **Наследие Дня 14 без изменений**: инварианты (`ConstraintSet` + `InvariantChecker` + отказ
  с объяснением), персонализация, модель памяти (4 слоя), каноническая иерархия хранения.

## Что нового относительно Дня 13 (наследие Дня 13)

- **Полный конечный автомат задачи**: задел (Enum из 4 стадий + `next_state()`) развёрнут в
  формализованный жизненный цикл; dataclass `TaskState`-снимок (поля канона задания),
  `ALLOWED_TRANSITIONS` + `transition()` (единственная точка смены этапа с логом
  «[Автомат] X → Y»), `pause_task()`/`resume_task()`, `save_state()`/`load_state()` (JSON,
  enum ↔ `.value`, битый файл → `None`), `run_task(state, executor, validator)` (один проход);
- **`task_state.json` в иерархии хранения**: `users/<id>/tasks/<task>/task_state.json` —
  снимок жизненного цикла; фасад `Store` дополнен `task_state_path()` / `read_task_state()` /
  `write_task_state()`;
- **Инжект стейта в промт (уровень 1 — build-prompt)**: блок `working` несёт строки «Этап:
  …», «Ожидаемое действие: …», «Пауза (вернуться к: …)», «Ошибка: …»; прежняя строка «Стадия
  задачи» сохранена (зеркало, обратная совместимость); авторитет — `task_state.json`;
- **Жизненный цикл в `Agent`**: `start_task()` / `step_task()` / `run_to_end(max_passes=50)` /
  `pause()` / `resume()` / `retry_task()` / `load_task_state()` + единая точка
  `_persist_task_state()`; `executor`/`validator` — инжектируемые зависимости (`LLMExecutor`
  для живого режима, `StubExecutor` для `--mock`/`test-key`, `default_validator(results) =
  len(results) > 0`); `save_state()` дополнительно сейвит `task_state.json`; `switch_task()`
  подтягивает состояние новой задачи;
- **Формы команд REPL**: `/plan <цель>`, `/step`, `/run`, `/pause`, `/resume`, `/task retry`;
  `/state` расширен до полного снимка `TaskState` + карта разрешённых переходов; `--fresh`
  дополнительно игнорирует `task_state.json`;
- **Наследие Дня 12 (персонализация) без изменений**: мультипрофильность, профиль-роутер,
  пайплайн скиллов, дозированная доставка, модель памяти (4 слоя), naming без признака дня.

## Модель памяти

| Тип | Что хранит | Где (файл/хранилище) | Почему так |
|---|---|---|---|
| **Краткосрочная** (`ShortTermMemory`, scope=`session`) | текущий диалог — неизменяемые сообщения с `id`/`parent_id` | `users/<id>/tasks/<task>/sessions/<sid>/session.json` | сообщения — история (append-only), их нельзя переписывать; `parent_id` — задел ветвления (наследие Дня 10) |
| **Рабочая** (`WorkingMemory`, scope=`task`) | состояние задачи: `description`, `refs`, `lifecycle_summary`, `decisions`, `constraints`, `facts`, `open_questions`, `current_state` | `users/<id>/tasks/<task>/working_memory.json` | это **пересчитываемое состояние**, а не лог сообщений: списки дополняются, скаляры перезаписываются |
| **Долговременная** (`LongTermMemory`, scope=`user`) | `profile_ref` (ССЫЛКА), `tasks[]` (со ссылками и `source_session`), `decisions[]` (`{text, status}` — «выполнена»/«не выполнена»), `knowledge[]` | `users/<id>/long_term_memory.json` | живёт между сессиями и задачами; профиль держится отдельно, здесь — только ссылка (канон куратора) |
| **Профиль** (`Profile`, scope=`user`) | **несколько профилей** на пользователя: `profile_id`, `name`, `domain`, `triggers[]`, `style` + `constraints` + `context`, `skills[]` (пайплайн) | JSON в SQLite (`profiles(user_id, profile_id)`), зеркала `users/<id>/profiles/<pid>.json` | канон куратора: профили — отдельная сущность в БД, а не часть долговременной памяти; запись слиянием (MERGE); активный профиль подключён к каждому запросу |

Единая точка входа в память — `MemoryManager`: `remember()` (запись с логом маршрута),
`recall()` (чтение выбранных слоёв), `build_blocks()` (текстовые блоки для промта в порядке
`LAYER_ORDER = profile → long_term → working → short_term`), `report()` (снимок для `/memory`).

> **Про «долговременная (профиль, решения, знания)» из задания.** Формулировка описывает
> *содержание* типа, а не одну файловую реализацию. Реализован предпочтительный по куратору
> вариант: профиль — отдельное хранилище (SQLite), в `long_term_memory.json` — ссылка.

### Иерархия хранения (канон куратора)

```
users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite profiles)
├── profiles/                    # зеркала всех профилей пользователя
│   ├── default.json
│   ├── chemist.json
│   └── economist.json
├── long_term_memory.json        # profile_ref + задачи + решения + знания
└── tasks/<task_name>/
    ├── invariants.json          # ← День 14: ConstraintSet (неизменяемые правила задачи)
    ├── task_state.json          # ← День 15: снимок FSM (state + prev_state + TransitionLog)
    ├── working_memory.json      # пересчитываемое состояние задачи (+ current_state — зеркало стадии)
    ├── sessions_resume.md       # резюме сессий задачи (блок summary в промте)
    └── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
        └── session.json         # краткосрочная память: сообщения с parent_id
```

Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — **формализованный жизненный
цикл**; `invariants.json` — **неизменяемые правила**. Четыре разные сущности, четыре файла.
**Очистка истории диалога не сбрасывает FSM и не удаляет инварианты** (разные файлы).

База профилей — `users/profiles.db` (общая для всех пользователей).
Все пути знает только `storage/store.py` (`safe_name`, `ensure_user/task/session`,
`read_json`/`write_json` с каноническими дефолтами, `invariants_path`/`read/write_invariants`,
`task_state_path`/`read/write_task_state`). Битый или отсутствующий файл не роняет приложение —
чтение всегда возвращает схему по умолчанию; при недоступной БД `load_profile`/`list_profiles`
откатываются на зеркала `profiles/` → `profile.json`.

### Сборка промта (явные блоки + дозированная доставка + бюджет)

```
[system: роль] → [system: profile] → [system: invariants] → [system: task_state] →
[system: long_term] → [system: working] → [system: summary, опц.] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER = ("role", "profile", "invariants", "task_state", "long_term", "working",
  "summary", "short_term", "current")`;
- слои добавляются system-блоками с заголовком `[<имя>]` **только если имя есть в `deliver`**;
- `short_term` идёт отдельными сообщениями `{role, content}`, а не склеенным текстом;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; роль и запрос не
  урезаются никогда;
- «резерв» — это место под ответ модели (лимит бюджета), а не сообщение в запросе.

## Персонализация

Поверх модели памяти — **несколько профилей на пользователя** (`arch_den_12.md` §2.3–2.7).
Профиль — «призма» под домен/задачу: он определяет стиль, ограничения, контекст, доменную
область и порядок скиллов. Активный профиль привязан к сессии и входит в каждый промт,
поэтому один и тот же запрос даёт разные ответы.

### Модель профиля (расширение JSON, обратно совместимое)

```json
{
  "id": "<user_id>",
  "profile_id": "chemist",
  "name": "Химик",
  "domain": "химия",
  "triggers": ["химия", "реактив", "реакция"],
  "style": {"answers": "строго по формулам"},
  "constraints": {"answers": "..."},
  "context": {"answers": "..."},
  "skills": [
    {"name": "spec",   "instructions": "сначала составь спеку ответа"},
    {"name": "review", "instructions": "проверь факты по домену"}
  ]
}
```

- `profile_id` — короткое имя профиля (`safe_name`); первый/единственный профиль — `default`;
  `domain`/`triggers`/`skills` опциональны (пустые — профиль работает как в Дне 11);
- **профиль = декларативный пайплайн скиллов**: упорядоченные инструкции подмешиваются в промт
  блоком «Пайплайн скиллов:» (движок исполнения скиллов — следующие дни);
- **хранение**: SQLite `profiles(user_id, profile_id, …, is_default)` + зеркала
  `users/<id>/profiles/<pid>.json`; `users/<id>/profile.json` остаётся зеркалом `default`;
  БД старой схемы мигрируется автоматически при открытии;
- **запись слиянием**: `Profile.write()` обновляет только переданные поля, словари
  `style`/`constraints`/`context` мержатся по ключам — инвариант MERGE действует для активного
  профиля (`ctx.profile_id`);
- **память независима от профилей**: краткосрочная/рабочая/долговременная не меняются при
  переключении профиля — профиль влияет только на блок `profile` в промте.

### Профиль-роутер (`core/profile_router.py`)

Общий профиль-роутер выбирает конкретный профиль по тексту запроса — детерминированно, без
LLM: **+2** за вхождение каждого триггера (регистронезависимо), **+1** за вхождение `domain`;
победитель = максимум (>0); ничья или ноль → `None` (остаёмся на текущем/дефолтном). Решение
логируется («[Роутер] запрос → профиль chemist (счёт 5)»), разбор по каждому кандидату
показывает `/profile route <текст>`. Режим `/profile auto on` запускает роутер на каждый запрос
**до** сборки промта.

## Инварианты и ограничения состояния (День 14)

Слой **неизменяемых правил** (`core/invariants.py`): `Invariant` (id, description, category,
severity, active) + `ConstraintSet` (набор активных правил) + `InvariantChecker` (проверка
`ProposedAction` кодом). Инварианты **хранятся отдельно от диалога** (`invariants.json`),
**явно учитываются в рассуждениях** (блок `[system: инварианты]` + правило роли) и
**проверяются кодом** до изменения состояния или запуска инструмента.

- **жёсткий запрет — только кодом**: промт рекомендует, код запрещает; несколько нарушений
  возвращаются одновременно;
- **отказ с объяснением**: запрос, нарушающий инвариант, не выполняется молча — агент называет
  нарушенное правило, объясняет причину и предлагает допустимую альтернативу;
- **изменение инварианта — отдельная авторизованная операция**: `update_invariant(...,
  authorized=True)` требует явного подтверждения (`/invariant set <id> <текст> --yes`);
- `severity` различает жёсткий запрет (`error` — действие блокируется) и предупреждение
  (`warning` — действие выполняется с ворнингом в лог).

## Контролируемые переходы состояний (Task State Machine)

Главная идея дня (`arch_den_15.md` §1.1, канон `Задание_Д15.txt`): **жизненный цикл задачи —
это строгая машина состояний**. LLM может предлагать решения и составлять план, но отдельный
Python-код управляет жизненным циклом: у задачи есть конечный набор допустимых состояний и
список **разрешённых** переходов, а ассистент **физически не может** «перепрыгнуть» этап.

### Модель состояний (`core/state_machine.py`)

`TaskState` — конечный enum из **7 допустимых состояний** (имена — как в задании):

```python
class TaskState(str, Enum):
    NEW = "new"                         # задача создана, но ещё не начата
    PLANNING = "planning"               # идёт планирование
    PLAN_APPROVED = "plan_approved"     # план утверждён
    IMPLEMENTATION = "implementation"   # идёт реализация
    VALIDATION = "validation"           # проверка / тестирование
    DONE = "done"                       # задача завершена
    PAUSED = "paused"                   # пауза (сохраняет prev_state)
```

Любое состояние вне enum недопустимо и отклоняется ещё на входе (парсинг CLI/промта).
Соответствие 4 базовым стадиям лекции (`Суть_N3.md`, «не убирать»):

| Базовая стадия | Состояния FSM |
|---|---|
| planning | `new → planning → plan_approved` |
| execution | `implementation` |
| validation | `validation` |
| done | `done` |

### Матрица разрешённых переходов (`ALLOWED_TRANSITIONS`)

Явный список переходов — **единственный источник истины** (канон `Задание_Д15.txt`):

```python
ALLOWED_TRANSITIONS = {
    TaskState.NEW:            {TaskState.PLANNING, TaskState.PAUSED},
    TaskState.PLANNING:       {TaskState.PLAN_APPROVED, TaskState.PAUSED},
    TaskState.PLAN_APPROVED:  {TaskState.IMPLEMENTATION, TaskState.PAUSED},
    TaskState.IMPLEMENTATION: {TaskState.VALIDATION, TaskState.PAUSED},
    TaskState.VALIDATION:     {TaskState.DONE, TaskState.PAUSED},
    TaskState.DONE:           set(),        # терминальное: из done никуда не переходим
    TaskState.PAUSED:         {TaskState.NEW, TaskState.PLANNING, TaskState.PLAN_APPROVED,
                               TaskState.IMPLEMENTATION, TaskState.VALIDATION},
}

def can_transition(from_state, to_state) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())
```

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
> задания): `VALIDATION → IMPLEMENTATION` (возврат на доработку при провале валидации) —
> включается флагом `--rework`.

### Контролируемый переход (`try_transition` + `InvalidTransitionError`)

```python
def try_transition(current, proposed):
    if not can_transition(current, proposed):
        # не меняем состояние — только сигнал об ошибке
        raise InvalidTransitionError(current, proposed)
    return proposed
```

Любой переход проходит через `try_transition`. Если `can_transition` вернула `False`, переход
**не выполняется**: состояние остаётся прежним, а вызывающий код получает
`InvalidTransitionError` с текущим состоянием и списком разрешённых.

### Аудит переходов (`TransitionLog`)

Каждая попытка (и разрешённая, и отклонённая) фиксируется — требование задания «в логе/истории
остаётся запись о попытке и отказе»:

```python
@dataclass
class TransitionRecord:
    ts: str          # ISO-таймстамп
    frm: str         # состояние до
    to: str          # предлагаемое состояние
    allowed: bool    # разрешён ли переход
    reason: str = "" # причина отказа (текст InvalidTransitionError) / метка ("resume")
```

### Строгая FSM (`StateMachine`)

```python
class StateMachine:
    """Единственное место, где меняется состояние; любой переход проходит can_transition."""
    def transition(self, proposed): ...    # проверка + применение + запись в TransitionLog
    def allowed_next(self): ...            # разрешённые переходы из текущего состояния
    def pause(self): ...                   # = transition(PAUSED), сохраняет prev_state
    def resume(self): ...                  # возврат ровно в prev_state (prev_state очищается)
    def snapshot(self) -> dict: ...        # {state, prev_state, log}
    @classmethod
    def from_snapshot(cls, data): ...
```

- `pause()` доступна из любого активного состояния (`new`…`validation`), но не из `done`;
- `resume()` возвращает **ровно `prev_state`** (не «любое из списка»); попытка `resume()` не из
  `paused` → `InvalidTransitionError`;
- `snapshot()`/`from_snapshot()` — сериализация для `task_state.json`.

### Персистентность (`task_state.json`)

Снимок FSM хранится отдельно от истории диалога и от инвариантов; переживает перезапуск.
Сейв — при каждом успешном переходе и при `/exit`; лоад — при старте, при `load_state(user_id)`
и при `/task <имя>`. Битый/отсутствующий `task_state.json` не роняет приложение — задача
стартует в `new`.

```json
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
```

### Инжект состояния в промт (уровень 1 — build-prompt)

Блок `task_state` (после `invariants`, до `working`) несёт текущее состояние, разрешённые
переходы и список запретов:

```text
[task_state]
Текущее состояние задачи: implementation.
Разрешённые переходы: validation, paused.
Запрещено перепрыгивать этапы:
- нельзя перейти в implementation без plan_approved;
- нельзя перейти в done без validation.
Работай строго в рамках текущего состояния; предлагай только разрешённый следующий шаг.
```

Это помогает модели видеть ограничения, но **окончательное решение принимает `try_transition`**
(двойная защита: правило в промте + запрет в коде).

### Рабочий цикл с контролем переходов

```text
Запрос пользователя / ответ LLM
        ↓
Предложение перехода (ProposedState)
        ↓
can_transition / try_transition (Python-код)
        ↓
применить переход  ИЛИ  InvalidTransitionError → остаться + объяснить
```

Проверка выполняется **перед** любым изменением стадии задачи (перед запуском реализации,
перед фиксацией `done`, перед отправкой результата пользователю). Недопустимый переход
инструмент не запускает и состояние не меняет.

### Реакция ассистента на запрещённый переход (канон задания)

```text
Переход в «implementation» невозможен: сейчас задача в состоянии «new».

Причина: по правилам жизненного цикла этап нельзя перепрыгнуть —
реализацию нельзя начать до утверждённого плана (нужен переход new → planning → plan_approved).

Разрешённые следующие состояния: planning, paused.
Предлагаю сначала перейти в «planning».
```

Отказ обязан: (1) назвать текущее состояние, (2) назвать сработавшее правило, (3) перечислить
разрешённые переходы, (4) предложить корректный следующий шаг. Плохие реакции: молчаливое
выполнение («Хорошо, сразу реализуем») и сухой запрет («Нельзя»).

### «Корректность продолжения после паузы»

1. задача в состоянии `implementation`;
2. переход в `paused` (сохраняется `prev_state = implementation`);
3. сессия завершается / процесс перезапускается (`task_state.json` уже на диске);
4. при продолжении: загружается последнее состояние; `resume()` возвращает **ровно
   `implementation`**; `allowed_next()` остаётся тем же (`validation`, `paused`); ассистент не
   «сбрасывается» в начало и не перескакивает этапы.

```python
data = store.read_task_state(user_id, task_name)
self.fsm = StateMachine.from_snapshot(data) if data else StateMachine()
if self.fsm.state is TaskState.PAUSED:
    self.fsm.resume()      # → prev_state (implementation), prev_state очищен
```

### Пример сессии (канон задания)

```text
Вы: /plan Найди три Python-фреймворка и сравни их
[FSM] new → planning;  [FSM] planning → plan_approved;  [FSM] plan_approved → implementation
Вы: /step
[Шаг] implementation | Собрать информацию …
Вы: /transition done
[FSM] переход отклонён: Переход implementation → done запрещён.
      Разрешено из implementation: paused, validation.
Переход в «done» невозможен: сейчас задача в состоянии «implementation».
Причина: по правилам жизненного цикла этап нельзя перепрыгнуть (финал без валидации запрещён).
Разрешённые следующие состояния: paused, validation.
Предлагаю сначала перейти в «validation».
Вы: /pause
[FSM] implementation → paused   (prev_state = implementation)
Вы: /exit                       # состояние сохранено в task_state.json
… перезапуск процесса (тот же --user/--memory-dir) …
Вы: /resume
[FSM] paused → implementation   # ровно prev_state, НЕ сброс в начало
Вы: /run
[Прогон] implementation → validation → done
```

## Команды REPL

Команды верхнего уровня; у `/profile` — 6 подкоманд, у `/task` — 2 формы.

| Команда | Действие | Пункт приёмки |
|---|---|---|
| `/memory` | снимок «какие данные в каком типе памяти» (report по всем слоям) | 4 |
| `/profile` | активный профиль: `style` / `constraints` / `context` (обратно совместимо с Днём 11) | 2 |
| `/profile list` | профили пользователя (`*` default, `>` активный) | 20 |
| `/profile show <id>` | полный JSON профиля | 20 |
| `/profile use <id>` | переключить активный профиль сессии | 22 |
| `/profile new <id>` | создать профиль (мини-интервью) и активировать его | 20 |
| `/profile route <текст>` | показать решение роутера (explain), НЕ переключая | 22 |
| `/profile auto on\|off` | авто-роутинг профиля по каждому запросу | 22 |
| `/tasks` | список задач + отметка активной (`*`) | 8 |
| `/task <имя>` | переключить/создать задачу: отметка перехода + новая сессия + ссылка на источник + загрузка её `task_state.json` | 8 |
| `/task retry` | Д13: восстановление из `failed` → `planning` | 25 |
| `/invariants` | Д14: список инвариантов (id, category, severity, active) | 26–30 |
| `/invariant add <id> <category> <текст>` | Д14: добавить инвариант | 26–30 |
| `/invariant set <id> <текст> [--yes]` | Д14: изменить инвариант (требует подтверждения) | 30 |
| `/invariant on\|off <id>` | Д14: включить/выключить инвариант | 26–30 |
| `/check <действие>` | Д14: демонстрация проверки (`ProposedAction` → нарушения) | 28–29 |
| `/plan <цель>` | Д13: новая задача — `start_task()` + первый проход (planning) → execution | 23 |
| `/step` | Д13: один проход автомата + снимок (этап, шаг, ожидаемое действие) | 23 |
| `/run` | Д13: крутить автомат до `done`/`failed`/`paused` (лимит 50 проходов) | 25 |
| `/pause` | ← Д15: пауза (сохраняет `prev_state`), доступна из любого активного состояния | 35 |
| `/resume` | ← Д15: возврат **ровно в `prev_state`**, без сброса в начало | 35 |
| `/transition <state>` | ← Д15: попытка перехода (проверяется `try_transition`) | 33 |
| `/next` | ← Д15: список разрешённых переходов из текущего состояния | 32 |
| `/history` | ← Д15: журнал переходов (`allowed`/`rejected` + причина) | 33 |
| `/fsm` | ← Д15: матрица разрешённых переходов | 32 |
| `/deliver <слои>` | набор доставляемых слоёв, напр. `/deliver profile,task_state,working` | 5 |
| `/compare` | ответ с `long_term` и без него — демонстрация влияния памяти | 14 |
| `/summary` | резюме сессий текущей задачи (`sessions_resume.md`) | 12 |
| `/state` | ← УСИЛЕНА: текущее состояние + разрешённые следующие + снимок `TaskState` | 11, 31 |
| `/tokens` | локальная оценка токенов сессии + указание на CSV-журнал | 16 |
| `/cost` | стоимость обменов (локальная оценка, ₽) | 16 |
| `/help` | список команд | — |
| `/exit` | `save_state()` (+ сейв `task_state.json`) и выход (resume «с того же места») | 12, 36 |

Без активной задачи `/step`, `/run`, `/pause`, `/resume` печатают подсказку «сначала
`/plan <цель>`». `EOFError` / `KeyboardInterrupt` тоже вызывают `save_state()` — состояние
(включая `task_state.json`) не теряется. Неизвестная команда и исключения цикла логируются и
не прерывают сессию.

## Запуск

```bash
# Через обёртку (активирует venv недели AI_9, работает из любого каталога)
./run.sh                     # интерактивный REPL — спросит user_id
./run.sh --user alice        # сразу идентификация alice
./run.sh --mock              # MockClient: детерминированные ответы, ключ не нужен

# Напрямую
python Kod.py --mock --user alice

# Персонализация
./run.sh --user alice --profile chemist    # активный профиль на старте
./run.sh --user alice --profile nope       # ⚠ предупреждение → default

# Контроль переходов
./run.sh --user alice --mock --rework      # включить опциональный VALIDATION → IMPLEMENTATION

# Демонстрация дозированной доставки: один и тот же вопрос с разными слоями
./run.sh --user alice --deliver profile,task_state,working,short_term   # без долговременной
./run.sh --user alice                                                  # все слои
```

**Флаги (11 + `--rework`):** `--user <id>`, `--profile <id>`, `--deliver <слои>` (по умолчанию
все), `--mock`, `--fresh` (не восстанавливать прошлое состояние, включая `task_state.json`),
`--log` (по умолчанию `Den_log.md`), `--token-log` (по умолчанию `tokens.csv`), `--max-tokens`,
`--price-in` / `--price-out` (₽ за 1M, по умолчанию 11 / 33), `--memory-dir` (перенос хранилища —
используется тестами для изоляции), `--rework` (опциональный `VALIDATION → IMPLEMENTATION`).

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env` (`load_dotenv()`). При `--mock`,
отсутствии ключа или `API_KEY=test-key` автоматически выбирается `MockClient`. `run.desktop`
содержит абсолютные `Exec=`/`Path=` — после переноса на другой хост его нужно пересоздать.

## Агентный цикл

```
старт → DI-сборка build_agent() → идентификация user_id (--user или ввод)
      ├─ profile_repo.exists()  → load_state(): long_term → первая задача → initialized
      │                           └── + load_fsm(): есть task_state.json →
      │                               состояние/лог переходов загружены, задача продолжается
      └─ нет профиля            → интервью (style/constraints/context) → initialize_user()
                                  → дерево users/<id>/… + профиль default + «Основная_задача»
      → активный профиль: --profile <id> (несуществующий → предупреждение и default)
      → deliver: --deliver ∩ LAYER_ORDER
обмен:  сообщение → [auto_route: ProfileRouter выбирает профиль ДО сборки промта]
        → remember_message("user", "M<N>") → build_context(profile_id=active_profile)
        → PromptBuilder.build(ctx, deliver)   # в блоках invariants + task_state
        → llm.complete(messages)
        → ответ None? (без записи) : remember_message("assistant", "M<N>a")
        → токен-оценка + строка в tokens.csv
переход: /transition <s> → request_transition(): can_transition → try_transition
         → применён (лог [FSM] X → Y) ИЛИ InvalidTransitionError → отказ с объяснением
         → сейв task_state.json (состояние НЕ менялось при отказе)
пауза:  /pause  → fsm.pause(): prev_state сохранён (на любом активном состоянии)
        /resume → fsm.resume(): возврат РОВНО в prev_state — без сброса в начало
инварианты: обычное действие → ProposedAction → InvariantChecker.check
         → разрешено: выполнить; нарушено: отказ с объяснением
выход:  save_state() → working.lifecycle_summary + sessions_resume.md
        + save_fsm() (task_state.json) → resume переживает перезапуск процесса
```

LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer, retry на
HTTP 429 с задержками 2 → 4 → 8 сек, таймаут 30 сек, `choices[0].message.content`, любой сбой →
`None`) и `MockClient` (детерминированная заглушка, отражающая видимые блоки промта — ею
проверяется доставка слоёв без сети). Агент зависит только от абстракции — провайдер инжектится
на старте.

## Архитектура

```
./
├── Kod.py                       # точка входа: DI-композиция + REPL (+ команды переходов)
├── core/                        # ядро агентности
│   ├── agent.py                 # stateful-оркестратор: identify / interview / respond /
│   │                            #   switch_task / save_state + active_profile / switch_profile /
│   │                            #   auto_route + инварианты (check_invariants / propose_and_check) +
│   │                            #   FSM: load_fsm / save_fsm / request_transition / pause /
│   │                            #   resume / allowed_next / transition_log / _transition_refusal
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля по запросу
│   ├── prompt_builder.py        # BLOCK_ORDER (role→profile→invariants→task_state→…), build()
│   ├── state_machine.py         # ← Д15: TaskState (enum, 7 состояний) + ALLOWED_TRANSITIONS +
│   │                            #   can_transition + try_transition + InvalidTransitionError +
│   │                            #   TransitionRecord/TransitionLog + StateMachine
│   │                            #   (transition/pause/resume/snapshot/from_snapshot)
│   └── invariants.py            # ← Д14: Invariant + ConstraintSet + InvariantChecker + ProposedAction
├── memory/                      # модель памяти
│   ├── base.py                  # MemoryContext (+profile_id), MemoryItem, MemoryLayer (ABC), PolicyEngine (задел)
│   ├── short_term.py            # append-only, parent_id, SHORT_TERM_WINDOW = 10
│   ├── working.py               # состояние задачи (MERGE) + зеркало стадии в блоке промта
│   ├── long_term.py             # profile_ref + tasks / decisions / knowledge
│   ├── profile.py               # активный профиль: style/constraints/context + domain/triggers/skills
│   └── manager.py               # remember / recall / build_blocks / report, LAYER_ORDER
├── storage/                     # физическое хранение
│   ├── store.py                 # фасад иерархии: safe_name, ensure_*, read_*/write_*, зеркала
│   │                            #   profiles/<pid>.json + invariants_path/read/write +
│   │                            #   task_state_path / read_task_state / write_task_state
│   └── db.py                    # ProfileRepository — SQLite profiles(user_id, profile_id) + is_default, миграция
├── users/                       # рантайм-данные: profiles.db + деревья пользователей
│                                #   (+ invariants.json и task_state.json задач)
└── dev/                         # служебное пространство: миграция (migr_plan_*/migr_log), метапромты,
                                 #   тесты, отчёты, чек-лист Проверка.md
```

| Модуль | Файлы | Назначение |
|---|---|---|
| CLI / DI | `Kod.py` | REPL, флаги (11 + `--rework`), токен-учёт и CSV, журнал маршрутизации, интервью, команды переходов |
| Ядро | `core/*` | агентный цикл, строгая FSM (переходы/pause/resume), инварианты, профиль-роутер, блоки промта с бюджетом, LLM-интерфейс |
| Память | `memory/*` | контракт слоя, 4 реализации, роутер `MemoryManager`, задел `PolicyEngine` |
| Хранилище | `storage/*` | фасад канонической иерархии JSON (+ `invariants.json`, `task_state.json`), репозиторий профилей в SQLite с миграцией |

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`storage/db.py` не зависит ни от чего внутри проекта. Слои памяти и ядро ФС напрямую не
трогают — только через фасад `Store`. `StateMachine` инжектится в агента; пути знает только
`Store`, агент — нет.

## Демонстрации задания

| Что проверяем | Как посмотреть | Что видно |
|---|---|---|
| Допустимые состояния задачи | `/state`, `/fsm` | `TaskState` (7 состояний) + матрица `ALLOWED_TRANSITIONS` |
| Попытка перейти в недопустимое состояние | `/transition done` (из `implementation`) | `[FSM] переход отклонён: … запрещён. Разрешено …`; состояние **не меняется** |
| Реакция ассистента | тот же сценарий | отказ называет текущее состояние, сработавшее правило и разрешённые переходы, предлагает корректный шаг |
| «Перепрыгнуть» этап | `/transition implementation` (из `new`) | отклонено: реализацию нельзя начать до утверждённого плана |
| Аудит переходов | `/history` | журнал: `allowed=true/false` + причина (`allowed=false` при отказе) |
| Корректность продолжения после паузы | `/pause` → `/exit` → перезапуск → `/resume` → `/next` | `resume` возвращает ровно в `prev_state`; `/next` те же (`validation`, `paused`); сброса в начало нет |
| Персистентность состояния | `cat users/<id>/tasks/<task>/task_state.json` | `state` + `prev_state` + `log` на диске; переживает перезапуск процесса |
| Какие данные попадают в каждый слой | `/memory`, журнал `Den_log.md` | `[Память] profile «default» ← …`, затем `working ← …`, `long_term ← …`, `short_term ← M1 (parent=None)` |
| Как память влияет на ответы | `/compare` | два ответа на один вопрос: с `long_term` и без него + разница в токенах |
| Дозированная доставка | `/deliver profile,task_state,working` | слой `long_term` физически отсутствует и в блоках, и в тексте запроса |
| Ответы для разных профилей | `/profile use chemist` → вопрос → `/profile use economist` → тот же вопрос | разный блок профиля и разный ответ при идентичном запросе |
| Конфликт с инвариантом | `/invariant add framework.django architecture "Использовать Django"` → «перепиши API на FastAPI» | отказ с объяснением: называет `framework.django`, причину и альтернативу |

Готовый сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`.

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient` или заглушка `requests`), тестовые
данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`), рабочие `users/` не
затрагиваются. `pytest` в venv недели отсутствует, поэтому L2 идёт через собственный лёгкий
раннер `unit_runner.py` (без аргумента — все модули, с аргументом — один).

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py` | exit 0 |
| L2 | `env -u API_KEY python dev/tests_debug/unit_runner.py` | OK (9 модулей: storage, memory, llm, prompt, agent, state, person, **fsm**, **invariants**), включая усиленный `test_fsm.py` (переходы/запреты/pause/resume/персистентность) |
| L3 | `API_KEY=test-key python dev/tests_debug/smoke.py` | SMOKE OK, exit 0 (полный цикл in-process + CLI, включая переходы) |
| L4 | `API_KEY=test-key python dev/tests_debug/scenario.py` | OK (интервью, маршрутизация, дозированная доставка, влияние, resume, персонализация, конфликт инварианта, **`scenario_invalid_transition`**, **`scenario_pause_resume`**) |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | ✅ exit 0 (идемпотентен, TMP = `.tmp/acc_$`; включает проверки 31–36 — переходы и персистентность FSM) |

Человеческая версия приёмки — **36 критериев, 36/36 зелёных** — в
[`dev/Проверка.md`](dev/Проверка.md): 30 прежних (без регрессии: память + персонализация +
инварианты) + **строки 31–36 переходов**:

- 31 — у задачи явный конечный набор состояний (`TaskState`, 7 состояний);
- 32 — разрешённые переходы заданы явной матрицей (`ALLOWED_TRANSITIONS`; `/fsm`);
- 33 — переход проверяется кодом до применения; недопустимый не меняет состояние и попадает в
  `TransitionLog` (`allowed=false`);
- 34 — ассистент не перепрыгивает этап + корректная реакция (`scenario_invalid_transition`);
- 35 — пауза/возобновление не ломают FSM (`resume()` → ровно `prev_state`; `scenario_pause_resume`);
- 36 — персистентность: состояние переживает перезапуск (`task_state.json`;
  `test_resume_after_restart`).

**Живой смоук — ⏸ отложен**: требует явного согласия на живые LLM-вызовы, финал не блокирует
(FSM детерминированный, проверяется на заглушках без сети).

## Что зафиксировано в процессе создания

- **Миграция на `arch_den_15.md`** — журнал `dev/migr_log.md`: задел `state_machine.py`
  развёрнут в строгую FSM (`TaskState` / `ALLOWED_TRANSITIONS` / `try_transition` /
  `InvalidTransitionError` / `TransitionLog` / реакция на запрет), добавлены `task_state.json`,
  блок `task_state` в промте, команды `/state`, `/next`, `/transition`, `/pause`, `/resume`,
  `/history`, `/fsm`;
- **Единый источник истины переходов**: матрица `ALLOWED_TRANSITIONS` — одно место, где описано,
  что куда можно; её читают и проверка, и промт, и CLI;
- **Двойная защита**: правило «не перепрыгивай этап» и в промте (блок `task_state`), и в коде
  (`try_transition`); жёсткий запрет — только кодом («код запрещает, промт рекомендует»);
- **Пауза/возобновление без регрессии**: `paused` доступна из любого активного состояния,
  `resume()` возвращает ровно в `prev_state`; снимок FSM переживает перезапуск, разрешённые
  переходы после возобновления не меняются;
- **Коррекция naming** (`dev/PLAN_naming.md`, наследие Дня 12): признак дня удалён из имён и
  внутренних путей — проект копируется в следующие дни без переименований;
- **Уроки прошлых дней** (`dev/logs_reports/errors/`): живой вызов LLM из теста (патч
  `requests.post` + `env -u API_KEY`), инцидент безопасности с `bash -x` и `API_KEY`
  (вывод переменных из чекера убран), загрязнение корня при смоуке (флаги `--log/--token-log`
  в `.tmp/`);
- **Метапромты дня** фиксировали контракты **до** написания кода; в цикле отладки сигнатуры
  не правились.

## Файлы проекта

| Файл / каталог | Назначение |
|---|---|
| `Kod.py` | Точка входа: DI-композиция `build_agent()`, REPL, токен-учёт, интервью, команды переходов |
| `core/` | Ядро: `agent.py`, `llm_client.py`, `profile_router.py`, `prompt_builder.py`, `state_machine.py`, `invariants.py` |
| `memory/` | Модель памяти: `base.py`, 4 слоя, `manager.py` |
| `storage/` | Хранилище: `store.py` (фасад иерархии), `db.py` (SQLite профилей + миграция) |
| `users/` | Рантайм-данные: `profiles.db` + `profile.json`, `profiles/<pid>.json`, `long_term_memory.json`, `invariants.json`, `task_state.json`, `working_memory.json`, `sessions_resume.md`, `session.json` |
| `run.sh` / `run.desktop` | Запускающий скрипт (+x) и ярлык (`.desktop` привязан к хосту — после переноса пересоздать) |
| `Den_log.md` | Журнал маршрутизации памяти и переходов: «какой слой ← что → куда» + строки `[FSM] …` |
| `tokens.csv` | CSV-журнал токенов и стоимости обменов |
| `README.md` | Текстовая часть результата — описание памяти, персонализации, инвариантов и **контролируемых переходов состояний** |
| `arch_den_15.md` | Целевая архитектура проекта `den_15` (контролируемые переходы состояний) |
| `Задание_Д15.txt` | Постановка задачи куратора (контролируемые переходы состояний) — не изменяется |
| `dev/migr_plan.md` + `migr_plan_0..N.md` | План-эталон и рабочие планы миграции на `arch_den_15.md` (конец этапа — автоматический гейт) |
| `dev/migr_log.md` | Журнал миграции: записи этапов + итоговая запись «МИГРАЦИЯ ЗАВЕРШЕНА» |
| `dev/Проверка.md` | Чек-лист приёмки: 36 критериев с командой проверки по каждому |
| `dev/tests_debug/` | L2 (`unit_runner.py` + `unit/` — 9 модулей), L3 (`smoke.py`), L4 (`scenario.py` — сценарии, включая `scenario_invalid_transition`, `scenario_pause_resume`), гейт (`check_acceptance.sh`), `scenario/scen_1.md`, `.tmp/` |
| `dev/logs_reports/` | `stages/`, `errors/` (карточки ошибок), `run_log.md` |

## Общее с Днями 6–11 (перенесённые уроки)

- API: RouterAI (OpenAI-совместимый), ключ в `.env` (переменная `API_KEY`), модель
  `stepfun/step-3.5-flash` не менять;
- Retry при HTTP 429: до 3 повторов, задержка 2 → 4 → 8 сек; таймаут 30 сек; сетевые и
  форматные сбои → `None`, цикл чата не прерывается;
- Устойчивость: `sys.stdin.reconfigure(encoding='utf-8', errors='replace')` +
  `sys.stdout.reconfigure(errors='replace')`, `try: import readline`, все пути через `BASE_DIR`;
- Токен-учёт: локальная оценка `~1 токен на 4 символа` с явной оговоркой, что авторитет —
  `usage` живого API; CSV-журнал стоимости;
- Зависимости: только `requests`, `python-dotenv` и стандартная библиотека (`sqlite3` из stdlib).

## Известные шероховатости и заделы

**Заделы по замыслу (программа следующих дней недели 3):**

- `PolicyEngine` и поле `visibility` — точка расширения фильтрации;
- `parent_id` сообщений — задел ветвления диалога (наследие Дня 10), самого ветвления ещё нет;
- `skills[]` профиля подмешиваются в промт декларативно — движок оркестрации скиллов (реальное
  исполнение пайплайна) — следующие дни;
- полная изоляция стадий (уровень 2 — контейнеры/отдельные сессии) — задел;
- `--rework` (`VALIDATION → IMPLEMENTATION`) по умолчанию выключен — включается флагом.

**Расхождения spec/кода (на поведение не влияют):**

- параметр `budget` у `PromptBuilder.build()` в рабочем пути может не передаваться — бюджет
  обрезания проверен юнит-тестом;
- окно краткосрочной памяти (`10`) продублировано: `SHORT_TERM_WINDOW` в `memory/short_term.py`
  и литерал `[-10:]` в `core/agent.py` — риск рассинхронизации;
- неиспользуемые импорты и объявления (`ROLES` и т. п.);
- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми; в `.tmp/`
  накапливаются каталоги прошлых прогонов (в `.gitignore`, не удаляются автоматически);
- изменения миграции не закоммичены (коммит — только по явной команде пользователя).

## Результат

- **Ассистент с контролируемым жизненным циклом задачи**: конечный набор допустимых состояний
  (`TaskState`, 7 значений) и явная матрица разрешённых переходов (`ALLOWED_TRANSITIONS` —
  единый источник истины);
- **Блокировка «перепрыгивания» этапа на уровне кода**: любой переход проходит
  `try_transition`; недопустимый бросает `InvalidTransitionError`, состояние **не меняется**,
  а попытка попадает в `TransitionLog` (`allowed=false` + причина);
- **Корректная реакция ассистента**: при попытке запрещённого перехода агент остаётся в текущем
  состоянии, называет сработавшее правило и предлагает корректную последовательность
  (`planning`, а не `implementation`);
- **Корректное продолжение после паузы**: `paused` доступна из любого активного состояния,
  `resume()` возвращает ровно в `prev_state`; снимок FSM (`task_state.json`) переживает
  перезапуск, разрешённые переходы после возобновления не меняются, сброса в начало нет;
- **Персистентность и аудит**: состояние и журнал переходов хранятся отдельно от истории
  диалога и от инвариантов; очистка истории не сбрасывает жизненный цикл;
- **Двойная защита**: правило «не перепрыгивай этап» и в промте (блок `task_state`), и в коде
  (`try_transition`) — «код запрещает, промт рекомендует»;
- **Персонализированный агент** (День 12, без регрессии): несколько профилей-«призм», роутер с
  авто-режимом, пайплайн скиллов — «один request → разные response»;
- **Инварианты** (День 14, без регрессии): неизменяемые правила отдельно от диалога, отказ с
  объяснением при конфликте, изменение — отдельная авторизованная операция;
- **4 типа памяти** — разные классы, разные хранилища, разные читатели; память не зависит от
  активного профиля;
- **Явная маршрутизация записи**: только через `remember(layer, ...)`, с логом «что куда легло»;
- **Дозированная доставка**: `deliver` как параметр (`--deliver`, `/deliver`) + токен-бюджет;
- **Каноническая иерархия хранения** с профилями в SQLite (зеркала — JSON) и фасадом `Store`,
  который не даёт слоям знать про пути;
- **Naming без признака дня**: проект копируется в следующие дни без переименований;
- **Проверяемость**: `/state`, `/next`, `/transition`, `/history`, `/fsm` + тестовый контур
  L2/L3/L4 без живого ключа, гейт и **36/36 критериев приёмки**;
- **Заделы недели**: `PolicyEngine`, `parent_id` для ветвления, исполнение пайплайна скиллов,
  изоляция стадий уровня 2.

## Ручная проверка

Пошаговый чек-лист приёмки с отметками — в файле [`dev/Проверка.md`](dev/Проверка.md):
**36 критериев** с конкретной командой проверки по каждому (комплектность и сборка, четыре слоя,
иерархия хранилища, явная маршрутизация, дозированная доставка, идентификация и интервью, задачи
и переходы, промт блоками, LLM за интерфейсом, state machine, resume, неизменяемые сообщения,
демонстрации, текстовое описание, уроки Дня 10, тесты без ключа, задел инвариантов, расположение
чек-листа, + строки 20–22 персонализации, + строки 23–25 состояния задачи, + строки 26–30
инвариантов, + **строки 31–36 контролируемых переходов**).
Машиночитаемый дубль — `dev/tests_debug/check_acceptance.sh` (идемпотентен).
Сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`.
