# migr_plan_2.md — рабочий план этапа M2 «Хранение инвариантов»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_14` на
> целевую архитектуру `Nedela_3/den_14/arch_den_14.md`. Разворачивает строку этапа **M2** из
> `migr_plan.md` §4 в конкретные правки и проверки.
> **Конец этого этапа — автоматический гейт в этап M3** (`migr_plan_3.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_14.md` §2.5–2.6, `Задание_Д14.txt`.

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M2** — Хранение инвариантов |
| Рабочий план | `dev/migr_plan_2.md` (этот файл) |
| Зависит от | **M1** (ядро `core/invariants.py`) |
| Открывает | `dev/migr_plan_3.md` (M3 — Инжект в промт) |
| Основной артефакт | методы в `storage/store.py`; файл `users/<id>/tasks/<task>/invariants.json` |
| Живой ключ | **Не нужен** (сериализация/чтение файлов) |

**Цель этапа.** Отделить инварианты от диалога **физически** — собственный файл `invariants.json`
в иерархии `users/`, переживающий очистку истории и перезапуск процесса.

---

## 1. Вход и предусловия

- Существующий `storage/store.py` (фасад хранилища; контракт дней 11–13 **не менять** —
  только **добавить** методы).
- `core/invariants.py` (M1).
- `arch_den_14.md` §2.5 (снимок `invariants.json`), §2.6 (иерархия хранения).

**Предусловия:** активное `.venv`; файла `invariants.json` в иерархии ещё нет.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 2.1 — Метод пути `invariants_path`
Добавить в фасад `storage/store.py`:
```python
def invariants_path(self, user_id, task_name) -> str
    # -> users/<id>/tasks/<task>/invariants.json
```
Фасад знает путь; `Agent` — нет (инкапсуляция через фасад).
**Ожидаемый результат:** метод возвращает корректный абсолютный путь.

### Шаг 2.2 — Метод чтения `read_invariants`
```python
def read_invariants(self, user_id, task_name) -> dict | None
    # None — набора ещё нет (не ошибка)
```
**Ожидаемый результат:** отсутствующий файл → `None`; существующий → dict.

### Шаг 2.3 — Метод записи `write_invariants`
```python
def write_invariants(self, user_id, task_name, data: dict) -> str
    # создаёт каталоги при необходимости, пишет JSON, возвращает путь
```
**Ожидаемый результат:** сейв создаёт/перезаписывает `invariants.json`.

### Шаг 2.4 — Сериализация `ConstraintSet` ↔ JSON
Реализовать (де)сериализацию по снимку `arch_den_14.md` §2.5:
```json
{
  "invariants": [
    {"id": "stack.python", "description": "Использовать только Python 3.12",
     "category": "stack", "severity": "error", "active": true},
    {"id": "framework.django", "description": "Использовать Django, а не FastAPI или Flask",
     "category": "architecture", "severity": "error", "active": true},
    {"id": "dependencies.no-new", "description": "Не добавлять новые внешние зависимости",
     "category": "technical", "severity": "error", "active": true},
    {"id": "database.no-schema-changes", "description": "Не изменять схему базы данных",
     "category": "business", "severity": "error", "active": true}
  ]
}
```
**Ожидаемый результат:** round-trip `ConstraintSet → JSON → ConstraintSet` без потерь.

### Шаг 2.5 — Устойчивость (битый/отсутствующий файл)
Правила:
- отсутствующий `invariants.json` → **пустой набор** (все действия разрешены, как в днях 11–13);
- битый JSON / несоответствие схеме → **не роняет приложение**, пустой набор + ворнинг в лог;
- **очистка истории диалога не удаляет инварианты** (разные файлы: `session.json` ≠
  `invariants.json`).
**Ожидаемый результат:** приложение устойчиво к повреждённому файлу.

### Шаг 2.6 — Зафиксировать иерархию хранения (`arch_den_14.md` §2.6)
Подтвердить итоговое дерево (без правки наследия):
```text
users/<user_id>/
├── profile.json
├── profiles/
├── long_term_memory.json
└── tasks/<task_name>/
    ├── invariants.json          # ← НОВОЕ: ConstraintSet (неизменяемые правила задачи)
    ├── task_state.json
    ├── working_memory.json
    ├── sessions_resume.md
    └── sessions/<session_id>/
        └── session.json
```
Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
состояние памяти задачи; `task_state.json` — жизненный цикл; `invariants.json` —
неизменяемые правила (4 разные сущности, 4 файла).

---

## 3. Выход этапа

- Новые методы в `storage/store.py` (`invariants_path` / `read_invariants` / `write_invariants`).
- Сериализация `ConstraintSet` ↔ JSON.
- Файл `invariants.json` появляется в иерархии `users/` при сейве.
- Запись этапа **M2** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M2→M3

Проверка round-trip и независимости (временный каталог — только в `.tmp/`, `users/` проекта не
трогать):
```bash
python - <<'PY'
import json, os, tempfile
from core.invariants import Invariant, ConstraintSet
# сохранить набор в tmp → прочитать → сравнить
# удалить session.json → убедиться, что invariants.json на месте
print("M2 OK")
PY
```
Гейт **зелёный**, если:
- [ ] `write_invariants` → `read_invariants` даёт **равный** набор (round-trip);
- [ ] отсутствующий файл → пустой набор (не ошибка);
- [ ] удаление `session.json` **не** затрагивает `invariants.json`;
- [ ] битый `invariants.json` не роняет приложение (пустой набор + ворнинг);
- [ ] контракты `storage/db.py` и наследия не изменены.

**Зелёный** → запись M2 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** → открыть
`migr_plan_3.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап M2 остаётся открыт.

---

## 5. Запись в `migr_log.md`

```text
## Этап M2 — Хранение инвариантов
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: инварианты не хранятся отдельно
- Стало: storage/store.py (invariants_path/read/write) + invariants.json в users/<id>/tasks/<task>/
- Проверка: round-trip save→load; отсутствие файла → пустой набор; удаление session.json не влияет, exit-код
- Артефакты: storage/store.py
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M2→M3: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать `dev/migr_plan.md`, затем **M3** по `dev/migr_plan_3.md` (блок `invariants` в
`core/prompt_builder.py`).
