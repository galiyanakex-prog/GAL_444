# arch_den_12.md — итоговая целевая архитектура проекта `den_12` «Персонализация ассистента»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_12`. Базируется на `ND/arch/arch_den_11.md` (модель памяти агента) и
> дополняет его **персонализацией поверх модели памяти** (несколько профилей +
> профиль-роутер + пайплайн скиллов).
> Источники: `Суть_N3.md`, `Задание_Д12.txt` (+ чат проекта: канон куратора по
> профилям/роутеру/скиллам).

---

## 0. Назначение документа

Документ фиксирует три слоя итогового состояния:

1. **Рабочая архитектура** — модульный stateful-агент с явной моделью памяти
   (краткосрочная / рабочая / долговременная + профиль), унаследованный от `den_11`
   без изменений контрактов, **плюс персонализация**: несколько профилей на
   пользователя, общий профиль-роутер, профиль как пайплайн скиллов.
2. **Служебное пространство `dev/`** — «проект про проект»: всё, чем агент автономно
   создаёт, тестирует и отлаживает проект, с полным аудитом каждого этапа.

---

## 1. Ключевая идея и принципы

### 1.1 Ключевая идея
`den_12` — переход от «одной модели памяти» (день 11) к **персонализированному
агенту**: пользователь настраивает агента под себя и под задачу. Профиль — это
«призма» конкретной доменной области (пример куратора: Химик / Психолог / Экономист
для постов в ТГ; агент для покупок → сборка корзины). На одного пользователя —
**несколько профилей**; **общий профиль-роутер** выбирает конкретный профиль по
запросу; **профиль = пайплайн из скиллов** (оркестрация под задачу).

Формула ценности (Суть_N3): **один request — разные response** — в зависимости от
активного профиля один и тот же запрос даёт разный состав промта и разный ответ.

### 1.2 Принципы
- **Полиморфизм через интерфейсы, а не наследование** — `MemoryLayer`, `LLMClient`, `PolicyEngine`.
- **Инкапсуляция через фасады** — агент не владеет файлами/БД/секретами напрямую.
- **История ≠ состояние** — неизменяемые сообщения (`parent_id`) vs пересчитываемое состояние задачи.
- **Метаданные у каждого объекта памяти** — `scope`, `owner`, `visibility`, `source`, `source_message_id`.
- **Дозированная доставка** — набор включаемых слоёв памяти — параметр, а не «всё всегда».
- **Явная маршрутизация** — вызов `remember(layer, ...)` с логом «что куда легло».
- **Память независима от профилей** (канон Федора Ч. из чата задания): краткосрочная
  (окно сообщений), рабочая (контекст задачи сессии) и долговременная (глобальные
  факты) живут отдельно от профилей; профиль — четвёртый слой с мультипрофильностью.

---

## 2. Рабочая структура проекта

### 2.1 Дерево модулей

```
Nedela_3/den_12/
├── Kod.py                       # точка входа: DI-композиция + REPL
├── core/
│   ├── __init__.py
│   ├── agent.py                 # оркестратор: active_profile, switch_profile, auto_route
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        # ← НОВОЕ: ProfileRouter — выбор профиля по запросу
│   ├── prompt_builder.py        # сборка промта блоками + дозированная доставка + бюджет
│   └── state_machine.py         # задел: TaskState + ALLOWED_TRANSITIONS (без логики)
├── memory/
│   ├── __init__.py
│   ├── base.py                  # MemoryLayer (ABC) + MemoryContext(+profile_id) + PolicyEngine(задел)
│   ├── short_term.py            # ShortTermMemory — неизменяемые сообщения (parent_id)
│   ├── working.py               # WorkingMemory — пересчитываемое состояние задачи
│   ├── long_term.py             # LongTermMemory — структурированные решения/знания
│   ├── profile.py               # Profile — style + constraints + context + skills (активный профиль)
│   └── manager.py               # MemoryManager — явная маршрутизация «что куда»
├── storage/
│   ├── __init__.py
│   ├── store.py                 # фасад: layout users/<id>/… + зеркала profiles/<pid>.json
│   └── db.py                    # ProfileRepository: (user_id, profile_id) + is_default, миграция
├── users/                       # рантайм-хранилище памяти (создаётся при работе)
├── run.sh                       # +x: cd dirname + source ../../.venv/bin/activate + python
├── run.desktop                  # Exec = абсолютный путь к .sh (единственное легитимное имя дня)
├── README.md                    # описание проекта + модель памяти + персонализация
├── PLAN_naming.md               # план коррекции naming (артефакт процесса, корень)
├── Den_log.md                   # журнал маршрутизации памяти (рантайм-артефакт)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
├── Задание_Д12.txt              # постановка куратора (неизменяемый первоисточник)
├── START-PROMT.md               # управляющий промт автономного создания
└── dev/                         # ← служебное пространство (раздел 3), в т.ч. Проверка.md
```

