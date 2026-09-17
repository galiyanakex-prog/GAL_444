# arch_den_11_plan_2.md — модернизация плана `den_11` (вариант А) лучшими решениями из `arch_prim.md`

> Документ — надстройка над `ND/arch/arch_den_11_plan.md` (вариант А: модульная архитектура).
> Здесь из `ND/arch/arch_prim.md` отобраны **наилучшие и реалистично применимые** решения
> для учебного дня `den_11` («Модель памяти агента») и спроецированы на модульную схему.
> Что НЕ берём в `den_11` и почему — раздел 7.

---

## 1. Принцип отбора: «состояние + ограничения, но без преждевременной промышленности»

`arch_prim.md` описывает enterprise-уровень (tenant, ReBAC/ABAC, vault, векторная БД,
подагенты). Для `den_11` отбираются решения, которые:

1. прямо соответствуют заданию и ответам куратора (3 типа памяти, иерархия хранения,
   явный выбор «что куда», идентификация, интервью, дозированная доставка);
2. дают **фундамент для следующих дней недели 3** (state machine, инварианты) без их
   преждевременной реализации;
3. сохраняют учебную соразмерность («2–3 файла», SOLID, интерфейсы) — то есть это
   **архитектурная мысль, а не раздувание кода**.

Формула из `arch_prim.md`, принятая как стержень дня:

> **Диалоги — это версии графа; проекты — контейнеры контекста и политик; права — отдельный
> вычисляемый граф отношений; память — набор объектов с областью видимости; агент —
> оркестратор, который не владеет напрямую ни данными, ни секретами, ни полномочиями.**

---

## 2. Что берём из arch_prim.md (9 решений)

| # | Решение из arch_prim.md | Как проецируется в den_11 (вариант А) |
|---|---|---|
| R1 | **Многоуровневая память вместо одного профиля** | 4 сущности памяти: ShortTerm / Working / LongTerm / Profile — каждый класс + своё хранилище + свой читатель |
| R2 | **Полиморфизм через интерфейсы, а не наследование** | единый интерфейс `MemoryLayer`, интерфейс `LLMClient`, интерфейс-задел `PolicyEngine` |
| R3 | **Инкапсуляция через фасады** | агент не читает файлы/БД напрямую: `MemoryService`, `ProfileRepository`, `PromptBuilder`, `Store` |
| R4 | **История ≠ состояние** | неизменяемые сообщения (append-only, `parent_id`) vs пересчитываемое состояние задачи (рабочая память) |
| R5 | **Метаданные у каждого объекта памяти** | `scope`, `owner`, `visibility`, `source`, `priority`, `expires_at`, `source_message_id` |
| R6 | **Checkpoint + структурированный summary** | долговременная/рабочая память — структурированные блоки (`decisions`, `constraints`, `facts`, `open_questions`) со ссылками на исходные сообщения |
| R7 | **Дозированная доставка контекста** | `PromptBuilder` собирает промт блоками; набор включаемых слоёв — параметр, а не «всё всегда» |
| R8 | **Наследование конфигурации merge** | цепочка `user → task → session`; скалярное перекрытие + поле `source` (происхождение) для объяснимости |
| R9 | **Токен-бюджет и приоритеты удаления** | резерв под ответ; сжатие заранее (60–75%); «нельзя удалять» (system/решения/активный запрос) vs «можно сжать» (приветствия/повторы/обработанные tool-результаты) |

---

## 3. Модернизированная схема варианта А

### 3.1 Структура модулей (обогащена фасадами и интерфейсами)

