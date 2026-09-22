# День 15 — Контролируемые переходы состояний (Controlled State Transitions)

> **Неделя 3** — «Память и состояние агента: переход от stateless к stateful».
> День 15 — поверх явной модели памяти (День 11), персонализации (День 12), формализованного
> состояния задачи (День 13) и слоя инвариантов (День 14) автомат задачи модернизируется до
> **строгой машины состояний с контролируемыми переходами**: явный набор допустимых состояний
> (8), явная карта разрешённых переходов (`ALLOWED_TRANSITIONS`, whitelist), программный
> запрет «перепрыгивания» этапов (`try_transition` → `InvalidTransitionError`), журнал попыток
> и отказов (`transition_log`) и корректное продолжение после паузы.
> Формула ценности — **недопустимый переход не выполняется молча**: попытка фиксируется в
> журнале, состояние остаётся прежним, ассистент называет сработавшее правило
> («нельзя делать реализацию до утверждённого плана») и предлагает корректный следующий шаг
> («сначала утвердите план — /approve»).
> Формат результата — Код / Текст. Целевая архитектура — `arch_den_15.md`.

## Суть проекта

CLI-агент (RouterAI, модель `stepfun/step-3.5-flash`) с **явной моделью памяти**,
**настраиваемой персонализацией**, **формализованным состоянием задачи**, **набором
неизменяемых правил (инвариантов)** и **контролируемым жизненным циклом задачи**. Память
разделена на четыре физически отдельных слоя (краткосрочная / рабочая / долговременная /
профиль), запись идёт только явным вызовом `memory.remember(layer, ...)`, а набор слоёв,
попадающих в промт, — параметр `deliver: set[str]` (дозированная доставка).

Поверх модели памяти пользователь настраивает агента под себя и под задачу: на одного `user_id`
заводится **несколько профилей**-«призм» (пример куратора: Химик / Психолог / Экономист для
постов в ТГ; агент для покупок → сборка корзины). **Общий профиль-роутер** детерминированно
выбирает конкретный профиль по тексту запроса, **профиль = упорядоченный пайплайн скиллов**,
чьи инструкции подмешиваются в промт. Активный профиль привязан к сессии и подключён к каждому
запросу — один и тот же запрос при разных профилях даёт разный состав промта и разный ответ.

Сверху — **строгая машина состояний задачи** (`core/state_machine.py`): LLM составляет план и
наполняет шаги, но жизненным циклом управляет Python-код по **явной карте переходов**
(whitelist: разрешено только то, что перечислено; всё остальное запрещено по умолчанию).
Утверждение плана — **отдельная стадия** (`plan_approved`): «нельзя делать реализацию до
утверждённого плана» реализуется не текстом, а топологией графа — из `planning` нет дуги в
`implementation`. Попытка недопустимого перехода (`/goto implementation` из `planning`)
отклоняется кодом: состояние не меняется, попытка пишется в `transition_log`, ассистент
называет правило и корректный следующий шаг.

Вершина — **слой инвариантов** (`core/invariants.py`): `Invariant` + `ConstraintSet` (набор
правил) + `InvariantChecker` (программная проверка действия). Инвариант — условие, которое
должно сохраняться во всех допустимых состояниях системы; действие, нарушающее его,
**не выполняется**, а пользователю выдаётся **отказ с объяснением**. Переходы и инварианты —
**разные сущности контроля**: `state_machine` проверяет переходы (этапы жизненного цикла),
`InvariantChecker` — действия (технологии, зависимости, схема БД); оба работают по принципу
«код запрещает, промт рекомендует», но не сливаются.

Ключевая идея недели: **история ≠ состояние, состояние ≠ правила, правила ≠ карта переходов**.
Краткосрочная — append-only лог с `parent_id`; рабочая — пересчитываемое *состояние* памяти
задачи; долговременная — устойчивые сведения уровня пользователя; профиль — отдельная
сущность в SQLite; `task_state.json` — формализованное состояние **жизненного цикла**
(+ `transition_log`); `invariants.json` — **неизменяемые правила**. Шесть разных сущностей,
разные файлы.

## Что нового относительно Дня 14

- **`TaskStage` — 8 состояний** (было 6): 4 базовых этапа канона недели
  (`planning → execution → validation → done`) **детализируются**, а не заменяются:
  `execution` расщепляется на `plan_approved + implementation`, добавляется входная стадия
  `new`; расширения дня 13 (`paused`/`failed`) сохраняются. Канон имён — из задания:
  `new`, `planning`, `plan_approved`, `implementation`, `validation`, `done`, `paused`,
  `failed`;
- **Явная карта `ALLOWED_TRANSITIONS`** (матрица «из → во», whitelist): переход существует
  только если он есть в карте; из `planning` **нет** дуги в `implementation`; в `done` —
  только из `validation`; `paused`/`done` — пустые множества; `failed → {planning}`;
- **API контроля перехода** (имена из задания): `can_transition(from, to) -> bool` и
  `try_transition(state, proposed) -> TaskState` — единственная точка смены этапа;
  недопустимый переход → `InvalidTransitionError(current, proposed)` (сообщение объясняет
  правило и список разрешённых), **состояние не меняется**, попытка логируется
  (`allowed=False`); прежняя `transition()` сохранена как обёртка обратной совместимости;
- **Утверждение плана — отдельная стадия**: `/plan <цель>` строит план и **останавливается**
  в `planning` (`expected_action = «утвердить план (/approve)»`); `/approve` — новая
  идемпотентная команда (`planning → plan_approved`); `/run` из `planning` **не может
  перепрыгнуть** утверждение — проходы автомата останавливаются, контрольный пункт проходит
  только человек; пересборка плана (`plan_approved → planning`) разрешена;
- **`REFUSAL_RULES` + `refusal_text()`** — детерминированные тексты отказов (без LLM):
  правило + корректный следующий шаг («Нельзя делать реализацию до утверждённого плана.
  Сначала утвердите план: /approve»; «Нельзя делать финал без валидации…»; терминальная
  `done`; из паузы — только `/resume`);
- **Журнал переходов `transition_log`** — новое поле `TaskState` (10-е): append-only записи
  `{from, to, allowed, reason, at}` при **каждой** попытке (успех и отказ); переживает
  перезапуск вместе со снимком; `/transitions` показывает карту + журнал + счётчик отказов;
- **3 новые команды REPL**: `/approve`, `/goto <этап>` (демо контроля: недопустимый → отказ
  с правилом, состояние не меняется), `/transitions`; `/state` расширен (разрешённые
  переходы из текущей стадии + счётчик отказов); `/plan` адаптирован под новый поток;