### 2.2 Модель памяти (без изменений от дня 11 + profile_id в контексте)

```python
# memory/base.py
class MemoryContext:
    def __init__(self, user_id, task="", session_id="", profile_id="")
    # profile_id — АДДИТИВНЫЙ параметр: существующие вызовы (3 аргумента) не ломаются;
    # "" → активный/дефолтный профиль.

class MemoryLayer(ABC):
    layer_name: str                 # short_term | working | long_term | profile
    scope: str                      # user | task | session
    def read(self, ctx) -> dict: ...
    def write(self, ctx, item) -> str:   # возвращает «куда легло»
    def as_prompt_block(self, ctx) -> str: ...

# memory/manager.py
class MemoryManager:
    def remember(self, layer: str, ctx, content=None, source=..., **item) -> str
    def recall(self, layers: set[str], ctx) -> dict:  # дозированная доставка
    def build_blocks(self, deliver: set[str], ctx) -> dict
    def report(self, ctx) -> str:                     # снимок «что где лежит» для /memory
```

| Класс                     | Что хранит                                                 | Файл/хранилище |
|---                        |---                                                         |---|
| `ShortTermMemory`         | сообщения текущей сессии (неизменяемые, `parent_id`)       | `tasks/<task>/sessions/<id>/session.json` |
| `WorkingMemory`           | описание задачи, ссылки, резюме жизненного цикла, `decisions/constraints/facts/open_questions`, `current_state` |     `tasks/<task>/working_memory.json` |
| `LongTermMemory`          | ссылка на профиль (`profile_ref`), задачи, решения, знания | `users/<id>/long_term_memory.json`  |
| `Profile`                 | **несколько профилей**: `profile_id`, `name`, `domain`, `triggers[]`, `style{}`, `constraints{}`, `context{}`, `skills[]` | SQLite `(user_id, profile_id)` + зеркала `users/<id>/profiles/<pid>.json` |

### 2.3 Модель данных профиля (расширение, обратно совместимое)

```json
{
  "id": "<user_id>",
  "profile_id": "chemist",
  "name": "Химик",
  "domain": "химия",
  "triggers": ["химия", "реактив", "реакция"],
  "style": {"answers": "..."},
  "constraints": {"answers": "..."},
  "context": {"answers": "..."},
  "skills": [
    {"name": "spec",   "instructions": "сначала составь спеку ответа"},
    {"name": "review", "instructions": "проверь факты по домену"}
  ]
}
```

- `profile_id` — короткое имя (safe_name); первый/единственный профиль — `default`.
- `domain`, `triggers`, `skills` опциональны: пустые — профиль работает как в дне 11.
- **Профиль = пайплайн из скиллов** (канон куратора): упорядоченный список скиллов,
  их инструкции подмешиваются в промт; исполнение — декларативное (движок оркестрации
  скиллов — следующие дни).
- Старый профиль без `profile_id` трактуется как `default` (миграция БД, п.2.4).

### 2.4 Хранилище профилей (SQLite + зеркала)

```python
# storage/db.py — ProfileRepository
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL DEFAULT 'default',
    profile_json TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, profile_id)
)
# Миграция: старая схема (user_id PRIMARY KEY) → перенос строк как
# profile_id='default', is_default=1 (одна транзакция, данные не теряются,
# проверка схемы — PRAGMA table_info).

class ProfileRepository:
    def save_profile(self, user_id, profile, profile_id="default") -> str
        # upsert; первый профиль → is_default=1; лог «[Хранилище] profile …»
    def load_profile(self, user_id, profile_id=None) -> dict | None  # None → дефолтный
    def list_profiles(self, user_id) -> list    # [(profile_id, is_default)], sorted
    def get_default(self, user_id) -> str | None
    def set_default(self, user_id, profile_id) -> bool
    def exists(self, user_id) -> bool           # есть хотя бы один профиль (семантика прежняя)
```