```
den_11/
├── den_11_Kod.py                # точка входа: DI-композиция + REPL
├── core/
│   ├── agent.py                 # оркестратор (stateful-обёртка): не владеет данными напрямую
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient (тесты)
│   ├── prompt_builder.py        # сборка промта блоками + дозированная доставка
│   └── state_machine.py         # задел: 4 стадии + ALLOWED_TRANSITIONS (без логики)
├── memory/
│   ├── base.py                  # MemoryLayer (ABC): read/write/route + метаданные
│   ├── short_term.py            # ShortTermMemory (неизменяемые сообщения с parent_id)
│   ├── working.py               # WorkingMemory (пересчитываемое состояние задачи)
│   ├── long_term.py             # LongTermMemory (структурированные решения/знания)
│   └── profile.py               # Profile: style + constraints + context
├── storage/
│   ├── store.py                 # layout users/<id>/tasks/<task>/sessions/<id> + CRUD (фасад)
│   └── db.py                    # SQLite: профили (ProfileRepository)
└── ... (README, run.sh, .desktop, Проверка_Д11.md, лог, users/)
```

Ключевое отличие от исходного плана: **агент работает только с фасадами и интерфейсами**
(`MemoryService`, `ProfileRepository`, `PromptBuilder`, `LLMClient`), а не с файловой
системой и БД напрямую (R3).

### 3.2 Модель памяти (R1 + R2 + R5)

```python
# memory/base.py — единый контракт (полиморфизм)
class MemoryLayer(ABC):
    layer_name: str                       # short_term | working | long_term | profile
    scope: str                            # user | task | session
    def read(self, ctx) -> dict: ...
    def write(self, ctx, item) -> str: ...  # возвращает «куда легло» (для лога)
    def as_prompt_block(self, ctx) -> str: ...
```

Каждый объект памяти несёт метаданные (R5):
```json
{
  "content": "...",
  "scope": "task", "owner": "user_42",
  "visibility": "private", "source": "user|model|document",
  "priority": 50, "expires_at": null,
  "source_message_id": "M52"
}
```

`MemoryManager` — роутер с **явной маршрутизацией** (требование задания «явно выбирали»):
```python
memory.remember("long_term", key="решение", value="PostgreSQL", source_message_id="M44")
memory.remember("working",  key="open_questions", value="...", ...)
memory.remember("short_term", message=msg)   # append-only
```
Каждый вызов пишет в лог строку вида `[Память] long_term ← решение=PostgreSQL (M44)`.

### 3.3 Хранилище: иерархия + неизменяемость (R4)

Каноничная структура куратора сохраняется, но дополняется **неизменяемой историей сообщений**
с `parent_id` (внутри `session.json`):

```
users/<user_id>/
├── profile.json                 # {id, name, style{}, constraints{}, context{}}  ← JSON в SQLite
├── long_term_memory.json        # {tasks:[{name, ref, status}], decisions:[...], knowledge:[...]}
└── tasks/<task_name>/
    ├── working_memory.json      # {description, refs:[session_id+timecode], lifecycle_summary,
    │                            #  decisions[], constraints[], facts[], open_questions[]}
    ├── sessions_resume.md       # резюме сессий (только данные о задаче)
    └── sessions/<session_id>/
        └── session.json         # {messages:[{id, parent_id, role, content, created_at}]}
```

- **`parent_id`** в сообщениях сессии — задел под ветвление из `den_10` (R4): сообщения
  неизменяемы, ветвление = новый `parent_id` от точки развилки, контекст восстанавливается
  обходом `leaf → parent → … → root`.
- **`working_memory`** — пересчитываемое состояние задачи (не лог): описание + ссылки на
  сессии/таймкоды + резюме жизненного цикла + структурированные блоки (R6).
- **`long_term_memory`** — структурированный набор (`decisions`, `knowledge`, ссылки на
  задачи), а не один текст.

### 3.4 Структурированный summary вместо «бесформенного абзаца» (R6)

Для сжатия контекста (наследие дней 7–10) и для долговременной памяти использовать
структуру, а не единый текст:

```json
{
  "period": "session_81 (M0-M70)",
  "goal": "...",
  "decisions":  [{"text": "PostgreSQL", "source_message_id": "M44", "confidence": 0.96}],
  "constraints": ["Нельзя отдавать секреты модели"],
  "facts":      ["Проект развёрнут в Kubernetes"],
  "open_questions": ["Нужен ли отдельный tenant?"],
  "rejected_options": ["Прямой доступ агента к БД"],
  "active_tasks": ["Спроектировать policy engine"]
}
```
Ссылки `source_message_id` критичны: при ошибке summary можно вернуться к оригиналу (R6).

### 3.5 PromptBuilder: дозированная доставка (R7 + R9)

```text
[system: роль]
[system: профиль — style/constraints/context]   ← слой profile (вкл/выкл)
[system: долговременная память]                  ← слой long_term (вкл/выкл)
[system: рабочая память задачи]                  ← слой working (вкл/выкл)
[system: summary общего префикса]                ← опционально
[messages: краткосрочная память — окно]          ← слой short_term
[user: текущий запрос]
[резерв: output + tool]
```

- Набор слоёв задаётся параметром: `deliver={"profile","working"}` без `long_term` — это и
  есть «явный выбор» и демонстрация «влияния памяти на ответы» (сравнение с/без слоя).
- Токен-бюджет (R9): `tokens(system) + tokens(memory) + tokens(history) + reserve ≤ C`,
  сжатие запускается заранее (60–75% бюджета), а не по переполнению.

### 3.6 LLM-клиент: полиморфизм (R2)

```python
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...

class RouterAIClient(LLMClient): ...   # текущий OpenAI-совместимый вызов
class MockClient(LLMClient): ...       # детерминированная заглушка для тестов
```
`Agent` и `PromptBuilder` зависят только от `LLMClient`; провайдер инжектится на старте.
`MockClient` закрывает тесты без живого ключа (урок дней 6–10).

### 3.7 Задел под права и state machine (без реализации)

- **State machine** (`state_machine.py`): только структура и хранение текущей стадии в
  рабочей памяти; логика переходов — следующий день:
```python
class TaskState(Enum):
    PLANNING = "planning"; EXECUTION = "execution"; VALIDATION = "validation"; DONE = "done"
ALLOWED_TRANSITIONS = {PLANNING:{EXECUTION}, EXECUTION:{VALIDATION, PLANNING},
                       VALIDATION:{EXECUTION, PLANNING}, DONE:set()}
```
- **PolicyEngine** (`memory/base.py`): пустой интерфейс-задел, чтобы инварианты следующего
  дня легли чисто; в `den_11` только `visibility`/`scope` в метаданных памяти (R5), без
  полноценного RBAC/ReBAC (см. раздел 7).

---

## 4. Что изменилось относительно arch_den_11_plan.md

| Аспект | Было в plan.md | Стало в plan_2.md |
|---|---|---|
| Память | 4 класса + MemoryManager | + единый интерфейс `MemoryLayer` (полиморфизм) + метаданные `scope/owner/visibility/source/priority/source_message_id` |
| Хранилище | иерархия users/tasks/sessions | + неизменяемые сообщения с `parent_id` + структурированные блоки в working/long-term |
| История/состояние | не разделялись явно | разделены: неизменяемая история vs пересчитываемое состояние задачи |
| Summary | единый текст | структурированный summary с `source_message_id` |
| PromptBuilder | блоки + выбор слоёв | + токен-бюджет и приоритеты удаления |
| LLM | интерфейс + RouterAIClient | + MockClient для тестов |
| Инкапсуляция | агент работает с классами | агент работает только с фасадами (`MemoryService`, `ProfileRepository`, `Store`) |
| Права | не было | задел: `visibility`/`scope` + пустой `PolicyEngine` |
| Наследование | не было | merge-цепочка `user → task → session` + поле `source` |

---

## 5. Ключевые контракты (псевдокод)

