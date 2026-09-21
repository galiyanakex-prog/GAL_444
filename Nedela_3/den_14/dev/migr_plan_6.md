# migr_plan_6.md — рабочий план этапа M6 «Тесты и отладка»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_14` на
> целевую архитектуру `Nedela_3/den_14/arch_den_14.md`. Разворачивает строку этапа **M6** из
> `migr_plan.md` §4 в конкретные правки и проверки.
> **Конец этого этапа — автоматический гейт в этап M7** (`migr_plan_7.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_14.md` §3.3, `Задание_Д14.txt`.

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M6** — Тесты и отладка |
| Рабочий план | `dev/migr_plan_6.md` (этот файл) |
| Зависит от | **M1–M5** |
| Открывает | `dev/migr_plan_7.md` (M7 — Документация) |
| Основные артефакты | `dev/tests_debug/unit/test_invariants.py`, обновлённые `scenario.py` / `smoke.py` / `check_acceptance.sh` |
| Живой ключ | **Не нужен** (`API_KEY=test-key` / `MockClient`) |

**Цель этапа.** Закрыть тестовый контур `arch_den_14.md` §3.3: юнит-тесты инвариантов,
сквозной сценарий конфликта, смоук и гейт приёмки — всё детерминированно.

---

## 1. Вход и предусловия

- Реализация M1–M5.
- Существующий `dev/tests_debug/` (`unit_runner.py`, `smoke.py`, `scenario.py`,
  `check_acceptance.sh`, `unit/`, `scenario/`).
- `arch_den_14.md` §3.3 (перечень тестов), §4.3 (критерии 26–30).

**Предусловия:** активное `.venv`; временные файлы — **только** в `dev/tests_debug/.tmp/`
(в `.gitignore`); `users/` проекта тестами не трогается.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 6.1 — `unit/test_invariants.py`: базовые тесты из задания
```python
def test_allowed_action():
    action = ProposedAction(description="Добавить новый endpoint", technology="django")
    violations = check_invariants(action, constraints)
    assert violations == []

def test_forbidden_framework():
    action = ProposedAction(description="Перейти на FastAPI", technology="fastapi")
    violations = check_invariants(action, constraints)
    assert len(violations) == 1
    assert "framework.django" in violations[0]

def test_forbidden_dependency():
    action = ProposedAction(description="Установить библиотеку", adds_dependency=True)
    violations = check_invariants(action, constraints)
    assert len(violations) == 1
```
**Ожидаемый результат:** три базовых теста задания зелёные (на заглушках, без живого ключа).

### Шаг 6.2 — Дополнительные юнит-кейсы
- **несколько нарушений одновременно**: `technology="fastapi"` **и** `adds_dependency=True`
  → 2 нарушения в одном списке;
- **инварианты загружаются после перезапуска**: save → load → набор равен;
- **очистка истории не удаляет инварианты**: очистить `session.json` → `invariants.json` на
  месте, проверка по-прежнему блокирует;
- **запрещённое действие не вызывает инструмент**: счётчик вызовов заглушки == 0;
- **агент явно называет нарушенное правило**: текст отказа содержит `id`;
- **при конфликте предлагается допустимая альтернатива**: текст отказа содержит альтернативу;
- **изменение требует подтверждения**: `update_invariant(authorized=False)` → `PermissionError`;
  `authorized=True` → применено;
- **`active=False` снимает блокировку**: выключенный инвариант не даёт нарушений;
- **`severity="warning"`**: действие выполняется, в лог пишется ворнинг.
**Ожидаемый результат:** расширенный набор кейсов зелёный.

### Шаг 6.3 — `scenario.py` + `scenario_invariant_conflict` (L4, сквозной)
Сценарий по `arch_den_14.md` §3.3:
```text
/invariant add framework.django architecture "Использовать Django"
→ запрос «перепиши API на FastAPI» → агент ОТКАЗЫВАЕТ, называет framework.django,
  предлагает альтернативу
→ /check "перейти на FastAPI" → показывает нарушение
→ /invariant set framework.django "..." --yes → правило изменено
→ повторный запрос проходит
```
Лог содержит строки `[Инварианты] …`.
**Ожидаемый результат:** сценарий воспроизводит конфликт и его разрешение.

### Шаг 6.4 — `smoke.py` (L3)
Полный цикл in-process + CLI subprocess; логи изолированы в `.tmp/`.
**Ожидаемый результат:** смоук проходит без живого ключа.

### Шаг 6.5 — `check_acceptance.sh` (гейт приёмки)
- 11 проверок; временный каталог `$TST/.tmp/acc_$$`;
- `users/` проекта **не трогается**;
- добавить проверки, связанные с инвариантами (26–30 — на этапе M7/M8 в Проверке).
**Ожидаемый результат:** гейт `11 из 11`.

### Шаг 6.6 — Прогон всего контура
```bash
export API_KEY=test-key
python dev/tests_debug/unit_runner.py
python dev/tests_debug/scenario.py
python dev/tests_debug/smoke.py
bash dev/tests_debug/check_acceptance.sh
```
**Ожидаемый результат:** L2/L3/L4/гейт зелёные, без живого ключа.

---

## 3. Выход этапа

- `dev/tests_debug/unit/test_invariants.py`.
- Обновлённые `scenario.py` (+ `scenario_invariant_conflict`), `smoke.py`, `check_acceptance.sh`.
- Запись этапа **M6** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M6→M7

Гейт **зелёный**, если (всё без живого ключа):
- [ ] `unit_runner.py` — все тесты зелёные (вкл. `test_invariants.py`);
- [ ] `scenario.py` — 8 сценариев (вкл. `scenario_invariant_conflict`);
- [ ] `check_acceptance.sh` — **11 из 11**;
- [ ] временные файлы только в `.tmp/`; `users/` проекта не изменён;
- [ ] прежние 25 критериев — без регрессии.

**Зелёный** → запись M6 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** → открыть
`migr_plan_7.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап M6 остаётся открыт.

---

## 5. Запись в `migr_log.md`

```text
## Этап M6 — Тесты и отладка
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: тестовый контур без тестов инвариантов
- Стало: unit/test_invariants.py + scenario_invariant_conflict + обновлённые smoke/check_acceptance
- Проверка: unit_runner / scenario (8) / smoke / check_acceptance (11/11), exit-коды
- Артефакты: dev/tests_debug/*
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M6→M7: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать `dev/migr_plan.md`, затем **M7** по `dev/migr_plan_7.md` (документация).