- **Миграция снимков дней 13/14**: `"stage": "execution"` → `implementation` при загрузке
  (`STAGE_ALIASES`); снимки без `transition_log` → `[]`; битый/отсутствующий файл → задача
  стартует с `NEW`; зеркало `current_state` в `working_memory.json` синхронно;
- **Пауза — не лазейка**: из `paused` возврат **только** в `previous_stage` (прямые
  `paused → implementation` запрещены — иначе пауза обошла бы утверждение плана или
  валидацию); `pause_task` разрешена на 5 рабочих стадиях (из `done`/`failed` — отказ);
- **Тестовый контур расширен**: L2 — `test_transitions.py` (14 тестов канона задания),
  `test_state.py`/`test_fsm.py` переписаны под 8 состояний → **91 OK**; L4 —
  `scenario_controlled_transitions` (9 сценариев); гейт — **15 проверок**; приёмка —
  **35 критериев** (30 прежних + 31–35);
- **Наследие дней 11–14 без регрессии**: модель памяти (4 слоя), персонализация
  (мультипрофиль + роутер), инварианты, LLM-клиент — контракты не тронуты.

## Наследие Дней 11–12 (память и персонализация)

- **Несколько профилей на пользователя**: схема SQLite
  `profiles(user_id, profile_id, profile_json, is_default, updated_at)` с PK `(user_id, profile_id)`
  вместо одного профиля на `user_id`; первый профиль автоматически становится дефолтным;
- **Миграция старой схемы**: БД Дня 11 (`user_id PRIMARY KEY`) переносится при открытии одной
  транзакцией (`PRAGMA table_info` → `RENAME` → строки как `profile_id='default'`, `is_default=1`)
  — данные не теряются;
- **Зеркала всех профилей**: `users/<id>/profiles/<pid>.json`; `users/<id>/profile.json` остаётся
  зеркалом `default` (обратная совместимость);
- **Расширенная модель профиля**: к `style`/`constraints`/`context` добавлены `profile_id`,
  `name`, `domain`, `triggers[]`, `skills[]` — все новые поля опциональны, пустой профиль работает
  как в Дне 11;
- **`core/profile_router.py`**: `ProfileRouter.route()` / `explain()` — детерминированный выбор
  профиля без LLM;
- **Активный профиль сессии**: `Agent.active_profile`, `switch_profile()`, `auto_route`; при
  `auto_route` роутер отрабатывает **до** сборки промта;
- **Семейство команд `/profile`**: `list` / `show <id>` / `use <id>` / `new <id>` /
  `route <текст>` / `auto on|off`;
- **Флаг `--profile <id>`**: активный профиль на старте; несуществующий → предупреждение и
  `default`.

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
    ├── invariants.json          # ConstraintSet (неизменяемые правила задачи, День 14)
    ├── task_state.json          # снимок TaskState (+ transition_log, День 15)
    ├── working_memory.json      # пересчитываемое состояние задачи (+ current_state — зеркало стадии)
    ├── sessions_resume.md       # резюме сессий задачи (блок summary в промте)
    └── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
        └── session.json         # краткосрочная память: сообщения с parent_id