```python
# 1. Единый контракт памяти
class MemoryLayer(ABC):
    layer_name: str
    scope: str
    def read(self, ctx) -> dict: ...
    def write(self, ctx, item) -> str: ...
    def as_prompt_block(self, ctx) -> str: ...

# 2. Явная маршрутизация (задание: «явно выбирали, что куда»)
class MemoryManager:
    def __init__(self, layers: dict[str, MemoryLayer]): ...
    def remember(self, layer: str, **item) -> str:   # лог «куда легло»
    def recall(self, layers: set[str], ctx) -> dict: # дозированная доставка

# 3. LLM-клиент (полиморфизм)
class LLMClient(ABC):
    def complete(self, messages, **params) -> str: ...

# 4. Prompt builder (блоки + бюджет)
class PromptBuilder:
    def build(self, ctx, deliver: set[str], budget: int) -> list[dict]: ...

# 5. Фасады (инкапсуляция)
class MemoryService: ...       # поверх Store + слоёв
class ProfileRepository: ...   # поверх SQLite
```

---

## 6. Порядок реализации (черновой, с учётом R1–R9)

1. Каркас (`МЕТА-ПРОМТ_den_N.md`).
2. `storage/store.py` (иерархия + неизменяемые сообщения) и `storage/db.py` (профили в SQLite).
3. `memory/base.py` (MemoryLayer + метаданные) → `short_term.py`, `working.py`, `long_term.py`, `profile.py`.
4. `MemoryManager` с явной маршрутизацией + лог «что куда легло».
5. `core/llm_client.py` (ABC + RouterAIClient + MockClient).
6. `core/prompt_builder.py` (блоки + дозированная доставка + бюджет).
7. `core/agent.py` (идентификация → интервью → загрузка памяти → диалог → явное сохранение).
8. `core/state_machine.py` (задел: стадии + переходы).
9. CLI/REPL: `--user`, команды `/memory` `/profile` `/tasks`, режим урезанной доставки.
10. Демонстрации задания: «какие данные куда», «влияние на ответы» (с/без слоя), интервью, resume.
11. Тесты (`MockClient`, без живого ключа) + `Проверка_Д11.md`.

---

## 7. Что НЕ берём в den_11 (и почему)

| Из arch_prim.md | Почему отложено |
|---|---|
| Полноценный RBAC/ReBAC/ABAC, OpenFGA, Zanzibar | enterprise-масштаб; в den_11 достаточно `visibility`/`scope` + задел `PolicyEngine`. Инварианты — отдельный день недели (куратор: в Д11 не нужен) |
| Tenant/multi-org изоляция, vault секретов, подписанный контекст запроса | нет мультиарендатора в учебном проекте; идентификация ограничена `user_id` |
| Векторная БД, retrieval, rerank | нет модели эмбеддингов; память — файлы по канону куратора |
| Подагенты с изоляцией контекста | вне задания Дня 11; возможны в следующих днях |
| Полный policy engine + фильтр инвариантов кодом | следующий день недели 3 (куратор: в Д11 не нужен) |
| Идемпотентность внешних действий (Jira и т.п.) | нет tool-вызовов в den_11; учесть, когда появятся инструменты |

---

## 8. Итог

Модернизация варианта А сводится к трём усилениям, которые не раздувают учебный день, но
делают архитектуру «правильной» по `arch_prim.md`:

1. **Полиморфизм и инкапсуляция**: единый `MemoryLayer` + `LLMClient`-интерфейс + фасады
   (`MemoryService`, `ProfileRepository`, `Store`) — агент не владеет данными напрямую.
2. **История ≠ состояние + метаданные**: неизменяемые сообщения с `parent_id`,
   пересчитываемая рабочая память, `scope/source/visibility/source_message_id` у каждого
   объекта памяти.
3. **Дозированная доставка и структурированный summary**: `PromptBuilder` с выбором слоёв
   и токен-бюджетом; память и summary — структурированные блоки со ссылками на исходные
   сообщения, а не «бесформенный текст».

Это сохраняет каноничную структуру хранения куратора и требования задания, но закладывает
чистый фундамент для следующих дней недели 3: state machine → инварианты → объединение в систему.