```python
# storage/store.py — Store (зеркала)
# users/<id>/profiles/<profile_id>.json — зеркало каждого профиля;
# users/<id>/profile.json остаётся зеркалом профиля default (обратная совместимость).
def profiles_dir(self, user_id) -> str
def profile_path(self, user_id, profile_id="default") -> str
def save_profile(self, user_id, profile, profile_id="default") -> str  # SQLite + зеркало
def load_profile(self, user_id, profile_id=None) -> dict | None        # SQLite → fallback JSON
def list_profiles(self, user_id) -> list
def set_default_profile(self, user_id, profile_id) -> bool
```

### 2.5 Иерархия хранения (канон + profiles/)

```
users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite)
├── profiles/                    # ← НОВОЕ: зеркала всех профилей
│   ├── default.json
│   ├── chemist.json
│   └── economist.json
├── long_term_memory.json        # {profile_ref, tasks:[{name, ref}], decisions[], knowledge[]}
└── tasks/<task_name>/
    ├── working_memory.json      # {description, refs, lifecycle_summary, decisions[],
    │                            #  constraints[], facts[], open_questions[], current_state}
    ├── sessions_resume.md       # резюме сессий (только данные о задаче)
    └── sessions/<session_id>/
        └── session.json         # {messages:[{id, parent_id, role, content, created_at}]}
```

- Сообщения **неизменяемы**; ветвление = новый `parent_id` от точки развилки.
- Рабочая память — **пересчитываемое состояние** задачи, а не лог сообщений.
- Слои short_term/working/long_term **не зависят от активного профиля** — профиль
  влияет только на блок profile в промте.

### 2.6 Профиль-роутер (новый модуль)

```python
# core/profile_router.py
class ProfileRouter:
    def __init__(self, store, log=None)
    def route(self, user_id, text) -> str | None
    # Оценка: +2 за каждый триггер (регистронезависимо), +1 за вхождение domain;
    # победитель = максимум (>0); ничья/ноль → None (остаёмся на текущем/дефолтном).
    # Лог: «[Роутер] запрос → профиль <id> (счёт N)» / «[Роутер] без совпадений → default».
    def explain(self, user_id, text) -> str    # разбор решения для /profile route
```

- Роутер — «общий профиль-роутер» из канона куратора: выбирает конкретный профиль
  по доменной области запроса.
- Детерминированный (без LLM) — тестируется без живого ключа.

### 2.7 Сборка промта (блоки + бюджет; порядок не меняется)

```text
[system: роль]
[system: профиль]                 ← АКТИВНЫЙ профиль: «Профиль: <name> (<profile_id>)»,
                                     стиль/ограничения/контекст + «Пайплайн скиллов:»
                                     (нумерованные инструкции skills) + «Домен:»
[system: долговременная память]   ← слой long_term (вкл/выкл)
[system: рабочая память задачи]   ← слой working (вкл/выкл)
[system: summary общего префикса] ← опционально
[messages: краткосрочная память]  ← слой short_term (окно 10)
[user: текущий запрос]
[резерв: output + tool]
```

- `PromptBuilder.build(ctx, deliver: set[str], budget: int) -> list[dict]`;
  `BLOCK_ORDER = (role, profile, long_term, working, summary, short_term, current)`.
- Профиль **подключён к каждому запросу**: активный профиль привязан к сессии, его
  блок входит в каждый промт (требование задания «подключите профиль к каждому запросу»).

### 2.8 LLM-клиент (без изменений)

```python
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...
class RouterAIClient(LLMClient): ...   # retry 429: 2→4→8 с, таймаут 30 с
class MockClient(LLMClient): ...       # детерминированная заглушка для тестов
```

### 2.9 Задел под state machine (без изменений)

```python
class TaskState(Enum):
    PLANNING = "planning"; EXECUTION = "execution"; VALIDATION = "validation"; DONE = "done"
ALLOWED_TRANSITIONS = {PLANNING:{EXECUTION}, EXECUTION:{VALIDATION, PLANNING},
                       VALIDATION:{EXECUTION, PLANNING}, DONE:set()}
```
Только структура + хранение стадии в рабочей памяти; логика переходов и фильтр
инвариантов — следующие дни.

### 2.10 Оркестратор `Agent` (жизненный цикл + активный профиль)

```python
# core/agent.py — дополнение к контракту дня 11
# В __init__: self.active_profile = None (None → default), self.auto_route = False,
# self.router = ProfileRouter(store, log) — если у store есть profile_repo.
def switch_profile(self, profile_id) -> bool
    # проверка через store.list_profiles; лог «[Агент] активный профиль: <id>»
def build_context(self, query)
    # ctx = MemoryContext(user_id, task, session_id, profile_id=active_profile or "")
def respond(self, user_message)
    # если auto_route: candidate = router.route(user_id, message);
    # candidate и != active → switch_profile(candidate) ПЕРЕД сборкой промта
```