```

Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — формализованное состояние
**жизненного цикла** (включая журнал переходов); `invariants.json` — **неизменяемые правила**.
Четыре разные сущности, четыре файла. **Очистка истории диалога не сбрасывает состояние,
не удаляет инварианты и не трогает журнал переходов** (разные файлы).

База профилей — `users/profiles.db` (общая для всех пользователей).
Все пути знает только `storage/store.py` (`safe_name`, `ensure_user/task/session`,
`read_json`/`write_json` с каноническими дефолтами, `task_state_path`/`read_task_state`/
`write_task_state` с миграцией `"execution"` → `implementation`,
`invariants_path`/`read/write_invariants`).
Битый или отсутствующий файл не роняет приложение — чтение всегда возвращает схему по умолчанию;
при недоступной БД `load_profile`/`list_profiles` откатываются на зеркала `profiles/` →
`profile.json`.

### Сборка промта (явные блоки + дозированная доставка + бюджет)

```
[system: роль] → [system: profile] → [system: invariants] → [system: long_term] →
[system: working] → [system: summary, опц.] → [messages: short_term (окно 10)] →
[user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER = ("role", "profile", "invariants", "long_term", "working", "summary",
  "short_term", "current")`;
- доставляемое подмножество блоков задаётся каноническим набором
  `DELIVERABLE = ("profile", "invariants", "long_term", "working", "summary",
  "short_term")` из `core/prompt_builder.py` (`role`/`current` — всегда, неуправляемы);
  `--deliver`/`/deliver` пересекаются с `DELIVERABLE` (не с `LAYER_ORDER` — тот
  задаёт порядок **слоёв памяти**), поэтому `summary` достижим из CLI
  (`--deliver profile,summary`);
- слои добавляются system-блоками с заголовком `[<имя>]` **только если имя есть в `deliver`**;
- `short_term` идёт отдельными сообщениями `{role, content}`, а не склеенным текстом;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; роль и запрос не
  урезаются никогда; бюджет передаётся в рабочем пути (`Agent.prompt_budget` ← флаг
  `--budget`, по умолчанию `None` — обрезание выключено);
- «резерв» — это место под ответ модели (лимит бюджета), а не сообщение в запросе.

## Персонализация

Поверх модели памяти — **несколько профилей на пользователя** (`arch_den_12.md` §2.3–2.7).
Профиль — «призма» под домен/задачу: он определяет стиль, ограничения, контекст, доменную
область и порядок скиллов. Активный профиль привязан к сессии и входит в каждый промт, поэтому
один и тот же запрос даёт разные ответы.

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

Общий профиль-роутер выбирает конкретный профиль по тексту запроса — детерминированно, без LLM:
**+2** за вхождение каждого триггера (регистронезависимо), **+1** за вхождение `domain`;
победитель = максимум (>0); ничья или ноль → `None` (остаёмся на текущем/дефолтном). Решение
логируется («[Роутер] запрос → профиль chemist (счёт 5)»), разбор по каждому кандидату показывает
`/profile route <текст>`. Режим `/profile auto on` запускает роутер на каждый запрос **до** сборки
промта.

### Блок активного профиля в промте

```
Профиль: Химик (chemist)      ← первой строкой
Имя: Химик
Стиль: answers: строго по формулам
Ограничения: …
Контекст: …
Пайплайн скиллов:
1. spec: составь спеку ответа
2. review: проверь факты по домену
Домен: химия
```

Порядок блоков промта не меняется — активный профиль подставляется в блок `profile`. Два разных
профиля на один запрос дают разный состав промта и разный ответ
(`test_person.py::test_two_profiles_different_answers`,
`scenario.py::scenario_personalization`).

## Контролируемые переходы состояний (День 15)

Главная идея Дня 15 (канон `Задание_Д15.txt`, `arch_den_15.md` §1): **жизненный цикл задачи —
строгая машина состояний**. Чёткий список допустимых состояний и разрешённых переходов между
ними; ассистент **физически не может «перепрыгнуть» этап** — запрет работает на уровне кода,
а не только текста. Даже если пользователь просит «сразу к реализации» — код отклоняет попытку,
состояние не меняется, ассистент объясняет правило и предлагает корректную последовательность.

### Модель состояний (`TaskStage` — 8)

4 базовых этапа канона недели (`planning → execution → validation → done`, «не убирать»)
**детализируются**, а не заменяются: `execution` расщепляется на `plan_approved +
implementation`, добавляется входная стадия `new`; расширения дня 13 (`paused`/`failed`)
сохраняются. Любое состояние вне набора — недопустимое.

```python
class TaskStage(Enum):
    NEW = "new"                      # задача создана, но ещё не начата
    PLANNING = "planning"            # план строится/построен, не утверждён
    PLAN_APPROVED = "plan_approved"  # план утверждён пользователем (/approve)
    IMPLEMENTATION = "implementation"  # идёт реализация (бывший execution)
    VALIDATION = "validation"        # проверка/тестирование
    DONE = "done"                    # задача завершена (терминальная)
    PAUSED = "paused"                # пауза (возврат в previous_stage)
    FAILED = "failed"                # ошибка (восстановление — /task retry)
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
| `transition_log` | `list[dict]` | ← День 15: журнал переходов (успехи + отказы) |

Семантика ожидаемых действий: `new` → «сформировать план (/plan <цель>)»; `planning` →
«утвердить план (/approve)»; `plan_approved` → «начать реализацию (/step или /run)»;
`implementation` → текст текущего шага; `validation` → «провести валидацию»; `done` → `None`;
`failed` → «восстановить задачу (/task retry)».

### Карта переходов (whitelist)

```python
ALLOWED_TRANSITIONS: dict[TaskStage, set[TaskStage]] = {
    NEW:            {PLANNING, PAUSED, FAILED},
    PLANNING:       {PLAN_APPROVED, PAUSED, FAILED},          # НЕТ implementation
    PLAN_APPROVED:  {IMPLEMENTATION, PLANNING, PAUSED, FAILED},  # PLANNING — пересборка
    IMPLEMENTATION: {VALIDATION, PLANNING, PAUSED, FAILED},
    VALIDATION:     {DONE, IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    PAUSED:         set(),        # выход только через resume_task() → previous_stage
    DONE:           set(),        # терминальная
    FAILED:         {PLANNING},   # восстановление — явный /task retry
}
```

Запреты задания реализуются **отсутствием дуги в графе** (не `if`-ами):

| Запрет задания | Дуги нет | Следствие |
|---|---|---|
| «нельзя делать реализацию до утверждённого плана» | `new → implementation`, `planning → implementation` | единственный путь в реализацию — через `plan_approved` |
| «нельзя делать финал без валидации» | `planning → done`, `plan_approved → done`, `implementation → done` | единственный путь в `done` — через `validation` |
| «нельзя перепрыгнуть этап» (общее) | любые дуги вне карты | `try_transition` → `InvalidTransitionError`, состояние не меняется |
| пауза — не обход контроля | `paused → implementation`, `paused → done`, … | из `paused` только `resume_task()` → `previous_stage` |

### API контроля (имена из задания)

```python
can_transition(from_state, to_state) -> bool   # единственный источник истины — карта

try_transition(state, proposed) -> TaskState    # единственная точка смены этапа:
    # недопустимый → InvalidTransitionError, состояние НЕ меняется,
    # попытка пишется в transition_log (allowed=False);
    # допустимый → меняет stage + запись (allowed=True)

class InvalidTransitionError(Exception):
    # сообщение объясняет: переход X → Y запрещён; разрешено из X: […]
```

Прежняя `transition(state, target) -> bool` сохранена как обёртка над `try_transition`
(ловит исключение, ворнинг в лог, `False`) — обратная совместимость callers дней 13/14.

### Утверждение плана — отдельный контрольный пункт

Ключевое изменение потока дня 13: `/plan` **больше не ведёт сразу в реализацию**.

```text
/plan <цель>   → new → planning: executor.plan() строит steps[]
                 → автомат ОСТАНАВЛИВАЕТСЯ в planning (план построен, не утверждён)
/approve       → planning → plan_approved (переход только по явной команде человека)
/step | /run   → plan_approved → implementation: выполнение шагов (current_step)
                 шаги кончились → validation → validator → done | failed
```

- `/approve` — идемпотентная команда (как `/pause`/`/resume`): из `planning` утверждает план;
  из `plan_approved` — «план уже утверждён (можно /step или /run)»; из `new` — «плана ещё
  нет — сначала постройте его: /plan <цель>»; из `implementation` — «план уже утверждён —
  идёт implementation»;
- `/run` из `planning` **не может перепрыгнуть утверждение**: проходы останавливаются
  («план ожидает утверждения (/approve)»);
- пересборка плана: `plan_approved → planning` разрешён (пользователь передумал) —
  `/plan <новая цель>` перестраивает `steps[]`, снова требуется `/approve`;
- `retry_task()` (`failed → planning`) сохраняет семантику дня 13: очистка
  `steps/results/error`, новая сборка плана, снова утверждение.

### Отказ с объяснением (реакция ассистента)

Шаблоны отказов — `REFUSAL_RULES` в `state_machine.py` (детерминированно, без LLM):
правило → текст с корректным следующим шагом. Пары без специального правила — общий шаблон
по `InvalidTransitionError` (список разрешённых из текущей стадии); терминальная `done` и
пауза — свои объяснения.

```text
Вы: /goto implementation          # стадия planning
[Автомат] Попытка перехода planning → implementation: ОТКАЗАНО
[Автомат] Правило: Нельзя делать реализацию до утверждённого плана. Сначала утвердите план: /approve
[Автомат] Состояние не изменено: planning
```

Состояние **фактически не меняется** (проверяемо `/state` до и после), в журнале остаётся
запись о попытке и отказе. «Нельзя» без объяснения — плохая реакция: отказ называет (1) какой
переход попытался выполнить пользователь, (2) какое правило сработало, (3) корректный
следующий шаг.

### Журнал переходов (`transition_log`)

Запись — при **каждой** попытке перехода (успешной и отклонённой); журнал append-only,
переживает перезапуск вместе со снимком; `/transitions` показывает карту + журнал + счётчик
отказов.

```json
{
  "task_id": "Тестовая_цель",
  "stage": "planning",
  "steps": ["Собрать данные", "Обработать данные", "Проверить результат"],
  "expected_action": "утвердить план (/approve)",
  "transition_log": [
    {"from": "new", "to": "planning", "allowed": true, "reason": "", "at": "2026-09-22 05:44:44"},
    {"from": "planning", "to": "implementation", "allowed": false,
     "reason": "Нельзя делать реализацию до утверждённого плана. Сначала утвердите план: /approve",
     "at": "2026-09-22 05:44:44"}
  ]
}
```

### Персистентность и миграция снимков

Сейв — после **каждого** перехода/шага и при `/exit` (а также `EOFError`/
`KeyboardInterrupt`); лоад — при старте, `load_state(user_id)` и `/task <имя>`. Плюс миграция:

- снимок дней 13/14 со `"stage": "execution"` → `IMPLEMENTATION` (алиас `STAGE_ALIASES`
  в `TaskState.from_dict`);
- снимки без `transition_log` → `[]`; без `stage` → `NEW`;
- битый/отсутствующий `task_state.json` не роняет приложение — задача стартует с `NEW`;
- `--fresh` игнорирует снимок;
- зеркало `current_state` в `working_memory.json` синхронизируется с новым именем стадии.

### Пауза и продолжение (корректность после паузы)

Сценарий проверки из задания: `implementation → paused` → перезапуск процесса → продолжение
загружает `implementation`, доступные переходы те же, агент не «сбрасывается» в начало и не
перескакивает этапы.

- `pause_task()` — идемпотентная функция (не через `transition`): сохраняет `previous_stage`,
  ставит `stage = PAUSED`; разрешена из `NEW`/`PLANNING`/`PLAN_APPROVED`/`IMPLEMENTATION`/
  `VALIDATION` (из `DONE`/`FAILED` — отказ с записью `allowed=False`);
- `resume_task()` — возврат в `previous_stage` (fallback `IMPLEMENTATION`), **не трогая**
  `current_step`/`expected_action`/`steps`/`results`; после перезапуска процесса
  `load_task_state()` восстанавливает снимок, включая `previous_stage`;
- **пауза не меняет топологию**: из `paused` нельзя попасть в `implementation`, минуя
  `plan_approved` — возврат только в то состояние, где были;
- «продолжение без повторных объяснений» (день 13): план не перестраивается, выполненные шаги
  не повторяются, задача не переспрашивается.

### Инжект стейта в промт

Порядок блоков не меняется (`BLOCK_ORDER`); состояние входит в блок `working`:

```text
[working]
…
Этап: plan_approved (план утверждён, шаг 0/3)
Ожидаемое действие: начать реализацию (/step или /run)
Пауза (вернуться к: implementation)   ← только при stage = paused
Ошибка: …                             ← только при заполненном error
Стадия задачи: plan_approved          ← зеркало (обратная совместимость)
```

В роль (`[system: роль]`) добавлено правило двойной защиты: **«работай в рамках текущего этапа
задачи, не перепрыгивай этапы; переходы контролирует код»**. LLM видит стадию и
«отождествляет себя с ней», а код не даёт выйти за рамки разрешённых переходов — та же двойная
защита, что у инвариантов дня 14.

### Пример сессии (канон задания)

```text
Вы: /plan Сделать REST API на Django
[Автомат] план построен (3 шагов), ожидает утверждения (/approve)
Вы: /goto implementation
[Автомат] Попытка перехода planning → implementation: ОТКАЗАНО
[Автомат] Правило: Нельзя делать реализацию до утверждённого плана. Сначала утвердите план: /approve
[Автомат] Состояние не изменено: planning
Вы: /approve
[Автомат] planning → plan_approved: план утверждён
Вы: /run
[Прогон] Этап: done | Шаг: 3/3 …  (results = 3, без дублей; validation пройдена)
Вы: /goto new
[Автомат] Попытка перехода done → new: ОТКАЗАНО   # терминальная стадия
```

## Инварианты и ограничения состояния (День 14, без регрессии)

Слой **неизменяемых правил** поверх памяти, персонализации и автомата: агент не имеет
права нарушать заданные инварианты. Главная идея дня 14: **инвариант — условие, которое должно
сохраняться во всех допустимых состояниях; переход, нарушающий его, должен быть запрещён**.
Недостаточно добавить правила в системный промт — перед выполнением действия запускается
**отдельная Python-проверка** («код запрещает, промт рекомендует»).

| Сущность | Назначение |
|---|---|
| `Invariant` | одно правило: `id`, `description`, `category`, `severity`, `active` |
| `ConstraintSet` | набор правил — **отдельная сущность** (не память, не профиль, не диалог) |
| `ProposedAction` | предлагаемое действие (`technology`, `adds_dependency`, `changes_database_schema`, `language`) |
| `InvariantChecker` (ABC) | интерфейс проверки: `check()` (блокирующие) + `warnings()` (`severity="warning"`) |
| `RuleBasedChecker` | детерминированная реализация: правила по id-неймспейсу, без вызовов LLM |
| `update_invariant` | изменение правила — только авторизованной операцией (`authorized=True`) |

Хранение — `users/<id>/tasks/<task>/invariants.json`, **отдельно от диалога**; очистка истории
не удаляет набор. Блок `[system: invariants]` входит в промт (после профиля, до рабочей
памяти) и участвует в дозированной доставке. При нарушении инструмент **не вызывается**, а
пользователю выдаётся отказ: (1) какое действие, (2) какой инвариант нарушен, (3) почему
обязателен, (4) допустимая альтернатива. Изменение правила — `/invariant set <id> <текст>
--yes` (без `--yes` — `PermissionError`).

**Переходы и инварианты — разные сущности контроля**: `state_machine` проверяет переходы
(этапы), `InvariantChecker` — действия; разные модели, разные проверки, разные отказы.

## Команды REPL

23 команды верхнего уровня; у `/profile` — 6 подкоманд, у `/invariant` — 3 формы
(`add` / `set` / `on|off`), у `/task` — форма `retry` (32 формы в таблице).

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
| `/task <имя>` | переключить/создать задачу + загрузка её `task_state.json` | 8 |
| `/task retry` | ← Д13: восстановление из `failed` → `planning` (steps/results/error очищены, снова `/approve`) | 25 |
| `/plan <цель>` | ← ИЗМЕНЕНО (Д15): `new → planning`, план строится и **ожидает утверждения** (не ведёт сразу в реализацию) | 23, 31 |
| `/approve` | ← НОВОЕ (Д15): утвердить план (`planning → plan_approved`); из других стадий — отказ с объяснением | 31, 33 |
| `/goto <этап>` | ← НОВОЕ (Д15): попытка явного перехода (демо контроля: недопустимый → отказ с правилом, состояние не меняется; без аргумента — список стадий) | 33, 34 |
| `/transitions` | ← НОВОЕ (Д15): карта `ALLOWED_TRANSITIONS` + журнал `transition_log` + счётчик отказов | 32 |
| `/step` | один проход автомата (`plan_approved → implementation`: первый шаг; далее шаги; шаги кончились → validation) | 23 |
| `/run` | крутить автомат до `done`/`failed`/`paused` (лимит 50 проходов); из `planning` — останавливается (утверждение — только человек) | 25 |
| `/pause` | пауза на любой рабочей стадии (`previous_stage` сохраняется; из `done`/`failed` — отказ) | 24 |
| `/resume` | продолжение с того же этапа и шага, без повторных объяснений | 24, 35 |
| `/deliver <слои>` | набор доставляемых слоёв, напр. `/deliver profile,working` | 5 |
| `/compare` | ответ с `long_term` и без него — демонстрация влияния памяти | 14 |
| `/summary` | резюме сессий текущей задачи (`sessions_resume.md`) | 12 |
| `/state` | ← РАСШИРЕНО (Д15): снимок `TaskState` + разрешённые переходы из текущей стадии + счётчик отказов в журнале + карта | 11, 23, 32 |
| `/invariants` | список инвариантов задачи (`on/off`, id, category, severity, description) | 26 |
| `/invariant add <id> <category> <текст>` | добавить инвариант (сейв `invariants.json`) | 26 |
| `/invariant set <id> <текст> [--yes]` | изменить инвариант — без `--yes` требует подтверждения | 30 |
| `/invariant on\|off <id>` | включить/выключить инвариант | 28 |
| `/check <действие>` | прогнать `ProposedAction` через `InvariantChecker` (демонстрация, без исполнения) | 28 |
| `/tokens` | локальная оценка токенов сессии + указание на CSV-журнал | 16 |
| `/cost` | стоимость обменов (локальная оценка, ₽) | 16 |
| `/help` | список команд | — |
| `/exit` | `save_state()` (+ сейв `task_state.json` с `transition_log`) и выход | 12, 25 |

Без активной задачи `/step`, `/run`, `/pause`, `/resume`, `/approve`, `/goto` печатают
подсказку «сначала `/plan <цель>`». `EOFError` / `KeyboardInterrupt` тоже вызывают
`save_state()` — состояние не теряется. Неизвестная команда и исключения цикла логируются
и не прерывают сессию.

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

# Демонстрация дозированной доставки: один и тот же вопрос с разными слоями
./run.sh --user alice --deliver profile,working,short_term   # без долговременной
./run.sh --user alice                                        # все четыре слоя
```

**Флаги (12):** `--user <id>`, `--profile <id>`, `--deliver <слои>` (по умолчанию полный
канонический набор `DELIVERABLE`: profile, invariants, long_term, working, short_term),
`--mock`, `--fresh` (не восстанавливать прошлое состояние), `--log` (по умолчанию
`Den_log.md`), `--token-log` (по умолчанию `tokens.csv`), `--max-tokens`,
`--price-in` / `--price-out` (₽ за 1M, по умолчанию из констант `PRICE_IN_PER_M` /
`PRICE_OUT_PER_M` = 11 / 33), `--budget <N>` (лимит входящих токенов промта; по
умолчанию `None` — обрезание выключено), `--memory-dir` (перенос хранилища —
используется тестами для изоляции).

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env` (`load_dotenv()`).
При `--mock`, отсутствии ключа или `API_KEY=test-key` автоматически выбирается `MockClient`.
`run.desktop` содержит абсолютные `Exec=`/`Path=` — после переноса на другой хост
его нужно пересоздать (в `.desktop` переменные окружения не раскрываются).

## Агентный цикл

```
старт → DI-сборка build_agent() → идентификация user_id (--user или ввод)
      ├─ profile_repo.exists()  → load_state(): long_term → первая задача → initialized
      │                           └── + load_task_state(): есть task_state.json →
      │                               задача продолжается «с того же места»
      │                               (миграция "execution" → implementation при необходимости)
      └─ нет профиля            → интервью (style/constraints/context) → initialize_user()
                                  → дерево users/<id>/… + профиль default + «Основная_задача»
      → активный профиль: --profile <id> (несуществующий → предупреждение и default)
      → deliver: --deliver ∩ DELIVERABLE (канонический набор блоков промта)
обмен:  сообщение → [auto_route: ProfileRouter выбирает профиль ДО сборки промта]
        → remember_message("user", "M<N>") → build_context(profile_id=active_profile)
        → PromptBuilder.build(ctx, deliver, budget=prompt_budget)   # в блоке working — этап/шаг/ожидаемое действие
        → llm.complete(messages)
        → ответ None? (без записи) : remember_message("assistant", "M<N>a")
        → токен-оценка + строка в tokens.csv
профиль: /profile use → switch_profile(): active_profile привязан к сессии
переход: /task → switch_task(): отметка в working старой задачи + новая задача
         в working и long_term со source_session + новый session_id + load_task_state()
автомат: /plan <цель> → start_task(): new → planning (план построен, ОСТАНОВКА)
         /approve     → approve_plan(): planning → plan_approved (утверждение человеком)
         /step        → step_task(): один проход run_task + сейв task_state.json
                        (plan_approved → implementation: первый шаг; implementation: шаг;
                         шаги кончились → validation; validation → done | failed)
         /run         → run_to_end(max_passes=50): до done/failed/paused;
                        из planning — останавливается (утверждение — только человек)
         /goto <этап> → attempt_transition(): try_transition; отказ → правило +
                        корректный шаг, состояние не меняется, попытка в transition_log
         /pause       → pause_task(): previous_stage сохранён (на любой рабочей стадии)
         /resume      → resume_task(): возврат в previous_stage с current_step — БЕЗ
                        повторного плана и БЕЗ повторных объяснений
         /task retry  → retry_task(): failed → planning (steps/results/error очищены)
выход:  save_state() → working.lifecycle_summary + sessions_resume.md
        + сейв task_state.json (включая transition_log) → resume переживает перезапуск
```

LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer,
retry на HTTP 429 с задержками 2 → 4 → 8 сек, таймаут 30 сек, `choices[0].message.content`,
любой сбой → `None`) и `MockClient` (детерминированная заглушка, отражающая видимые
блоки промта — ею проверяется доставка слоёв без сети). Агент зависит только от
абстракции — провайдер инжектится на старте.

