# migr_plan_4.md — Рабочий план. Этап 4: Оркестратор — `core/agent.py` (жизненный цикл задачи)

> **Тип файла: РАБОЧИЙ ПЛАН** (создан из план-эталона `dev/migr_plan.md`, раздел «Этап 4»).
> Миграция выполняется **по этому файлу**, подшаг за подшагом.
> **Автономный режим: включён по умолчанию** — действия считаются заранее одобренными;
> живые LLM-вызовы с реальным ключом — только с явного согласия пользователя.
>
> **Цель этапа:** `Agent` получает жизненный цикл задачи (`arch_den_13.md` §2.8):
> `start_task` / `step_task` / `run_to_end` / `pause` / `resume` / `retry_task` +
> `load_task_state` + единая точка персистентности `_persist_task_state()`.
> LLM составляет план и наполняет шаги, **Python-код управляет жизненным циклом**.
>
> **Источники истины:** `Задание_Д13.txt` («Продолжение без повторных объяснений») →
> `$ARCH` §2.4, §2.8.

---

## Входные условия этапа

- [ ] Этап 3 завершён: в `dev/migr_log.md` есть запись «Этап 3 … ✅».
- [ ] Готова база: `state_machine.py` (Этап 1), `store.*_task_state` (Этап 2),
      блок working с этапом/шагом (Этап 3).
- [ ] Переменные: `$KOD`, `$TST`, `$PY`, `$ARCH` — как в эталоне §0.5 п. 8.

## Правила этапа (наследуются из эталона §0.5 и §0.3)

1. Порядок подшагов **строгий** (4.1 → 4.5): каждый опирается на предыдущий — **не батчить**.
2. После каждого подшага: `py_compile` + smoke → запись в `migr_log.md`.
3. Retry-цикл: при неуспехе — фиксация ❌, минимальная правка, повтор до ✅.
4. Smoke-прогоны — на `MockClient`, `--memory-dir $TST/.tmp/…`; без живого ключа.
5. **Регресс-запрет:** контракты дней 11–12 (`identify/interview/respond/switch_profile/
   switch_task/save_state`, профили, роутер) не ломать — `test_agent.py` (4) и
   `test_person.py` (9) обязаны остаться зелёными.

---

## Подшаги этапа

### Подшаг 4.1 — `self.task_state` + `load_task_state()`
- Цель: `Agent.__init__`: `self.task_state: TaskState | None = None`; метод
  `load_task_state()` — читает `store.read_task_state(user_id, task)` → dict → TaskState
  или None; вызывается из `load_state(user_id)` и из `switch_task()`.
- Прочитать: `core/agent.py` (`__init__`, `load_state`, `switch_task`), `$ARCH` §2.8.
- Изменить/создать: `core/agent.py` — импорт `core.state_machine`, поле, метод, два вызова.
- Проверка: `py_compile`; smoke (MockClient, `--memory-dir .tmp`): `load_state` не падает
  без `task_state.json`.
- Запись в журнал: 4.1.
- Объём: ~80 строк чтения, ~30 строк правки.
- Кандидат на батч: нет.

### Подшаг 4.2 — `start_task(objective)` + `_persist_task_state()`
- Цель: новая задача: `task_id = safe_name(objective)`, `TaskState(task_id, objective,
  stage=PLANNING)`, отметки в working/long_term (механика `switch_task` дня 11), сейв
  `task_state.json` + зеркало `current_state`; лог «[Автомат] новая задача «…» → planning».
  Хелпер `_persist_task_state()` — единая точка: сейв JSON + зеркало + лог перехода.
- Прочитать: `core/agent.py` (`switch_task` — образец отметок), `$ARCH` §2.8.
- Изменить/создать: `core/agent.py` — `start_task()` + `_persist_task_state()`.
- Проверка: `py_compile`; smoke: `start_task` → `task_state.json` создан, stage=planning.
- Запись в журнал: 4.2.
- Объём: ~60 строк чтения, ~40 строк правки.
- Кандидат на батч: нет.

