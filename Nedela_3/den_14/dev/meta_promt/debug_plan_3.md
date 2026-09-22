# debug_plan_3.md — рабочий план этапа D3 «Косметика ядра: окно, ROLES, identify, импорты»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** дебага проекта `den_14`
> по плану-эталону `dev/meta_promt/debug_plan.md`. Разворачивает этап **D3** из
> `debug_plan.md` §5 в конкретные правки и проверки. Закрывает проблемы **A4–A7**.
> **Конец этого этапа — автоматический гейт в этап D4** (`debug_plan_4.md`).
> Источники: `debug_plan.md` §3 (A4–A7), §3.3 (решения: окно — в слой; ROLES —
> роль→source; identify — удалить).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **D3** — Косметика ядра |
| Рабочий план | `dev/meta_promt/debug_plan_3.md` (этот файл) |
| Зависит от | **D2** (константы/бюджет закрыты; импорты `Kod.py` уже правились — A7 делать после) |
| Открывает | `dev/meta_promt/debug_plan_4.md` (D4 — Документация) |
| Закрывает | **A4** (`identify`), **A5** (`ROLES`), **A6** (окно), **A7** (импорты) |
| Основные артефакты | `memory/short_term.py`, `core/agent.py`, `Kod.py`, `storage/store.py`, `dev/tests_debug/unit/test_memory.py` |
| Живой ключ | **Не нужен** |
| Меняет поведение | **Нет** (окно остаётся 10; маппинг роль→source тот же; `identify` не вызывался) |

**Цель этапа.** Устранить мёртвый код и задвоения: единственный владелец окна
краткосрочной памяти — `ShortTermMemory`; `ROLES` — реально используемый словарь
роль→source; `identify()` удалён; неиспользуемые импорты убраны.

---

## 1. Вход и предусловия

- `memory/short_term.py`: `SHORT_TERM_WINDOW = 10` объявлена **после** класса;
  `as_prompt_block()` использует `messages[-SHORT_TERM_WINDOW:]`.
- `core/agent.py`: `build_context()` — литерал `[-10:]`; `ROLES =
  {"short_term": "user"}` (не читается); `remember_message()` — тернарник
  `source="user" if role == "user" else "model"`; `identify()` (не вызывается);
  импорты `os`, `uuid4` (не используются).
- `Kod.py`: импорты `uuid4`, `MemoryItem`, `LLMClient`, `MODEL` (не используются;
  `MODEL` — решить на D2, здесь только факт).
- `storage/store.py`: импорт `datetime` (не используется).
- D2 зелёный.

**Предусловия:** A4–A7 подтверждены в D0; правки D1–D2 не задели эти места
(проверить grep перед шагами).

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 3.1 — Окно short_term: единственный владелец — слой (A6)
1. `memory/short_term.py`:
   - атрибут класса (первым делом в классе, до методов):
     ```python
     # ЕДИНСТВЕННЫЙ источник истины о размере окна краткосрочной памяти.
     window = 10
     ```
   - новый метод:
     ```python
     def recent(self, ctx: MemoryContext, limit: int = None) -> list:
         """Последние N сообщений как role/content (N = window, если limit=None)."""
         messages = self.read(ctx).get("messages", [])
         n = self.window if limit is None else limit
         return [{"role": m.get("role", "user"), "content": m.get("content", "")}
                 for m in messages[-n:]]
     ```
   - `as_prompt_block()` переписать через `recent()`:
     ```python
     def as_prompt_block(self, ctx: MemoryContext) -> str:
         return "\n".join(f"{m['role']}: {m['content']}" for m in self.recent(ctx))
     ```
   - константу `SHORT_TERM_WINDOW` (в конце файла) **удалить**.
2. `core/agent.py`, `build_context()`: заменить блок с литералом:
   ```python
   short_messages = self.memory.layers["short_term"].recent(ctx)
   ```
3. **Не** добавлять: `Agent.SHORT_TERM_WINDOW`, импорт константы в агент
   (§3.3 эталона — отклонённые варианты).
4. **Ожидаемый результат:** `grep -rn "SHORT_TERM_WINDOW\|\[-10:\]"` — пусто;
   окно задаётся в одном месте; `as_prompt_block` и `build_context` согласованы.

### Шаг 3.2 — `ROLES`: словарь роль→source (A5)
1. `core/agent.py` — заменить определение:
   ```python
   class Agent:
       # Роль реплики → source для MemoryItem (единый источник соответствия).
       ROLES = {"user": "user", "assistant": "model"}
   ```
2. `remember_message()` — использовать `ROLES`:
   ```python
   def remember_message(self, role: str, content: str, message_id: str) -> str:
       """Сохраняет реплику в краткосрочную память (append-only)."""
       if role not in self.ROLES:   # защита от опечатки/дрейфа роли
           role = "user"
       source = self.ROLES[role]
       ctx = MemoryContext(self.user_id, self.task, self.session_id)
       item = MemoryItem(content=content, source=source, scope="session",
                         owner=self.user_id, source_message_id=message_id,
                         role=role)
       return self.memory.layers["short_term"].write(ctx, item)
   ```
3. **Ожидаемый результат:** `ROLES` читается; тернарник удалён; записанные
   сообщения те же (user→user, assistant→model — маппинг не изменился).

### Шаг 3.3 — Удалить `Agent.identify()` (A4)
1. Удалить метод `identify()` целиком (идентификация и интервью уже выполняются в
   `main()` `Kod.py` — там и остаются; интерактивный I/O — зона CLI, агент без I/O).