## Архитектура

```
./
├── Kod.py                       # точка входа: DI-композиция + REPL (745 строк)
├── core/                        # ядро агентности (1668 строк)
│   ├── agent.py                 # stateful-оркестратор: identify / interview / respond /
│   │                            #   switch_task / save_state + active_profile / switch_profile /
│   │                            #   auto_route + жизненный цикл задачи: start_task / step_task /
│   │                            #   run_to_end / pause / resume / retry_task / load_task_state +
│   │                            #   ← Д15: approve_plan / attempt_transition / transitions_report +
│   │                            #   LLMExecutor / StubExecutor / default_validator +
│   │                            #   инварианты: load_constraints / propose_and_check / _execute /
│   │                            #   _refusal_message + TextActionAnalyzer
│   ├── invariants.py            # Invariant + ConstraintSet + ProposedAction + InvariantChecker
│   │                            #   (ABC) + RuleBasedChecker + update_invariant
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля по запросу
│   ├── prompt_builder.py        # BLOCK_ORDER (+invariants), build(ctx, deliver, budget)
│   └── state_machine.py         # ← Д15 ПЕРЕПИСАН: TaskStage (8) + TaskState (10 полей) +
│                                #   ALLOWED_TRANSITIONS (whitelist) + can_transition /
│                                #   try_transition / InvalidTransitionError + REFUSAL_RULES +
│                                #   refusal_text + transition_log + approve_plan / pause_task /
│                                #   resume_task / run_task (new → planning → [approve] → …)
├── memory/                      # модель памяти (447 строк)
│   ├── base.py                  # MemoryContext (+profile_id), MemoryItem, MemoryLayer (ABC), PolicyEngine (задел)
│   ├── short_term.py            # append-only, parent_id, SHORT_TERM_WINDOW = 10
│   ├── working.py               # состояние задачи (MERGE) + этап/шаг/действие в блоке промта
│   ├── long_term.py             # profile_ref + tasks / decisions / knowledge
│   ├── profile.py               # активный профиль: style/constraints/context + domain/triggers/skills
│   └── manager.py               # remember / recall / build_blocks / report, LAYER_ORDER
├── storage/                     # физическое хранение (485 строк)
│   ├── store.py                 # фасад иерархии: safe_name, ensure_*, read_*/write_*, зеркала
│   │                            #   profiles/<pid>.json + task_state_path / read_task_state
│   │                            #   (миграция "execution" → implementation) / write_task_state +
│   │                            #   invariants_path / read/write_invariants
│   └── db.py                    # ProfileRepository — SQLite profiles(user_id, profile_id) + is_default, миграция
├── users/                       # рантайм-данные: profiles.db + деревья пользователей
│                                #   (+ task_state.json с transition_log, invariants.json задач)
└── dev/                         # служебное пространство: миграция (migr_plan_*/migr_log),
                                 #   тесты, отчёты, чек-лист Проверка.md
```

