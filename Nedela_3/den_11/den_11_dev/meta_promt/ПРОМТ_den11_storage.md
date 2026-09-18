# ПРОМТ_den11_storage — создание слоя хранилища (storage/*)

## 1. Цель и граница
Создать фасад хранилища, реализующий каноническую иерархию куратора (арх §2.3,
Суть_N3 §4.8 п.3):
```
users/<user_id>/
├── profile.json                 # ЗЕРКАЛО профиля; авторитет — SQLite (ProfileRepository)
├── long_term_memory.json        # ссылка на профиль, задачи (со ссылками), решения, знания
└── tasks/<task_name>/
    ├── working_memory.json      # описание, refs, lifecycle_summary, decisions/constraints/facts/open_questions
    ├── sessions_resume.md       # резюме сессий (только данные о задаче)
    └── sessions/<session_id>/
        └── session.json         # {messages:[{id,parent_id,role,content,created_at}]}
```
Плюс `ProfileRepository`: профили (JSON) в БД SQLite.

Что НЕ делаем: не пишем слои памяти (memory/*), не трогаем LLM-клиент и промты.

## 2. Вход (уже готово ЗАВИСИМОСТЕЙ НЕТ — это базовый слой)
- `ND/arch/arch_den_11.md` §2.3 (иерархия) и §2.2 (таблица «что где лежит»).
- `Nedela_3/Суть_N3.md` §4.8 п.3 и п.6 (канон структуры; профиль — JSON в SQLite,
  в long_term_memory.json профиль имеет вид ССЫЛКИ).
- Донор `Nedela_2/den_10/den_10_Kod.py` — только за паттерном чтения/записи JSON.

## 3. Контракты (точные сигнатуры — источник истины для memory/*)
```python
def safe_name(name: str) -> str
# нормализует имя каталога/файла: допустимы [0-9A-Za-zА-Яа-яЁё_-], пробелы → «_»,
# прочие символы заменяются пробелом; пустой результат → "task"; длина ≤ 80.

class ProfileRepository:
    def __init__(self, db_path: str, log=None)
    def _init_db(self)      # CREATE TABLE IF NOT EXISTS profiles(
                            #   user_id TEXT PRIMARY KEY, profile_json TEXT NOT NULL,
                            #   updated_at TEXT NOT NULL)
    def save_profile(self, user_id: str, profile: dict) -> str   # upsert + лог
    def load_profile(self, user_id: str) -> dict | None          # None, если нет/битый
    def exists(self, user_id: str) -> bool

class Store:
    def __init__(self, root: str, profile_repo=None, log=None)
    # root — каталог users/ (создаётся при необходимости); log — callable(line).
    def user_dir(self, user_id) -> str
    def task_dir(self, user_id, task_name) -> str
    def session_dir(self, user_id, task_name, session_id) -> str
    def ensure_user(self, user_id) -> str
    def ensure_task(self, user_id, task_name) -> str      # создаёт и tasks/<task>/sessions/
    def ensure_session(self, user_id, task_name, session_id) -> str
    def save_profile(self, user_id, profile: dict) -> str  # SQLite + зеркало profile.json
    def load_profile(self, user_id) -> dict | None         # SQLite → fallback JSON
    def long_term_path(self, user_id) -> str
    def read_long_term(self, user_id) -> dict              # дефолт: {profile_ref, tasks[], decisions[], knowledge[]}
    def write_long_term(self, user_id, data) -> str
    def working_path(self, user_id, task_name) -> str
    def read_working(self, user_id, task_name) -> dict     # дефолт канонических полей
    def write_working(self, user_id, task_name, data) -> str
    def sessions_resume_path(self, user_id, task_name) -> str
    def read_sessions_resume(self, user_id, task_name) -> str   # "" если нет
    def write_sessions_resume(self, user_id, task_name, text) -> str
    def session_path(self, user_id, task_name, session_id) -> str
    def read_session(self, user_id, task_name, session_id) -> dict  # дефолт {messages:[]}
    def write_session(self, user_id, task_name, session_id, data) -> str
    def list_tasks(self, user_id) -> list                  # имена каталогов tasks/, sorted
    def read_json(self, filepath, default)                 # не падать при битом/отсутствии
    def write_json(self, filepath, data) -> str            # mkdirs + JSON ensure_ascii=False indent=2
```

Схема `session.json` (критично для п.13 «неизменяемые сообщения с parent_id»):
`{messages: [{id: "M<N>", parent_id: "<id-предыдущего|None>", role: "user|assistant",
content: str, created_at: "YYYY-MM-DD HH:MM:SS", ...метаданные}]}`.

## 4. Выход (scope записи — только storage/*)
- `storage/__init__.py` (пустой), `storage/store.py`, `storage/db.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — тесты `test_storage.py` зелёные (exit 0). Проверяется:
иерархия создаётся по каноническим путям; профиль roundtrip через SQLite; long_term/
working/session roundtrip с гарантированными каноническими полями; `safe_name`
нормализует; `list_tasks` возвращает имена. `pytest` НЕ обязателен (в venv отсутствует).

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_02_storage.md` (было→стало→проверка→статус ✅).
Цикл отладки — §6.1 START-PROMT (не менять контракты `memory/base.py` и
`core/llm_client.py`). Приёмка — §7 п.3 (иерархия), п.7 (дерево для нового ID),
п.13 (session.json с parent_id), п.17 (артефакты — только в $TST или /tmp).