2. Проверить: `grep -rn "identify" Kod.py core/ dev/tests_debug/` — вызовов нет
   (метод не вызывался — подтверждено D0; если тест вдруг ссылается — поправить
   тест, зафиксировать в журнале).
3. **Ожидаемый результат:** метод отсутствует; ничего не сломано.

### Шаг 3.4 — Неиспользуемые импорты (A7)
1. `core/agent.py`: убрать `import os`, `from uuid import uuid4` (проверить grep
   по файлу перед удалением; `datetime` — используется, остаётся).
2. `Kod.py`: убрать `from uuid import uuid4`, `MemoryItem` и `LLMClient` из
   импортов (проверить grep; `MODEL` — по решению D2: используется в help-тексте
   `--budget` → остаётся; если D2 решил иначе — согласованно).
3. `storage/store.py`: убрать `datetime` (проверить grep).
4. После каждого удаления — `python -m py_compile <файл>`.
5. **Ожидаемый результат:** `py_compile` ok; grep по удалённым именам — только
   целевые использования.

### Шаг 3.5 — Юнит-тесты (тест с правкой)
В `dev/tests_debug/unit/test_memory.py` добавить:
1. `test_recent_window_and_limit`: записать 12 сообщений → `recent(ctx)` возвращает
   последние 10; `recent(ctx, limit=3)` — последние 3; формат элементов
   `{role, content}`.
2. `test_as_prompt_block_uses_window`: 12 сообщений → `as_prompt_block(ctx)`
   содержит контент последних 10 и не содержит первого.
В `dev/tests_debug/unit/test_agent.py` добавить:
3. `test_roles_mapping_in_session`: `respond()` (или пара
   `remember_message("user"...)`/`remember_message("assistant"...)`) → в
   `session.json` у user-реплики `source == "user"`, у assistant — `source ==
   "model"` (маппинг через `ROLES`).
4. **Ожидаемый результат:** новые тесты зелёные; прежние — без правок и падений.

### Шаг 3.6 — Регрессия контура + контроль поведения промта
```bash
python -m py_compile Kod.py core/*.py memory/*.py storage/*.py
env -u API_KEY python dev/tests_debug/unit_runner.py
env API_KEY=test-key python dev/tests_debug/smoke.py
env API_KEY=test-key python dev/tests_debug/scenario.py
env API_KEY=test-key bash dev/tests_debug/check_acceptance.sh
```
Контроль неизменности промта (в `.tmp/`): прогон CLI из D1 (шаг 1.5) — состав
блоков и число сообщений в ответе `MockClient` **те же**, что после D1 (окно 10,
маппинг ролей, сборка — не изменились).
**Ожидаемый результат:** L2 73 + 3 = 76 OK / 0 FAIL; L3 OK; L4 8/8; гейт 12/12;
состав промта идентичен D1.

---

## 3. Выход этапа

- `memory/short_term.py` (`window` + `recent()`, без константы), `core/agent.py`
  (`ROLES` роль→source, без `identify()`, `build_context` через `recent()`, без
  лишних импортов), `Kod.py`/`storage/store.py` (чистые импорты).
- 3 новых юнит-теста.
- Запись этапа **D3** в `dev/meta_promt/debug_log.md`; статусы A4–A7 → ✅.

---

## 4. Автоматический гейт D3→D4

Гейт считается **зелёным**, если одновременно:
- [ ] `grep -rn "SHORT_TERM_WINDOW\|\[-10:\]" core/ memory/ Kod.py` — пусто;
- [ ] `grep -n "def identify" core/agent.py` — пусто; вызовов `identify` нет;
- [ ] `ROLES` читается в `remember_message`; тернарник роль→source удалён;
- [ ] неиспользуемые импорты убраны; `py_compile` всей сборки ok;
- [ ] новые тесты зелёные; L2 76 OK / 0 FAIL; L3 OK; L4 8/8; гейт 12/12;
- [ ] состав промта при дефолтах идентичен D1 (контрольный прогон);
- [ ] контракт `MemoryLayer` (read/write/as_prompt_block) не изменён.

**Зелёный** → запись D3 в `debug_log.md` (✅, A4–A7 → ✅) → **перечитать
`debug_plan.md`** → создать/открыть `debug_plan_4.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап D3
остаётся открыт.

---

## 5. Запись в `debug_log.md` (форма §7.4 `debug_plan.md`)

```text
## Этап D3 — Косметика ядра
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Закрыто: A4, A5, A6, A7
- Было: окно задвоено (SHORT_TERM_WINDOW + [-10:]); ROLES — мёртвый код;
  identify() не вызывался; неиспользуемые импорты в 3 файлах
- Стало: ShortTermMemory.window + recent() — единственный владелец окна;
  ROLES = {user→user, assistant→model} читается в remember_message;
  identify() удалён; импорты чистые
- Проверка: <grep-контроли; L2 76 OK; L3; L4 8/8; гейт 12/12; состав промта = D1>
- Артефакты: memory/short_term.py, core/agent.py, Kod.py, storage/store.py,
  test_memory.py, test_agent.py
- Спорное/риски: <если тест ссылался на identify — как поправлен>
- Перечитывание debug_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт D3→D4: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/meta_promt/debug_plan.md`, затем приступить к **D4** по
`dev/meta_promt/debug_plan_4.md` (синхронизация README / arch / Проверка — закрытие
B4).