| Модуль | Файлы | Назначение |
|---|---|---|
| CLI / DI | `Kod.py` | REPL (32 формы команд), флаги (12), токен-учёт и CSV, журнал маршрутизации, интервью профиля, снимки автомата, команды инвариантов и контроля переходов |
| Ядро | `core/*` | агентный цикл, контролируемый жизненный цикл задачи (строгая машина состояний), профиль-роутер, блоки промта с бюджетом, LLM-интерфейс, слой инвариантов |
| Память | `memory/*` | контракт слоя, 4 реализации, роутер `MemoryManager`, инжект стейта в блок working, задел `PolicyEngine` |
| Хранилище | `storage/*` | фасад канонической иерархии JSON (+ `task_state.json` с миграцией, `invariants.json`), репозиторий профилей в SQLite с миграцией |

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`storage/db.py` не зависит ни от чего внутри проекта. Слои памяти и ядро ФС напрямую
не трогают — только через фасад `Store`.

## Демонстрации задания

| Что проверяем | Как посмотреть | Что видно |
|---|---|---|
| Какие данные попадают в каждый слой | `/memory`, журнал `Den_log.md` | `[Память] profile «default» ← ['id','name','style',…] → … (JSON в SQLite)`, затем `working ← ['description']`, `long_term ← ['tasks']`, `short_term ← M1 (parent=None)`, `M2 (parent=M1)` |
| Как память влияет на ответы | `/compare` | два ответа на один вопрос: с `long_term` и без него + разница в токенах |
| Дозированная доставка | `/deliver profile,working` | слой `long_term` физически отсутствует и в блоках, и в тексте запроса |
| Ответы для разных профилей | `/profile use chemist` → вопрос → `/profile use economist` → тот же вопрос | разный блок профиля и разный ответ при идентичном запросе |
| Ассистент учитывает профиль автоматически | `/profile auto on` → запрос с триггером; `/profile route <текст>` | роутер переключает профиль до сборки промта; в логе «[Роутер] запрос → профиль …» |
| **Явный набор состояний + карта переходов** | `/transitions`, `/state` | 8 стадий, матрица «из → во» (whitelist), «← текущая», журнал попыток + счётчик отказов |
| **Недопустимый переход блокируется кодом** | `/plan <цель>` → `/goto implementation` → `/state` | «ОТКАЗАНО», правило «нельзя делать реализацию до утверждённого плана», состояние не изменилось (planning), запись `allowed: false` в `transition_log` |
| **Реакция ассистента на попытку перепрыгнуть** | `/goto done` (из implementation), `/goto new` (из done) | отказ называет правило («нельзя финал без валидации» / «терминальная стадия») + корректный следующий шаг |
| **Утверждение плана — контрольный пункт** | `/plan` → `/run` (остановка) → `/approve` → `/run` | `/run` из planning останавливается; после `/approve` — реализация → валидация → done |
| **Пауза и продолжение без повторных объяснений** | `/pause` → `/exit` → повторный запуск → `/resume` → `/run` | resume возвращает в `previous_stage` с тем же `current_step` (шаг НЕ повторён, план НЕ перестроен) → done |
| **Персистентность состояния и журнала** | `cat users/<id>/tasks/<task>/task_state.json` | снимок этапа/шага/действия/results + `transition_log` (успехи и отказы) на диске |
| Формализованное состояние задачи | `/plan <цель>` → `/step` → `/state` | снимок: этап, шаг N/M + текст шага, ожидаемое действие, разрешённые переходы |
| Конфликт запроса и инварианта | «Перепиши наш API на FastAPI» (при инварианте Django) | отказ: `id` правила, причина, альтернатива; инструмент не вызван |
| Накопление контекста | `tokens.csv` | рост `prompt_tokens` на серии обменов и стоимость каждого обмена в ₽ |

