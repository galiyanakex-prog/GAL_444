# FINAL_REV.md — каталог-резюме проекта `den_13` (итоговое состояние)

> Артефакт процесса: живёт только в `dev/`. Сверен с фактическим деревом
> (`find $KOD -name '*.py'`, 2026-09-20) после завершения миграции на
> `ND/arch/arch_den_13.md` (Task State Machine).
> История создания дня 12 — `logs_reports/stages/stage_00_env.md … stage_E_person.md`;
> Этап F (автомат) — `logs_reports/stages/stage_F_state.md`; журнал миграции — `migr_log.md`.

## 1. Что это за проект

CLI-агент (RouterAI, `stepfun/step-3.5-flash`) с **явной моделью памяти** (4 слоя),
**персонализацией** (мультипрофиль + роутер + пайплайн скиллов) и **формализованным
состоянием задачи** (конечный автомат: этап / текущий шаг / ожидаемое действие, пауза на
любом этапе, продолжение без повторных объяснений, персистентность `task_state.json`).

Главная идея Дня 13 (канон `Задание_Д13.txt`): LLM составляет план и наполняет шаги,
но **отдельный Python-код управляет жизненным циклом задачи** через явные переходы.

## 2. Дерево проекта (факт, 2026-09-20)

```
den_13/
├── Kod.py                       # 597 строк — точка входа: DI + REPL (15 секций, 24 формы команд)
├── core/                        # 906 строк
│   ├── agent.py                 # 469 — оркестратор + жизненный цикл задачи + LLMExecutor/StubExecutor
│   ├── llm_client.py            #  91 — LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        #  70 — детерминированный выбор профиля
│   ├── prompt_builder.py        #  67 — BLOCK_ORDER + deliver + budget
│   └── state_machine.py         # 209 — TaskStage(6) + TaskState + transition/pause/resume/save/load/run_task
├── memory/                      # 438 строк
│   ├── base.py                  #  85 — MemoryLayer (ABC), MemoryContext(+profile_id), PolicyEngine (задел)
│   ├── short_term.py            #  50 — append-only, parent_id, окно 10
│   ├── working.py               #  86 — состояние задачи + инжект стейта в блок промта
│   ├── long_term.py             #  51 — profile_ref + tasks/decisions/knowledge
│   ├── profile.py               #  77 — активный профиль (+domain/triggers/skills)
│   └── manager.py               #  89 — remember/recall/build_blocks/report, LAYER_ORDER
├── storage/                     # 462 строки
│   ├── store.py                 # 252 — фасад иерархии + task_state_path/read/write_task_state
│   └── db.py                    # 210 — ProfileRepository (SQLite) + миграция схемы
├── users/                       # рантайм-данные (profiles.db + деревья пользователей)
├── run.sh / run.desktop         # запуск (+x; .desktop привязан к хосту)
├── README.md                    # описание: память + персонализация + «Состояние задачи»
├── Den_log.md / tokens.csv      # рантайм-артефакты (журнал маршрутизации, CSV токенов)
├── Задание_Д13.txt              # неизменяемый первоисточник
└── dev/                         # служебное пространство (раздел 3)
```

Итого рабочего кода: ~2400 строк в 17 .py-файлах (без тестов); с тестами — ~3700.

## 3. Блоки и контракты (маркеры ПРОГРЕСС)

