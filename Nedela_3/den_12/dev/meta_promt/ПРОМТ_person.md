# ПРОМТ_person — Этап: персонализация (несколько профилей + профиль-роутер)

## 1. Цель и граница
Добавить персонализацию поверх готовой модели памяти (п.3 задания, чат куратора):
- **несколько профилей на пользователя**: профиль — «призма» под домен/задачу
  (пример куратора: Химик / Психолог / Экономист для постов; «покупки» → сборка корзины);
- **общий профиль-роутер**: выбирает конкретный профиль по тексту запроса
  («его можно побить на файлы, сделать общий профиль роутер и потом выбирать конкретный»);
- **профиль = пайплайн из скиллов**: упорядоченный список скиллов в профиле,
  инструкции скиллов подмешиваются в промт (оркестрация — декларативно);
- **профиль подключён к каждому запросу**: активный профиль привязан к сессии,
  его блок входит в каждый промт (порядок блоков не меняется);
- проверяемость: **ответы для разных профилей различаются**, видно **что учитывается
  автоматически** (роутер + дефолтный профиль).

Что НЕ делаем: не строим движок исполнения скиллов (мультиагентную оркестрацию) —
пайплайн декларативный: скиллы как инструкции в промте, реальная оркестрация —
следующие дни; не трогаем краткосрочную/рабочую/долговременную память — они
независимы от профилей (канон Федора Ч. из чата); не ломаем обратную совместимость:
существующий пользователь с одним профилем продолжает работать (его профиль
становится `default`); 19 пунктов приёмки остаются зелёными.

## 1.1 Алгоритм внедрения Персонализации (согласно архитектуре AI_9/ND/arch/arch_den_12.md)
Порядок — по зависимостям, снизу вверх: хранилище → память → роутер → агент → CLI →
тесты → документация. Каждый шаг завершается L1 (`$PY -m py_compile <файл>`) и НЕ ломает
зелёные тесты предыдущих шагов; контракты §3 — источник истины (в цикле отладки не
правятся, ≤5 итераций на модуль). Четыре фазы = четыре перехода на arch_den_12.md.

1- **Фаза A. Хранилище: несколько профилей** (arch §2.4–2.5; контракты §3.2, §3.3)
   - `storage/db.py`: схема `profiles(user_id, profile_id, profile_json, is_default,
     updated_at)` + **миграция** старой схемы (строки → `profile_id='default'`,
     `is_default=1`, одна транзакция, контроль через `PRAGMA table_info`);
     `save_profile/load_profile` с `profile_id`; новые `list_profiles/get_default/
     set_default`; `exists()` — семантика прежняя (есть хотя бы один профиль).
   - `storage/store.py`: зеркала `users/<id>/profiles/<pid>.json`; `users/<id>/profile.json`
     остаётся зеркалом `default` (обратная совместимость); `profiles_dir/profile_path/
     list_profiles/set_default_profile`.
   - Проверка фазы: `test_storage.py` зелёный **без правок**; roundtrip двух профилей
     независим; миграция тестовой БД старой схемы не теряет данные.
   - записать результат в Den_log.md; перечитать Алгоритм внедрения ПРОМТ_person.md

2- **Фаза B. Память и роутер** (arch §2.2–2.3, §2.6–2.7; контракты §3.4, §3.5)
   - `memory/base.py`: `MemoryContext(user_id, task="", session_id="", profile_id="")` —
     аддитивный параметр; `as_dict()` включает `profile_id`; вызовы с 3 аргументами работают.
   - `memory/profile.py`: read/write **активного** профиля (`ctx.profile_id or None`),
     merge-инвариант сохраняется; `as_prompt_block` += «Профиль: <name> (<profile_id>)»
     первой строкой, «Пайплайн скиллов:» (нумерованные инструкции `skills`), «Домен: <domain>».
   - `core/profile_router.py` (новый): `ProfileRouter.route()` (+2 за триггер,
     +1 за домен, победитель >0, ничья/ноль → None) и `explain()`; лог «[Роутер] …».
   - Проверка фазы: `test_memory.py`/`test_prompt.py` зелёные без правок; блок профиля
     содержит имя и скиллы; роутер детерминированный (без LLM, без живого ключа).
   - записать результат в Den_log.md; перечитать Алгоритм внедрения ПРОМТ_person.md