Готовый сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`.

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient` или заглушка `requests`),
тестовые данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`), рабочие
`users/` не затрагиваются. `pytest` в venv недели отсутствует, поэтому L2 идёт через
собственный лёгкий раннер `unit_runner.py` (без аргумента — все модули, с аргументом — один).

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py` | exit 0 |
| L2 | `env -u API_KEY python dev/tests_debug/unit_runner.py` | **91 OK, 0 FAIL** (10 модулей: storage 7, memory 6, llm 6, prompt 4, agent 4, state 5, person 9, fsm 15, invariants 13, **transitions 14**) |
| L3 | `API_KEY=test-key python dev/tests_debug/smoke.py` | SMOKE OK, exit 0 (4 прогона: полный цикл in-process + CLI, жизненный цикл автомата in-process + CLI с `/approve`) |
| L4 | `API_KEY=test-key python dev/tests_debug/scenario.py` | **9/9 OK** (интервью, маршрутизация, дозированная доставка, влияние, resume, персонализация, пауза/продолжение, конфликт инварианта, **контролируемые переходы**) |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | **15 из 15 ✅, exit 0** (идемпотентен, TMP = `.tmp/acc_$$`; №13–15 — контролируемые переходы: блокировка+логирование, флоу `/approve`, пауза→перезапуск→resume) |