```
старт → идентификация user_id (ввод или --user) → активный профиль (--profile или default)
  ├── известный id → загрузка профиля + long-term + список задач
  └── новый id → интервью (style/constraints/context) → профиль default + дерево users/<id>/…
цикл:
  сообщение → [auto_route: роутер выбирает профиль] → remember(short_term) →
  build_context(с активным профилем) → PromptBuilder(deliver=...) →
  LLMClient.complete → ответ → remember(short_term)
exit → сохранение состояния (resume «с того же места»)
```

### 2.11 CLI-команды (рабочие)

| Команда | Назначение |
|---|---|
| `/memory` | снимок «какие данные в каком типе памяти» |
| `/profile` | активный профиль (обратно совместимо с днём 11) |
| `/profile list` | профили пользователя: `* default`, `> активный` |
| `/profile show <id>` | полный JSON профиля |
| `/profile use <id>` | переключить активный профиль сессии |
| `/profile new <id>` | мини-интервью: name, domain, triggers, style, constraints, context |
| `/profile route <текст>` | показать решение роутера (explain), НЕ переключая |
| `/profile auto on\|off` | авто-роутинг по каждому запросу |
| `/tasks` | список задач + активная задача |
| `/task <имя>` | переключить/создать задачу (с отметкой перехода и обратной ссылкой) |
| `/deliver <layers>` | задать набор включаемых слоёв (дозированная доставка) |
| `/compare`, `/summary`, `/state`, `/tokens`, `/cost`, `/help`, `/exit` | наследуются из дня 11 |

Флаги запуска: `--user <id>`, `--profile <id>` (← НОВОЕ: активный профиль на старте;
несуществующий → предупреждение и default), `--deliver <layers>`, `--mock`, `--fresh`,
`--log`, `--token-log`, `--memory-dir`, `--max-tokens`, `--price-in/--price-out`.

---

## 3. Служебное пространство `dev/` (проект про проект)

`dev/` хранит всё, чем агент **автономно** создаёт, тестирует и отлаживает проект.
Разделено по назначению: сценарий создания → метапромты частей → тесты/дебаг →
логи/отчёты.

### 3.1 Дерево `dev/`

```
Nedela_3/den_12/dev/
├── FINAL_REV.md                  # каталог-резюме проекта (корректируется на текущее состояние)
├── Проверка.md                   # сценарий РУЧНОЙ проверки готового проекта
├── meta_promt/                   # метапромты для создания отдельных частей
│   ├── ПРОМТ_memory.md           # модель памяти: MemoryLayer, 4 класса, метаданные
│   ├── ПРОМТ_storage.md          # хранилище: layout + SQLite + неизменяемые сообщения
│   ├── ПРОМТ_llm.md              # LLMClient + RouterAIClient + MockClient
│   ├── ПРОМТ_prompt.md           # PromptBuilder: блоки + бюджет + дозированная доставка
│   ├── ПРОМТ_agent.md            # оркестратор: идентификация, интервью, цикл
│   ├── ПРОМТ_state.md            # задел state machine
│   ├── ПРОМТ_cli.md              # REPL, команды, флаги
│   ├── ПРОМТ_readme.md           # README.md + Проверка.md + текстовое описание модели
│   ├── ПРОМТ_FINAL_REV.md        # каталог-резюме: конвенция блоков/маркеров/счётчиков
│   └── ПРОМТ_person.md           # ← НОВОЕ: Этап E — персонализация (контракты §2.3–2.7, 2.10–2.11)
├── tests_debug/                  # тестирование и отладка
│   ├── check_acceptance.sh       # гейт приёмки (9 проверок, TMP в .tmp/acc_$$)
│   ├── unit_runner.py            # L2-раннер юнит-тестов (без pytest)
│   ├── smoke.py                  # L3-смоук: in-process + CLI subprocess
│   ├── scenario.py               # L4-сценарии задания (+ scenario_personalization)
│   ├── unit/                     # юнит-тесты: test_{storage,memory,llm,prompt,agent,state}.py
│   │                             #   + ← НОВОЕ: test_person.py (мультипрофиль, миграция, роутер)
│   ├── scenario/                 # scen_1.md — сценарий ручной демонстрации куратору
│   ├── smoke/                    # пусто (каркас)
│   ├── fixtures/                 # пусто (каркас)
│   └── .tmp/                     # ← единственное место прогонов и временных файлов
│                                 #   (в .gitignore; unit_*/smoke_*/scn_*/acc_$$)
└── logs_reports/                 # логирование и отчёты по этапам создания
    ├── stages/                   # stage_00_env … stage_10_final + ← НОВОЕ: stage_E_person.md
    ├── errors/                   # карточки ошибок: контекст, стек, решение, статус
    ├── run_log.md                # сводный журнал прогонов (команда → результат → EXIT)
    └── final_report.md           # итоговый отчёт «было/стало/проверено/спорное»
```