3- **Фаза C. Агент и CLI** (arch §2.10–2.11; контракты §3.6, §3.7)
   - `core/agent.py`: `active_profile`/`auto_route`/`router` в `__init__`;
     `switch_profile()` (лог «[Агент] активный профиль: <id>»); `build_context` передаёт
     `profile_id`; `respond()` при `auto_route` вызывает роутер **до** сборки промта.
   - `Kod.py`: `/profile list|show|use|new|route|auto` (голое `/profile` — как раньше);
     флаг `--profile <id>` (несуществующий → предупреждение и default); `/help` дополнен.
   - Проверка фазы: `test_agent.py` зелёный; L3 `$PY $TST/smoke.py` зелёный; ручной
     прогон команд `/profile …` в режиме `--mock`.
   - записать результат в Den_log.md; перечитать ПРОМТ_person.md

4- **Фаза D. Тесты, документация, приёмка** (arch §3.4, §4.3; §4–6)
   - `dev/tests_debug/unit/test_person.py` (новый) + `scenario_personalization` в
     `dev/tests_debug/scenario.py` (добавить в список `main()`).
   - `README.md` += раздел «Персонализация»; `dev/Проверка.md` += строки 20–22;
     отчёт `dev/logs_reports/stages/stage_E_person.md` (было→стало→проверка→статус).
   - Проверка фазы (гейт, без живого ключа): `$PY $TST/unit_runner.py` → все зелёные;
     `API_KEY=test-key $PY $TST/scenario.py` → SCENARIO OK;
     `API_KEY=test-key bash $TST/check_acceptance.sh` → 9 из 9; вывод и временные файлы —
     только `dev/tests_debug/.tmp/`; `users/` и корень проекта не загрязнены; прежние
     19 пунктов `dev/Проверка.md` без регрессии.
   - записать результат в Den_log.md; перечитать Алгоритм внедрения ПРОМТ_person.md


## 2. Вход (зависимости: storage/*, memory/*, core/*, Kod.py — готовы и зелёные)
- `Задание_Д12.txt` — п.3 (персонализация) и чат проекта (канон: роутер, пайплайн
  скиллов, профили-призмы, независимость памяти).
- `Nedela_3/Суть_N3.md` §3.4 (три рычага: стиль/констрейнты/контекст), §4.8 п.6
  (профиль — JSON в SQLite, зеркало).
- Текущие контракты: `storage/db.py` (ProfileRepository: один профиль на user_id),
  `storage/store.py` (зеркало `users/<id>/profile.json`), `memory/base.py`
  (MemoryContext), `memory/profile.py` (слой profile, merge-запись),
  `core/agent.py` (deliver, build_context), `core/prompt_builder.py` (BLOCK_ORDER),
  `Kod.py` (REPL, /profile).
- `dev/meta_promt/ПРОМТ_memory.md` §3.1 (инвариант слоя Profile: merge, не перезапись).

## 3. Контракты (точные сигнатуры — источник истины; в цикле отладки НЕ правятся)

### 3.1 Модель данных профиля (расширение JSON, обратно совместимое)
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
    {"name": "spec",    "instructions": "сначала составь спеку ответа"},
    {"name": "review",  "instructions": "проверь факты по домену"}
  ]
}
```
- `profile_id` — короткое имя профиля (safe_name); у первого/единственного профиля —
  `default`. Поля `domain`, `triggers`, `skills` опциональны (пустые — профиль
  работает как раньше: style/constraints/context).
- Старый профиль без `profile_id` трактуется как `default` (миграция, п.3.2).

### 3.2 `storage/db.py` — ProfileRepository: несколько профилей
```python
# Новая схема (создаётся идемпотентно; СТАРАЯ БД МИГРИРУЕТСЯ):
CREATE TABLE IF NOT EXISTS profiles (
    user_id TEXT NOT NULL,
    profile_id TEXT NOT NULL DEFAULT 'default',
    profile_json TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, profile_id)
)
# Миграция: если существующая таблица со старой схемой (user_id PRIMARY KEY) —
# перенести строки в новую как profile_id='default', is_default=1 (одна транзакция,
# данные не теряются; проверка схемы — по PRAGMA table_info).