`test_transitions.py` (14 тестов) — канон `arch_den_15.md` §3.2: `can_transition`
разрешённые/запрещённые; `try_transition` не меняет состояние при отказе;
`InvalidTransitionError` объясняет правило; полный поток с утверждением; `/run` не
перепрыгивает утверждение; журнал попыток; `REFUSAL_RULES`; пауза/resume; перезапуск;
миграция снимка; пауза — не лазейка; карта = arch построчно; идемпотентность `/approve`.

Человеческая версия приёмки — **35 критериев, 35/35 зелёных** — в
[`dev/Проверка.md`](dev/Проверка.md): 30 прежних (без регрессии) + **строки 31–35
контролируемых переходов** (31 — явный набор состояний; 32 — явная карта; 33 — блокировка
кодом; 34 — реакция ассистента; 35 — корректность продолжения после паузы).
**Живой смоук — ⏸ отложен**: требует явного согласия на живые LLM-вызовы, финал не блокирует
(карта переходов детерминированная, проверяется на заглушках без сети).

## Что зафиксировано в процессе создания

- **Коррекция naming** (день 12): 21 переименование, признак дня удалён из имён и внутренних
  путей. Инцидент: первая версия `fix_naming.py` подменяла `den_11` → `den_12` (150+
  вхождений) и повредила сам план — исправлено `fix_day_prefix.py` (regex + защита внешних
  путей, режим `--dry`);
- **Живой вызов LLM из теста** (день 11, ✅ исправлено): тест конструктором подхватил реальный
  ключ из окружения и ушёл в сеть. Решение — патчить `core.llm_client.requests.post` и
  запускать тесты с `env -u API_KEY`; отсюда правило и `MockClient` как основной путь L2–L4;
- **Нарушение порядка этапов** (день 11, ⚠️ обход): рабочий код оказался на диске раньше
  плана. Принято правило «файловая система важнее памяти о планах»;
- **Инцидент безопасности** (день 11, ✅ исправлено): при `bash -x check_acceptance.sh`
  реальный `API_KEY` попал в stdout. Вывод значений переменных из чекера убран; ключ не
  коммитился и не уходил в сеть. Рекомендация: при подозрении на компрометацию — ротация
  ключа routerai.ru;
- **Загрязнение корня при смоуке** (день 11, ✅ исправлено): `smoke.py::test_cli_subprocess`
  не передавал `--log/--token-log`, и дефолты писали `Den_log.md`/`tokens.csv` в корень.
  Оба флага переведены в `.tmp/`;
- **Миграция на arch_den_13 → arch_den_14** (дни 13–14): процессная модель «план-эталон →
  рабочие планы → журнал»; дебаг дня 14 (реестр A1–A7/B1–B4, этапы D0–D6) закрыл расхождения
  spec/кода (журналы — в `Nedela_3/den_14/dev/`);
- **Миграция на arch_den_15** (день 15, журнал `dev/migr_log.md`, план-эталон
  `dev/migr_plan.md` + рабочие планы `migr_plan_0..7.md`): этапы M0–M7 по зависимостям
  (ядро → хранение → оркестратор → CLI → тесты → документация → финал). Спорные пункты
  зафиксированы в журнале: правки ядра/оркестратора/CLI слились в один проход M1 (иначе
  проект не компилировался); при отладке гейта найден баг паттерна `grep` (лишняя кавычка
  в `'"allowed": false"'` — в JSON после `false` идёт запятая).

## Файлы проекта

| Файл / каталог | Назначение |
|---|---|
| `Kod.py` | Точка входа: DI-композиция `build_agent()`, REPL, токен-учёт, интервью пользователя и профиля, команды инвариантов и контроля переходов |
| `core/` | Ядро: `agent.py`, `llm_client.py`, `profile_router.py`, `prompt_builder.py`, `state_machine.py` (строгая машина состояний), `invariants.py` |
| `memory/` | Модель памяти: `base.py`, 4 слоя, `manager.py` |
| `storage/` | Хранилище: `store.py` (фасад иерархии + миграция снимков), `db.py` (SQLite профилей + миграция) |
| `users/` | Рантайм-данные: `profiles.db` + `profile.json`, `profiles/<pid>.json`, `long_term_memory.json`, `working_memory.json`, `sessions_resume.md`, `session.json`, `task_state.json` (+ `transition_log`), `invariants.json` |
| `run.sh` / `run.desktop` | Запускающий скрипт (+x) и ярлык (`.desktop` привязан к хосту — после переноса пересоздать) |
| `Den_log.md` | Журнал маршрутизации памяти: «какой слой ← что → куда» + строки «[Автомат] … ОТКАЗАНО» |
| `tokens.csv` | CSV-журнал токенов и стоимости обменов |
| `README.md` | Текстовая часть результата — описание модели памяти, персонализации, инвариантов и контролируемых переходов состояний |
| `Задание_Д15.txt` | Постановка задачи куратора (контролируемые переходы состояний) + чат проекта (не изменяется) |
| `arch_den_15.md` | Целевая архитектура проекта `den_15` (источник миграции) |
| `dev/Проверка.md` | Чек-лист приёмки: 35 критериев с командой проверки по каждому |
| `dev/migr_plan.md` + `migr_plan_0..7.md` | План-эталон и рабочие планы миграции на `arch_den_15.md` (этапы M0–M7) |
| `dev/migr_log.md` | Журнал миграции: записи этапов M0–M7 + финальная запись «Итог миграции» |
| `dev/tests_debug/` | L2 (`unit_runner.py` + `unit/` — 10 модулей), L3 (`smoke.py`), L4 (`scenario.py` — 9 сценариев), гейт (`check_acceptance.sh` — 15 проверок), `scenario/scen_1.md`, `.tmp/` |
| `dev/logs_reports/` | `stages/` (`stage_F_state.md` — факт Дня 13), `errors/` (4 карточки), `archive/` (исторические артефакты Дней 11/12 + указатель) |

