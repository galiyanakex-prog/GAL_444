# ПРОМТ_den11_memory — создание модели памяти (memory/*)

## 1. Цель и граница
Создать явную модель памяти: единый контракт `MemoryLayer` (ABC) + метаданные + задел
`PolicyEngine`; 4 класса-слоя (ShortTermMemory, WorkingMemory, LongTermMemory, Profile);
роутер `MemoryManager` с явной маршрутизацией `remember(layer, ...)` (лог «что куда
легло») и дозированной доставкой `recall/build_blocks` (набор слоёв — параметр).

Что НЕ делаем: не реализуем рабочий фильтр инвариантов (только интерфейс `PolicyEngine`
и поля `visibility`/`scope` — п.18); не обращаемся к файлам напрямую — только через
контракт `storage.Store`.

## 2. Вход (зависимость: `storage/store.py` и `storage/db.py` уже готовы)
- `ND/arch/arch_den_11_plan_2.md` §3.2 (модель памяти и метаданные).
- `Nedela_3/Суть_N3.md` §4.2 (содержимое каждого типа) и §4.8 (канон).
- `ND/arch/arch_den_11.md` §2.2 (таблица классов).

## 3. Контракты (неизменяемые — источник истины; в цикле отладки НЕ правится)
```python
# memory/base.py
class MemoryContext:
    def __init__(self, user_id: str, task: str = "", session_id: str = "")
    def as_dict(self) -> dict

class MemoryItem:           # метаданные у каждого объекта памяти (arch_prim R5)
    def __init__(self, content, source="unknown", scope="", owner="",
                 visibility="private", source_message_id="", role="")
    # source: user|model|document|system; scope: user|task|session;
    # visibility: private (задел); role: user|assistant (для краткосрочной)
    def to_dict(self) -> dict

class MemoryLayer(ABC):
    layer_name: str    # short_term | working | long_term | profile
    scope: str         # session | task | user
    def __init__(self, store, log=None)
    def read(self, ctx: MemoryContext) -> dict
    def write(self, ctx: MemoryContext, item: MemoryItem) -> str  # «куда легло»
    def as_prompt_block(self, ctx: MemoryContext) -> str

class PolicyEngine:     # пустой интерфейс-задел (п.18): рабочий фильтр — следующие дни
    pass

# memory/manager.py
LAYER_ORDER = ("profile", "long_term", "working", "short_term")
def default_layers(store, log=None) -> dict[str, MemoryLayer]

class MemoryManager:
    def __init__(self, layers: dict, log=None)
    def remember(self, layer: str, ctx, content=None, source="unknown",
                 source_message_id="", **item) -> str   # лог «[Память] layer ← … → путь»
    def recall(self, layers: set, ctx) -> dict          # дозированная доставка
    def build_blocks(self, deliver: set, ctx) -> dict   # в каноническом LAYER_ORDER
    def report(self, ctx) -> str                        # снимок «что где лежит» для /memory
```

### 3.1 Инварианты четырёх слоёв (обязательны к реализации)
- **ShortTermMemory** (`layer_name="short_term", scope="session"`): append-only.
  Сообщения НЕИЗМЕНЯЕМЫ: новое дописывается в конец `session.json`, `id="M<N>"`,
  `parent_id` = id предыдущего (корень None). `as_prompt_block` отдаёт окно последних
  `SHORT_TERM_WINDOW=10` сообщений.
- **WorkingMemory** (`layer_name="working", scope="task"`): ПЕРЕСЧИТЫВАЕМОЕ состояние
  задачи, НЕ лог сообщений. Поля: description, refs (список, append), lifecycle_summary,
  decisions/constraints/facts/open_questions (списки со ссылкой source_message_id),
  current_state (стадия state machine).
- **LongTermMemory** (`layer_name="long_term", scope="user"`): profile_ref (ССЫЛКА на
  профиль, не сам профиль), tasks (список, со ссылками), decisions (со статусом
  «выполнена/не выполнена»), knowledge.
- **Profile** (`layer_name="profile", scope="user"`): style + constraints + context
  (три блока персонализации). Запись — MERGE, не перезапись целиком. Хранится как JSON
  в SQLite (ProfileRepository), зеркало profile.json пишет Store.

## 4. Выход (scope записи — только memory/*)
- `memory/__init__.py`, `memory/base.py`, `memory/short_term.py`, `memory/working.py`,
  `memory/long_term.py`, `memory/profile.py`, `memory/manager.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — `test_memory.py` зелёный (exit 0). Проверяется: 4 класса с
разными `layer_name`/своими файлами; лог «куда легло» при remember; дозированная
доставка (build_blocks не подмешивает невыбранный слой); неизменяемость + parent_id;
профиль merge; report содержит все слои.

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_03_memory.md` (✅). Цикл отладки — §6.1.
Приёмка — §7 п.2 (3 типа + профиль), п.4 (явная маршрутизация), п.5 (дозированная
доставка), п.9 (блоки), п.13 (неизменяемость/parent_id, рабочая ≠ лог), п.18 (PolicyEngine-задел).