class ProfileRepository:
    def save_profile(self, user_id, profile, profile_id="default") -> str
        # upsert; первый профиль пользователя автоматически is_default=1;
        # в profile_json дописывает profile_id; лог «[Хранилище] profile …»
    def load_profile(self, user_id, profile_id=None) -> dict | None
        # None/"" → дефолтный профиль; нет такого → None (битый JSON → None)
    def list_profiles(self, user_id) -> list    # [(profile_id, is_default: bool)], sorted
    def get_default(self, user_id) -> str | None
    def set_default(self, user_id, profile_id) -> bool   # False если профиля нет
    def exists(self, user_id) -> bool           # есть ХОТЯ БЫ один профиль (семантика прежняя)
```

### 3.3 `storage/store.py` — Store: зеркала профилей
```python
# Зеркало: users/<id>/profiles/<profile_id>.json (каталог создаётся автоматически).
# Совместимость: users/<id>/profile.json остаётся зеркалом профиля default
# (пишется при save_profile(profile_id='default'); чтение fallback — как раньше).
def profiles_dir(self, user_id) -> str
def profile_path(self, user_id, profile_id="default") -> str
def save_profile(self, user_id, profile, profile_id="default") -> str  # SQLite + зеркало
def load_profile(self, user_id, profile_id=None) -> dict | None        # SQLite → fallback JSON
def list_profiles(self, user_id) -> list       # делегирует репозиторию; без БД — по каталогу profiles/
def set_default_profile(self, user_id, profile_id) -> bool
```

### 3.4 `memory/base.py` + `memory/profile.py` — профиль в контексте
```python
class MemoryContext:
    def __init__(self, user_id, task="", session_id="", profile_id="")
    # profile_id — АДДИТИВНЫЙ параметр: все существующие вызовы (3 аргумента)
    # работают без изменений; as_dict() включает profile_id.

class Profile(MemoryLayer):   # layer_name/scope не меняются
    def read(self, ctx)       # store.load_profile(ctx.user_id, ctx.profile_id or None)
    def write(self, ctx, item)  # merge в АКТИВНЫЙ профиль (инвариант merge сохраняется)
    def as_prompt_block(self, ctx) -> str
        # прежние строки (Имя/Стиль/Ограничения/Контекст) + новые:
        # «Профиль: <name> (<profile_id>)» — первой строкой;
        # «Пайплайн скиллов:» + нумерованные инструкции skills (если есть);
        # «Домен: <domain>» (если есть)
```

### 3.5 `core/profile_router.py` — новый модуль: профиль-роутер
```python
class ProfileRouter:
    def __init__(self, store, log=None)
    def route(self, user_id, text) -> str | None
    # Оценка: +2 за вхождение каждого триггера (регистронезависимо), +1 за вхождение
    # domain в текст; победитель = профиль с максимумом (>0); ничья/ноль → None
    # (остаёмся на текущем/дефолтном). Решение логируется:
    # «[Роутер] запрос → профиль <id> (счёт N)» или «[Роутер] без совпадений → default».
    def explain(self, user_id, text) -> str    # человекочитаемый разбор для /profile route
```

### 3.6 `core/agent.py` — активный профиль и авто-роутинг
```python
# В __init__: self.active_profile = None (None → default), self.auto_route = False,
# self.router = ProfileRouter(store, log) — только если у store есть profile_repo.
def switch_profile(self, profile_id) -> bool
    # проверка существования через store.list_profiles; установка active_profile;
    # лог «[Агент] активный профиль: <id>»; False если профиля нет
