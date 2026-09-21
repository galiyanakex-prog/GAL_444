# migr_plan_1.md — рабочий план этапа M1 «Ядро инвариантов»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_14` на
> целевую архитектуру `Nedela_3/den_14/arch_den_14.md`. Разворачивает строку этапа **M1** из
> `migr_plan.md` §4 в конкретные правки и проверки.
> **Конец этого этапа — автоматический гейт в этап M2** (`migr_plan_2.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_14.md` §2.2–2.4, §2.10, `Задание_Д14.txt`.

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M1** — Ядро инвариантов |
| Рабочий план | `dev/migr_plan_1.md` (этот файл) |
| Зависит от | **M0** (baseline зелёный, точки внедрения зафиксированы) |
| Открывает | `dev/migr_plan_2.md` (M2 — Хранение инвариантов) |
| Основной артефакт | `core/invariants.py` (+ экспорт в `core/__init__.py` при необходимости) |
| Живой ключ | **Не нужен** (чистые dataclass'ы + детерминированная проверка) |

**Цель этапа.** Реализовать `core/invariants.py` — модель и программную проверку инвариантов
по контрактам `arch_den_14.md` §2.2–2.4 и §2.10.

---

## 1. Вход и предусловия

- Существующий пакет `core/` (контракты дней 11–13 **не менять**).
- Результат M0: точки внедрения зафиксированы.
- `arch_den_14.md` §2.2 (модель), §2.3 (`InvariantChecker`), §2.4 (каталог), §2.10
  (`update_invariant`).

**Предусловия:** активное `.venv`; `core/invariants.py` ещё не существует.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 1.1 — Создать `core/invariants.py` с моделью
Реализовать dataclass'ы (имена — как в `Задание_Д14.txt`, канон):
```python
from dataclasses import dataclass, field

@dataclass
class Invariant:
    id: str                       # "framework.django"
    description: str              # "Использовать Django, а не FastAPI или Flask"
    category: str                 # stack | architecture | technical | business
    severity: str = "error"       # error | warning
    active: bool = True

@dataclass
class ConstraintSet:
    invariants: list[Invariant] = field(default_factory=list)

    def active(self) -> list[Invariant]:
        return [i for i in self.invariants if i.active]

    def by_id(self, invariant_id: str) -> Invariant | None: ...

@dataclass
class ProposedAction:
    description: str
    technology: str | None = None
    adds_dependency: bool = False
    changes_database_schema: bool = False
    # расширяемые поля под конкретные инварианты (target_file, package, ...)
```
**Ожидаемый результат:** модель `Invariant` / `ConstraintSet` / `ProposedAction` создана.
`ConstraintSet` — **отдельная сущность**, не часть `TaskState` и не часть истории диалога.

### Шаг 1.2 — Реализовать `InvariantChecker` (интерфейс ABC + реализация)
```python
class InvariantChecker(ABC):
    @abstractmethod
    def check(self, action: ProposedAction, constraints: ConstraintSet) -> list[str]: ...

class RuleBasedChecker(InvariantChecker):
    def check(self, action, constraints) -> list[str]:
        violations: list[str] = []
        for inv in constraints.active():
            if inv.id == "framework.django" and action.technology == "fastapi":
                violations.append(f"Нарушен invariant {inv.id}: проект должен использовать Django.")
            if inv.id == "dependencies.no-new" and action.adds_dependency:
                violations.append(f"Нарушен invariant {inv.id}: нельзя добавлять новые зависимости.")
            if inv.id == "database.no-schema-changes" and action.changes_database_schema:
                violations.append(f"Нарушен invariant {inv.id}: нельзя изменять схему базы данных.")
            # ... остальные правила по каталогу
        return violations
```
Требования:
- `InvariantChecker` — **интерфейс (ABC)**; конкретная реализация `RuleBasedChecker` инжектится
  в `Agent` (полиморфизм, тестируемость);
- проверка **не зависит от LLM** (детерминированные правила: поля `ProposedAction`/паттерны);
- **несколько нарушений одновременно** (не только первое);
- учитывать `active` (выключенные не проверяются) и `severity` (`error` — блокирует,
  `warning` — ворнинг).
**Ожидаемый результат:** `check()` возвращает список нарушений; пустой список = разрешено.

### Шаг 1.3 — Реализовать `update_invariant` (отдельная авторизованная операция)
```python
def update_invariant(constraints, invariant_id, new_description, authorized=False) -> None:
    if not authorized:
        raise PermissionError("Изменение инвариантов требует отдельного подтверждения.")
    for inv in constraints.invariants:
        if inv.id == invariant_id:
            inv.description = new_description
            return
    raise KeyError(f"Инвариант не найден: {invariant_id}")
```
**Ожидаемый результат:** без `authorized=True` — `PermissionError`; отсутствующий id — `KeyError`.

### Шаг 1.4 — Каталог инвариантов-примера (`arch_den_14.md` §2.4)
Зафиксировать фабрику/хелпер примера набора (Python-проект, канон задания):
| id | description | category | severity |
|---|---|---|---|
| `stack.python` | Использовать только Python 3.12 | stack | error |
| `framework.django` | Использовать Django, а не FastAPI или Flask | architecture | error |
| `dependencies.no-new` | Не добавлять новые внешние зависимости | technical | error |
| `database.no-schema-changes` | Не изменять схему базы данных | business | error |

**Ожидаемый результат:** пример набора воспроизводим одной функцией (используется в тестах M6).

### Шаг 1.5 — Экспорт модуля (при необходимости)
Если в `core/__init__.py` принят ре-экспорт публичных классов — добавить `Invariant`,
`ConstraintSet`, `ProposedAction`, `InvariantChecker`, `RuleBasedChecker`, `update_invariant`.
**Ожидаемый результат:** классы доступны для импорта из `core`.

---

## 3. Выход этапа

- `core/invariants.py` (модель + проверка + `update_invariant` + каталог примера).
- При необходимости — обновлённый `core/__init__.py`.
- Запись этапа **M1** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M1→M2

Примитив-смоук (инлайн или в `python -c`), без живого ключа:
```bash
python - <<'PY'
from core.invariants import Invariant, ConstraintSet, ProposedAction, RuleBasedChecker, update_invariant
cs = ConstraintSet(invariants=[Invariant(id="framework.django", description="Использовать Django", category="architecture")])
chk = RuleBasedChecker()
assert chk.check(ProposedAction(description="Добавить endpoint", technology="django"), cs) == []
assert chk.check(ProposedAction(description="Перейти на FastAPI", technology="fastapi"), cs) != []
try:
    update_invariant(cs, "framework.django", "x", authorized=False); raise SystemExit("FAIL")
except PermissionError:
    pass
print("M1 OK")
PY
```
Гейт **зелёный**, если:
- [ ] модуль `core/invariants.py` импортируется без ошибок;
- [ ] разрешённое действие → `[]`; запрещённое (`technology="fastapi"` при `framework.django`)
      → нарушение с `id` в тексте;
- [ ] `update_invariant(authorized=False)` → `PermissionError`;
- [ ] несколько нарушений возвращаются одновременно;
- [ ] контракты дней 11–13 не затронуты.

**Зелёный** → запись M1 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** → открыть
`migr_plan_2.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап M1 остаётся открыт.

---

## 5. Запись в `migr_log.md`

```text
## Этап M1 — Ядро инвариантов
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: слой инвариантов отсутствует
- Стало: core/invariants.py (Invariant/ConstraintSet/ProposedAction/InvariantChecker/update_invariant + каталог)
- Проверка: примитив-смоук (разрешённое → [], запрещённое → нарушение, authorized=False → PermissionError), exit-код
- Артефакты: core/invariants.py [, core/__init__.py]
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M1→M2: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать `dev/migr_plan.md`, затем **M2** по `dev/migr_plan_2.md` (хранение инвариантов в
`storage/store.py`, файл `invariants.json`).