### 3.2 `START-PROMT.md` — каркас-алгоритм автономного создания

Задаёт пошаговый алгоритм и делегирует детали метапромтам: суть дня → входные данные
(переменные `$KOD/$DEV/$MP/$LOGS/$TST/$PY/$DONOR/$MODEL`, запрет хардкода путей) →
автономный режим (human-gate только на живой ключ) → каркас Этап 0→11 → параллельный
запуск субагентов → журналирование → цикл отладки L1–L4 со стоп-условиями → критерии
приёмки + гейт → запреты → восстановление контекста.

Для `den_12` программа работ дополняется этапами из `Задание_Д12.txt`:
коррекция naming (по `PLAN_naming.md`) → Этап C (очистка артефактов) → Этап D
(проверки, вывод только в `.tmp/`) → **Этап E (персонализация по `ПРОМТ_person.md`)**.

### 3.3 `PLAN_naming.md` — план коррекции naming (корень проекта)

Концепция: признак дня (`den_11`, `den11`, `d11`, `Д11`) из имён папок/файлов и
внутренних путей **удаляется, а не подменяется**; пути — относительные от корня
проекта. Исключения: внешние ссылки (`ND/arch/arch_den_11*.md`, донор `den_10_Kod.py`,
`Суть_N3.md`, `Step-3.5-Flash_params.md`), абсолютные пути хоста (`run.desktop`,
`$KOD`), `Задание_Д12.txt`, сам план (колонка «Было»). Содержит таблицу 21
переименования, алгоритм шагов 1–13, правила правки содержимого, инструменты
(`.tmp/fix_naming.py`, `.tmp/fix_day_prefix.py`) и журнал выполнения.

**Результат:** при копировании проекта в `den_13`, `den_14`, … переименовывать ничего
не нужно — меняется только внешняя папка дня (и абсолютные пути хоста в `run.desktop`).

### 3.4 `tests_debug/` — тестирование и отладка

- `unit/` — юнит-тесты каждого слоя памяти, `MemoryManager`, `PromptBuilder`, `Store`,
  `ProfileRepository`; **`test_person.py`** — мультипрофильный roundtrip, миграция
  старой схемы, обратная совместимость, роутер (триггеры/ничья/None), различие
  промтов для двух профилей, switch_profile/auto_route. Все на `MockClient`.
- `smoke.py` (L3) — полный цикл in-process + CLI subprocess; логи изолированы
  флагами `--log/--token-log` в `.tmp/` (корень проекта не загрязняется).
- `scenario.py` (L4) — сценарии задания: интервью, маршрутизация, дозированная
  доставка, влияние памяти, resume + **`scenario_personalization`**: пользователь с
  профилями «Химик» и «Экономист» — один запрос даёт разный состав промта; лог
  содержит «[Роутер]» и «[Агент] активный профиль».
- `check_acceptance.sh` — гейт приёмки (9 проверок); временный каталог
  `$TST/.tmp/acc_$$`; не трогает `users/` проекта.
- `.tmp/` — **единственное место** прогонов и временных файлов (в `.gitignore`).

### 3.5 `logs_reports/` — логирование и отчёты по этапам

- `stages/stage_NN_*.md` — на каждый этап: «было → стало → проверка → статус»;
  Этап E — `stage_E_person.md`.
- `errors/error_<timestamp>.md` — контекст этапа, тип ошибки, стек, решение, статус
  (✅ исправлено / ⚠️ обход / ❌ открыто).
- `run_log.md` — сводный журнал прогонов: команда → результат → exit-код; карта
  «этап → субагент → target → статус» при параллельной работе.
- `final_report.md` — итоговый отчёт: дерево проекта, результаты приёмки,
  «что сделано / что проверено / что осталось спорным», предложение коммита.