def build_context(self, query)   # ctx = MemoryContext(user_id, task, session_id,
                                 #                     profile_id=self.active_profile or "")
def respond(self, user_message)  # если self.auto_route: candidate = router.route(...);
                                 # candidate и != active → switch_profile(candidate)
                                 # ПЕРЕД сборкой промта (профиль подключён к каждому запросу)
```

### 3.7 `Kod.py` — команды REPL и флаги
| Команда | Назначение |
|---|---|
| `/profile` | активный профиль (как раньше — обратно совместимо) |
| `/profile list` | профили пользователя: `* default`, `> активный` |
| `/profile show <id>` | полный JSON профиля |
| `/profile use <id>` | переключить активный профиль сессии |
| `/profile new <id>` | мини-интервью: name, domain, triggers (через запятую), style, constraints, context → save_profile |
| `/profile route <текст>` | показать решение роутера (explain), НЕ переключая |
| `/profile auto on\|off` | авто-роутинг по каждому запросу |

Флаг: `--profile <id>` — активный профиль на старте (после идентификации;
несуществующий → предупреждение и default). Справка `/help` дополняется.

## 4. Выход (scope записи)
- `storage/db.py`, `storage/store.py` (расширение), `memory/base.py` (аддитивный
  параметр), `memory/profile.py` (расширение), `core/profile_router.py` (новый),
  `core/agent.py` (расширение), `Kod.py` (команды/флаг).
- Тесты: `dev/tests_debug/unit/test_person.py` (новый); `dev/tests_debug/scenario.py`
  — новый сценарий `scenario_personalization` в списке main().
- Документация: `README.md` — раздел «Персонализация» (профили, роутер, пайплайн);
  `dev/Проверка.md` — новые строки 20–22; `dev/tests_debug/check_acceptance.sh` —
  без изменений (test_person.py подхватывается unit_runner автоматически,
  новый сценарий — проверкой [6]).

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — все тесты зелёные, включая `test_person.py` (exit 0);
`API_KEY=test-key $PY $TST/scenario.py` — SCENARIO OK; гейт
`API_KEY=test-key bash $TST/check_acceptance.sh` — 9 из 9. Проверяется:
- мультипрофильный roundtrip: два профиля сохраняются/читаются независимо, list_profiles
  возвращает оба, get_default/set_default работают;
- миграция: БД старой схемы (один профиль) после открытия даёт профиль `default`,
  данные не потеряны; exists() семантику не изменил;
- обратная совместимость: load_profile(user_id) без profile_id = дефолтный профиль;
  MemoryContext с тремя аргументами работает;
- роутер: совпадение триггеров выбирает правильный профиль; нет совпадений → None;
  explain содержит разбор;
- промт: блок profile содержит имя активного профиля и пайплайн скиллов;
  ДВА разных профиля на один запрос → РАЗНЫЕ блоки/ответы (требование задания
  «ответы для разных профилей»);
- агент: switch_profile меняет активный профиль; auto_route переключает профиль
  по запросу до сборки промта;
- сценарий `scenario_personalization`: пользователь с профилями «Химик» и «Экономист»
  → один и тот же запрос даёт разный состав промта (MockClient отражает блоки);
  лог содержит «[Роутер]» и «[Агент] активный профиль».

## 6. Правила дня
Отчёт — `dev/logs_reports/stages/stage_E_person.md` (было→стало→проверка→статус).
Цикл отладки — §6.1 START-PROMT (контракты §3 в цикле НЕ править; ≤5 итераций на
модуль). Приёмка — п.3 задания (профиль/предпочтения/подключение к запросу) +
требования чата (несколько профилей, роутер, пайплайн скиллов) + прежние 19 пунктов
`dev/Проверка.md` (не регрессировать). Naming — без признаков дня в именах
(`PLAN_naming.md`); временные файлы и вывод прогонов — только `dev/tests_debug/.tmp/`;
тесты без живого ключа (API_KEY=test-key / MockClient); коммиты — только по явной
команде пользователя.