| Блок | Файл | Ключевые сущности | Статус |
|---|---|---|---|
| Автомат задачи | `core/state_machine.py` | `TaskStage` (6 этапов), `TaskState` (9 полей), `ALLOWED_TRANSITIONS`, `transition()`, `next_state()` (обёртка), `pause_task()`, `resume_task()`, `save_state()`, `load_state()`, `run_task()` | ✅ Этап F |
| Оркестратор | `core/agent.py` | `Agent` (identify/interview/respond/switch_profile/switch_task/save_state) + `start_task/step_task/run_to_end/pause/resume/retry_task/load_task_state/_persist_task_state`; `LLMExecutor`, `StubExecutor`, `default_validator` | ✅ Этап F |
| Хранилище | `storage/store.py` | `task_state_path()`, `read_task_state()`, `write_task_state()` (+ весь фасад Д11–12) | ✅ Этап F |
| Память | `memory/working.py` | `as_prompt_block()` + `_task_state_lines()` («Этап: … (шаг N/M): …», «Ожидаемое действие», «Пауза», «Ошибка»; зеркало «Стадия задачи») | ✅ Этап F |
| CLI | `Kod.py` | `/plan /step /run /pause /resume /task retry`; `/state` — снимок TaskState + карта переходов; `print_task_snapshot()`; `--fresh` сбрасывает `task_state` | ✅ Этап F |
| Персонализация | `core/profile_router.py`, `memory/profile.py`, `storage/db.py` | мультипрофиль, роутер, пайплайн скиллов | ✅ Этап E (Д12, без изменений) |
| Модель памяти | `memory/*`, `storage/store.py` | 4 слоя, MemoryManager, фасад иерархии | ✅ Д11 (без изменений) |
| LLM | `core/llm_client.py` | ABC + RouterAI (retry 429: 2→4→8 с) + Mock | ✅ Д11 (без изменений) |

## 4. Тестовый контур (факт)

| Уровень | Файл | Объём | Результат |
|---|---|---|---|
| L1 | `py_compile` всей сборки | 17 файлов | exit 0 |
| L2 | `dev/tests_debug/unit_runner.py` + `unit/` (8 модулей) | **56 тестов**: storage 7, memory 6, llm 6, prompt 4, agent 4, state 5, person 9, **fsm 15** | 56 OK, 0 FAIL |
| L3 | `dev/tests_debug/smoke.py` | 4 прогона (цикл in-process + CLI; автомат in-process + CLI) | exit 0 |
| L4 | `dev/tests_debug/scenario.py` | **7 сценариев** (+`scenario_pause_resume`) | exit 0 |
| Гейт | `dev/tests_debug/check_acceptance.sh` | **10 проверок** (+№10 «task_state.json переживает перезапуск») | 10/10 |

Приёмка: **25 критериев** (`dev/Проверка.md`): 19 прежних + 20–22 (персонализация) +
23–25 (автомат, `arch_den_13.md` §4.3). Всё без живого ключа
(`API_KEY=test-key` / `MockClient` / заглушки executor+validator).

## 5. Dev-пространство (факт)

```
dev/
├── migr_plan.md                 # план-эталон миграции (источник содержания)
├── migr_plan_0.md … migr_plan_8.md   # рабочие планы этапов
├── migr_log.md                  # журнал выполнения (этапы 0–8 + финальная запись)
├── Проверка.md                  # чек-лист приёмки: 25 критериев
├── FINAL_REV.md                 # этот файл
├── PLAN_naming.md               # артефакт дня 12 (исторический)
├── meta_promt/                  # ПРОМТ_fsm.md (контракты Этапа F) + ПРОМТ_readme.md
│                                #   (исторические метапромты дня 12 удалены по рекомендации куратора)
├── tests_debug/                 # unit_runner.py, smoke.py, scenario.py, check_acceptance.sh,
│   ├── unit/                    #   8 тест-модулей (вкл. test_fsm.py)
│   ├── scenario/scen_1.md       #   сценарий живой демонстрации
│   ├── fixtures/, smoke/        #   каркас (пустые)
│   └── .tmp/                    #   единственное место временных файлов (.gitignore)
└── logs_reports/
    ├── stages/                  # stage_00_env … stage_10_final, stage_E_person, stage_F_state
    ├── errors/                  # карточки ошибок (вкл. error_20260920_234900.md — экранирование гейта)
    ├── run_log.md               # сводный журнал прогонов
    └── final_report.md          # итоговый отчёт
```

## 6. Известные заделы (не объём дня)

- `PolicyEngine` + `visibility` — фильтр инвариантов (п.18) не реализуется;
- `parent_id` — задел ветвления диалога;
- `skills[]` — декларативный пайплайн в промте, движок оркестрации — следующие дни;
- `validator` — заглушка `len(results) > 0` (усложнение — следующие дни);
- изоляция стадий уровня 2 (контейнеры/отдельные сессии) — задел;
- `next_state()` сохранена обёрткой совместимости (рабочий код использует `transition()`).