---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)
| Артефакт                                    | Назначение   |
|                 ---                         |           ---|
| `Kod.py` + `core/` + `memory/` + `storage/` | персонализированный stateful-агент с моделью памяти |
| `core/profile_router.py`                    | общий профиль-роутер (детерминированный выбор профиля) |
| `run.sh` / `run.desktop`                    | запуск (`.sh` исполняемый, `Exec` — абсолютный путь) |
| `README.md`                                 | описание проекта + модель памяти + **раздел «Персонализация»** |
| `users/<id>/…`                              | рантайм-хранилище: память + `profiles/<pid>.json` + `profiles.db` |

### 4.2 Служебные артефакты (процесс)
| Артефакт              | Назначение |
|---                    |---|
| `START-PROMT.md`      | сценарий автономного создания и тестирования |
| `PLAN_naming.md`      | план и журнал коррекции naming |
| `dev/Проверка.md`     | единственный сценарий ручной проверки (19 пунктов + строки 20–22 персонализации) |
| `dev/FINAL_REV.md`    | каталог-резюме проекта (блоки, деревья, маркеры ПРОГРЕСС) |
| `dev/meta_promt/*.md` | метапромты создания частей (включая `ПРОМТ_person.md`) |
| `dev/tests_debug/*`   | L2/L3/L4 + гейт + `.tmp/` (единственное место временных файлов) |
| `dev/logs_reports/*`  | отчёты по этапам (вкл. `stage_E_person.md`), ошибки, сводный лог, финальный отчёт |

> `Проверка.md` и `FINAL_REV.md` живут **только в `dev/`** — артефакты процесса
> создания/приёмки, а не продукт; в корне проекта их нет (проверка [9] гейта).

### 4.3 Критерии приёмки персонализации
| Пункт | Что проверяем                     | Как                                                                       |
|  ---  |---                                |---                                                                        |
|   20  | Несколько профилей на пользователя| `test_person.py`: roundtrip двух профилей, list_profiles, get/set_default |
|   21  | Миграция и обратная совместимость | старая БД → профиль `default`; `MemoryContext` с 3 аргументами работает; 19 прежних пунктов зелёные |
|   22  | Роутер и авто-выбор профиля       | `test_person.py` + `scenario_personalization`: триггеры → профиль; разные профили → разные промты/ответы; лог «[Роутер]» |

Гейт: `unit_runner.py` (все тесты) → `scenario.py` → `check_acceptance.sh` 9 из 9 —
всё без живого ключа (`API_KEY=test-key` / `MockClient`).

---

## 5. Порядок достижения итогового состояния

1. **Этап Персонализация** — по `dev/meta_promt/ПРОМТ_person.md`, порядок по
   зависимостям: `storage/db.py` (схема + миграция) → `storage/store.py` (зеркала) →
   `memory/base.py` (profile_id) → `memory/profile.py` (блок промта) →
   `core/profile_router.py` → `core/agent.py` (active_profile/auto_route) →
   `Kod.py` (/profile-семейство, --profile) → `test_person.py` +
   `scenario_personalization` → README/Проверка (строки 20–22) → `stage_E_person.md`.
6. **Финал** — прогон всех проверок, `final_report.md`, корректировка `FINAL_REV.md`,
   предложение коммита (коммит — только по явной команде пользователя).

---

## 6. Итог

После завершения `den_12` получается:

- **Персонализированный агент**: поверх явной модели памяти (4 слоя, унаследованы
  без регрессии) пользователь настраивает агента под себя — несколько профилей-«призм»
  (стиль/констрейнты/контекст + домен/триггеры), общий профиль-роутер (детерминированный
  выбор по запросу, режим auto), профиль как декларативный пайплайн скиллов; активный
  профиль привязан к сессии и подключён к каждому запросу — «один request — разные
  response» доказуемо (разные профили → разный состав промта → разные ответы).
- **Служебное пространство `dev/`**: воспроизводимое автономное создание — каркас
  (`START-PROMT.md`), метапромты частей (включая
  `ПРОМТ_person.md`), тестовый контур L2–L4 + гейт (временные файлы только в `.tmp/`),
  полный аудит этапов (отчёты, ошибки, сводный лог).

Такой фундамент позволяет следующим дням недели 3 нарастить полноценную task state
machine, фильтр инвариантов (PolicyEngine), исполнение пайплайна скиллов (реальную
оркестрацию) и объединение «кубиков» в систему без переписывания базы.