### Подшаг 4.3 — `LLMExecutor` + `step_task()` / `run_to_end()`
- Цель: инжектируемые зависимости автомата (§2.4): `LLMExecutor(llm, …)` — `plan(objective)`
  (один LLM-запрос «составь список шагов, по одному в строке» → парсинг в `steps[]`;
  MockClient даёт детерминированный план) и `execute(step)` (LLM-запрос с блоком working:
  этап/шаг/действие); `validator = lambda results: len(results) > 0` (заглушка задания;
  усложнение — следующие дни). `step_task()` — один проход `run_task` +
  `_persist_task_state()`; `run_to_end(max_passes=50)` — цикл до DONE/FAILED/PAUSED
  с защитой от бесконечного цикла.
- Прочитать: `$ARCH` §2.4, §2.8; `core/llm_client.py` (MockClient — формат ответов).
- Изменить/создать: `core/agent.py` — класс `LLMExecutor` (решение: рядом с оркестратором;
  зафиксировать в журнале) + `step_task()`, `run_to_end()`.
- Проверка: `py_compile`; smoke (MockClient): start_task → run_to_end → stage=done, results
  непустые, шаги не дублируются.
- Запись в журнал: 4.3.
- Объём: ~80 строк чтения, ~70 строк правки.
- Кандидат на батч: нет (крупнейший подшаг этапа).

### Подшаг 4.4 — `pause()` / `resume()`
- Цель: `pause()` — `pause_task(self.task_state)` + сейв + лог; не на рабочем этапе
  (done/failed/paused/нет задачи) → ворнинг, False. `resume()` — `resume_task` + сейв +
  лог «продолжение с шага N (этап X)»; не на паузе → no-op, False. **Без повторного плана
  и без переспроса задачи** — состояние уже в `task_state.json`.
- Прочитать: `Задание_Д13.txt` («Что означает «продолжение без повторных объяснений»»).
- Изменить/создать: `core/agent.py` — два метода.
- Проверка: `py_compile`; smoke: step → pause → (новый Agent, тот же memory-dir) → resume →
  stage/current_step прежние.
- Запись в журнал: 4.4.
- Объём: ~40 строк чтения, ~35 строк правки.
- Кандидат на батч: нет.

### Подшаг 4.5 — Интеграция с `save_state()` / `respond()` / `switch_task()` + `retry_task()`
- Цель: `save_state()` (выход/EOF/Ctrl-C) дополнительно сейвит `task_state.json`;
  `respond()` — логика прежняя (блок working уже несёт этап/шаг после Этапа 3);
  `switch_task()` вызывает `load_task_state()` для новой задачи; `retry_task()` —
  transition(FAILED→PLANNING), steps/results очищаются, current_step=0.
- Прочитать: `core/agent.py` (`save_state`, `respond`, `switch_task`).
- Изменить/создать: `core/agent.py` — правки трёх методов + `retry_task()`.
- Проверка: `py_compile`; smoke: switch_task туда-обратно сохраняет состояния обеих задач.
- Запись в журнал: 4.5.
- Объём: ~70 строк чтения, ~40 строк правки.
- Кандидат на батч: нет.

---

## Чек-лист приёмки этапа

- [ ] `py_compile core/agent.py` — OK.
- [ ] Smoke-сценарий «plan → step → pause → новый процесс (новый Agent, тот же memory-dir)
      → resume → run → done» проходит in-process на MockClient.
- [ ] После resume: этап и `current_step` прежние, план НЕ перестроен, задача НЕ переспрошена.
- [ ] Завершённые шаги не повторяются (results без дублей, current_step монотонен).
- [ ] `pause()` на done/failed/paused → ворнинг, состояние не меняется; `resume()` не на
      паузе → no-op.
- [ ] `save_state()` при выходе сейвит `task_state.json`; `switch_task()` подтягивает
      состояние задачи.
- [ ] `unit_runner.py`: `test_agent.py` (4) и `test_person.py` (9) зелёные; `test_state.py` — ⚠.

## Последний пункт алгоритма этапа (выполняется только после ✅ приёмки)

1. Записать в `dev/migr_log.md` блок «## Этап 4 — Оркестратор (`core/agent.py`)»
   по формату эталона §0.4.
2. **Перейти к выполнению следующего этапа: открыть `dev/migr_plan_5.md` и начать с его
   подшага 5.1.** (Если этап не принят — повторять подшаги/правки до успеха.)