## Общее с Днями 6–11 (перенесённые уроки)

- API: RouterAI (OpenAI-совместимый), ключ в `.env` (переменная `API_KEY`), модель
  `stepfun/step-3.5-flash` не менять;
- Retry при HTTP 429: до 3 повторов, задержка 2 → 4 → 8 сек; таймаут 30 сек; сетевые и
  форматные сбои → `None`, цикл чата не прерывается;
- Устойчивость: `sys.stdin.reconfigure(encoding='utf-8', errors='replace')` +
  `sys.stdout.reconfigure(errors='replace')`, `try: import readline`, все пути через
  `BASE_DIR`;
- Токен-учёт: локальная оценка `~1 токен на 4 символа` с явной оговоркой, что авторитет —
  `usage` живого API; CSV-журнал стоимости;
- Зависимости: только `requests`, `python-dotenv` и стандартная библиотека (`sqlite3`
  из stdlib).

## Известные шероховатости и заделы

**Заделы по замыслу (программа следующих дней недели 3):**

- `PolicyEngine` в `memory/base.py` остаётся пустой интерфейс-задел: рабочий слой
  инвариантов реализован **отдельным модулем** `core/invariants.py`;
- `parent_id` сообщений — задел ветвления диалога (наследие Дня 10), самого ветвления ещё нет;
- `skills[]` профиля подмешиваются в промт декларативно — движок оркестрации скиллов
  (реальное исполнение пайплайна) — следующие дни;
- `transition_log` растёт без ограничения (сжатие журнала — следующие дни);
- смоуки этапов миграции (`m1_smoke.py`, `m2_smoke.py`, `m34_smoke.py` в
  `dev/tests_debug/`) — рабочие артефакты этапов M1–M4, вне дерева `arch_den_15.md` §3.1;
  судьба (оставить как доказательства этапов / заархивировать) решена на финальном этапе
  миграции (см. `dev/migr_log.md`).

**Расхождения spec/кода (на поведение не влияют):**

- закрыты в дебаге Дня 14 (журналы — в `Nedela_3/den_14/dev/`): константы
  `MODEL_CONTEXT_LIMIT`/`PRICE_*` в `core/llm_client.py`; `budget` в рабочем пути;
  блок `summary` достижим из CLI; `Agent.identify()` удалён;
- День 15: `next_state()` из `state_machine.py` **удалён** (заменён
  `can_transition`/`try_transition`, callers не осталось) — в отличие от дня 14, где он
  был неиспользуемым заделом.

**Косметика:**

- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми;
  в `.tmp/` накапливаются каталоги прошлых прогонов (в `.gitignore`, не удаляются
  автоматически);
- `dev/meta_promt/` в этой копии пуст (метапромты и журналы дебага дней 13–14 остались
  в `Nedela_3/den_13/`, `Nedela_3/den_14/`);
- изменения миграции не закоммичены (коммит — только по явной команде пользователя).

## Результат

- **Строгая машина состояний задачи**: 8 допустимых состояний (`new`, `planning`,
  `plan_approved`, `implementation`, `validation`, `done`, `paused`, `failed`), явная карта
  `ALLOWED_TRANSITIONS` (whitelist — запрет по умолчанию), программный контроль
  `can_transition`/`try_transition`/`InvalidTransitionError`;
- **Перепрыгивание этапов невозможно**: «нельзя реализацию до утверждённого плана» и «нельзя
  финал без валидации» реализованы топологией графа (отсутствием дуг); `/run` не может обойти
  утверждение плана; пауза — не лазейка (возврат только в `previous_stage`);
- **Отказ с объяснением**: попытка недопустимого перехода не меняет состояние; ассистент
  называет сработавшее правило (`REFUSAL_RULES`) и предлагает корректный следующий шаг;
  каждая попытка (успех и отказ) фиксируется в `transition_log` и переживает перезапуск;
- **Утверждение плана — контрольный пункт человека**: `/plan` строит план и останавливается;
  `/approve` — единственный переход в реализацию;
- **Корректное продолжение после паузы**: `pause` → перезапуск процесса → `resume` возвращает
  ту же стадию и шаг; доступные переходы те же; план не перестраивается, шаги не повторяются;
- **Обратная совместимость**: снимки дней 13/14 мигрируются при загрузке
  (`"execution"` → `implementation`); прежние 30 критериев приёмки — без регрессии;
  контракты памяти/профилей/инвариантов/LLM не тронуты;
- **Инварианты — отдельный слой правил** (День 14, без регрессии): хранятся отдельно от
  диалога, учитываются в промте, проверяются кодом до действия;
- **Персонализированный агент** (День 12, без регрессии): несколько профилей-«призм»,
  роутер с авто-режимом, пайплайн скиллов — «один request → разные response»;
- **4 типа памяти** — разные классы, разные хранилища, разные читатели; дозированная
  доставка + токен-бюджет; каноническая иерархия хранения с фасадом `Store`;
- **Проверяемость**: `/state`, `/transitions`, `/plan`, `/approve`, `/goto`, `/step`,
  `/run`, `/pause`, `/resume`, `/invariants`, `/check` + тестовый контур L2 (91) / L3
  (4 прогона) / L4 (9) без живого ключа, гейт 15/15 и 35/35 критериев приёмки;
- **Заделы недели**: `PolicyEngine`, `parent_id` для ветвления, исполнение пайплайна
  скиллов, сжатие `transition_log`, усложнение `validator`.

## Ручная проверка

Пошаговый чек-лист приёмки с отметками — в файле
[`dev/Проверка.md`](dev/Проверка.md): 35 критериев с конкретной командой проверки по каждому
(комплектность и сборка, четыре слоя, иерархия хранилища, явная маршрутизация, дозированная
доставка, идентификация и интервью, задачи и переходы, промт блоками, LLM за интерфейсом,
state machine, resume, неизменяемые сообщения, демонстрации, текстовое описание, уроки Дня 10,
тесты без ключа, задел инвариантов, расположение чек-листа,
+ строки 20–22: несколько профилей, миграция и обратная совместимость, роутер и авто-выбор,
+ строки 23–25: формализованное состояние, пауза/продолжение, персистентность,
+ строки 26–30: инварианты — отдельное хранение, учёт в промте, отказ, конфликт с объяснением,
изменение с подтверждением,
+ **строки 31–35: контролируемые переходы** — явный набор состояний, явная карта, блокировка
кодом, реакция ассистента, корректность продолжения после паузы).
Машиночитаемый дубль — `dev/tests_debug/check_acceptance.sh` (15 проверок, идемпотентен).
Сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`.
