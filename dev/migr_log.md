# migr_log.md — журнал модернизации `AI_9` (Ревизия 8): локальные LLM + локальный RAG + оптимизация + доступ извне

> Журнал результатов модернизации по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_12.md`
> (единая сквозная нумерация; один файл = один этап = один гейт).
> Мастер-план: `dev/migr_plan.md` (**Ревизия 8, редакция v1.1**; формат записей — §7.3,
> правила — §1.1, §5).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> **Живой слой обязателен** на этапах 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12 (LM Studio
> `127.0.0.1:1234` с боевой моделью; Ollama `127.0.0.1:11434` — эмбеддинги RAG); на
> остальных — детерминированной регрессии (unit / L3 / L4 / гейт) достаточно.
> **Регрессия запрещена на всех этапах:** без `--model`/`--local-gen` промпт и поведение
> идентичны текущим; прежние проверки `check_acceptance.sh` и все юнит-модули зелёные.
> История прошлых ревизий — в `dev/old_vers/` (…, **8 — снимок на входе Ревизии 8**).
>
> **Ревизия 8.** Задача: довести **существующий** полноценный CLI-агент AI_9 до требований
> `ND/tasks/n_6/Задание.txt` (5 частей): 1) локальные LLM (боевая — `Qwen2.5-Coder-14B-Instruct-Q4_K_M`
> через LM Studio); 2) интеграция локальных LLM (`ModelRegistry`, `/model`, отображение модели,
> субагенты); 3) полностью локальный RAG (retrieval + генерация) и сравнение с облаком;
> 4) оптимизация (профили параметров, prompt-шаблон, квантование, замеры «до/после»);
> 5) приватный сервис с доступом извне (фасад на хосте → шлюз на VPS → SSH reverse tunnel).
> **Контур S (доступ извне) добавлен впервые** — в Ревизии 7 его не было.
> **Коммиты — только за оператором**; агент готовит правки и предлагает текст сообщения.

---

## Подготовка — мастер-план Ревизии 8 (v1.1) + рабочие планы 0–12 (до этапа 0)

- Статус: ✅ завершён (2026-10-11)
- Тип: не этап конвейера, а **порождение мастер-плана и 13 рабочих планов**.

### Было

- `dev/migr_plan.md` — мастер-план Ревизии 7 (тема — RAG по 4 частям `Задание.txt`).
- Требования `ND/tasks/n_6/Задание.txt` (5 частей, ревизия 8) проанализированы, но не сведены в план.
- Рабочие планы `migr_plan_0.md`/`_1.md`/`_2.md` — от Ревизии 7 (Ollama-путь, репер 244 OK, гейт 33/33).

### Стало

- `dev/migr_plan.md` — мастер-план **Ревизии 8, v1.1**: этапы **0…12**, контур **S**,
  решения оператора **№1–22** (все закрыты), `models.json`/`gateway.json`, механизм гейта,
  DoD по 5 частям, трассировка.
- Рабочие планы `dev/migr_plan_0.md` … `dev/migr_plan_12.md` — **13 файлов** в едином формате
  (шапка-цитата + Цель · Предусловия · Границы · Шаги · Выход · Гейт N→N+1 · Откат ·
  Что передаём дальше + текст коммита). Планы 0–2 перезаписаны под Ревизию 8; 3–12 созданы.
- **Боевая модель (решение №20):** `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF`, файл
  `~/.lmstudio/models/mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`
  (2,5 ГБ, единственный тег, квант Q6_K). Боевой id — `lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K`.
- **Правки мастера по факту прогона 2026-10-11:** строка `pytest` (§0.4) → установлен в `.venv`
  (9.1.1); новая строка о хрупкости тестов к `importlib.reload`; строка базовой линии → фактические
  числа; шаг 1 Этапа 0 переписан под факт 39/43; §5 — правило про pytest и запрет захвата
  через `from … import` объектов reload-мых модулей.

### Артефакты

- `dev/migr_plan.md` (v1.1), `dev/migr_plan_0.md` … `dev/migr_plan_12.md`.
- Снимок Ревизии 7 — `dev/old_vers/8/migr_log.md` (2048 строк) и `dev/old_vers/8/migr_plan_v1.1.md`.

### Коммит

- Предложен оператору (текст — в ШАГЕ 0.7 плана 0); выполнен оператором — хеш: _(ожидается)_.

---

## Этап 0 — Базовая линия Ревизии 8 + аудит LLM-слоя + репер MCP (цель: О0)

- Статус: ✅ завершён (2026-10-11)
- Было: журнал Ревизии 7; числа базовой линии — по памяти (33/33, 25/25, 27 модулей).
- Стало: базовая линия зафиксирована **фактическим прогоном**; аудит LLM-слоя и `rag/` снят;
  карта разрывов под 5 частей составлена; репер MCP снят.

### Живой прогон (базовая линия «до»)

- `ls dev/tests_debug/unit/test_*.py | wc -l` → **33** модуля.
- `env -u API_KEY .venv/bin/python dev/tests_debug/unit_runner.py` → **Итого: 290 OK, 0 FAIL**.
- `API_KEY=test-key .venv/bin/python dev/tests_debug/smoke.py` → **SMOKE OK: exit 0**.
- `API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py` → **SCENARIO OK: exit 0**.
- `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **ИТОГ: 39 из 43 зелёные (FAIL=4)**.
- `pytest -q` → **291 passed** (дополнительный раннер; репер — `unit_runner.py`).

### Красные 4 проверки гейта (ограничение среды, не регресс)

- №33 `--rag-eval`, №38 `--rag-ask`, №39 `--rag-verify`, №43 `dialog_runner` — все требуют
  **живого RAG-индекса/эмбеддингов Ollama**, который на момент прогона **не отвечал**.
- Причина — недоступная Ollama (эмбеддинги), **не регресс кода**.
- **Снято на этапе 1:** после `sudo systemctl start ollama` (модель `bge-m3:latest` на месте)
  гейт → **43 из 43 зелёные (FAIL=0)**. Итоговая базовая линия Ревизии 8 — **43/43**.

### Аудит LLM-слоя (`core/llm_client.py`, `Kod.py`, `core/agent.py`)

- Классы: `LLMReply`, `LLMClient(ABC)`, `RouterAIClient`, `MockClient`; функции
  `parse_tool_calls`, `parse_fallback_tool_call`, `render_tool_protocol`.
- Создание клиента — в одном месте: `Kod.py::build_agent` (стр. 226): `MockClient` (244) /
  `RouterAIClient` (248) → `Agent` (251).
- Точки вызова в `Agent`: `self.llm` (183), `self.executor = LLMExecutor` (212),
  `self.llm.complete(...)` (700, 870, 983), `rag_service.rephrase(..., llm=self.llm.complete)` (768),
  `rag_service.ground/grounding_feedback` (663, 693).

### Аудит фундамента `rag/`

- **19** модулей (`cache, chunking, citations, compare, config, corpus, embedding, eval,
  grounding, index, rerank, retrieval, rewrite, service, sources, text, types, verify, __init__`).
- `rag/index/` — `chunks.json`, `emb_cache.json`, `meta.json`, `postings.json`, `vectors.bin`;
  индекс **117 чанков / 9 документов**, `dim=1024` (эмбеддинги `bge-m3`).
- `rag/datasets/` — `corpus.list` (9 файлов), `queries.jsonl` (**34** запроса, из них **10** с `expect`).
- `rag.__all__` — `RagConfig, RagConfigError, RagDependencyError, load_config, DEFAULTS,
  DEFAULT_CONFIG_PATH, Chunk, DocMeta, Hit, IngestReport, EvalReport, CompareReport,
  GroundingReport, Answer, Source, Quote, RagService`.

### Карта разрывов (под 5 частей `Задание.txt`)

| Часть | Требование | Есть сейчас | Разрыв → этап |
|---|---|---|---|
| 1 | локальная LLM запущена, доступна по CLI/HTTP, ≥ 3 запроса | LM Studio + боевая модель на диске; сервер не поднят | поднять LM Studio → **1** |
| 2 | `/model`, отображение модели, субагенты | только `RouterAIClient`/`MockClient`; реестра нет | `ModelRegistry` + локальные клиенты → **2**; `/model` + подпись → **3**; субагенты → **4** |
| 3 | локальный RAG (retrieval + генерация), сравнение | retrieval локальный (`bge-m3`); генерация — облако | `--local-gen` + инжект `llm` → **5**; сравнение → **6** |
| 4 | параметры + prompt-шаблон + квантование + замеры | профилей нет; шаблон общий | профили + шаблон → **7**; квант/замеры → **8** |
| 5 | сервис, туннель, вход, лимиты, устойчивость | нет фасада/шлюза/туннеля | фасад → **9**; шлюз + туннель → **10**; устойчивость → **11** |

### Состояние локальных сервисов (только чтение)

- Ollama `127.0.0.1:11434` → **НЕ отвечает**.
- LM Studio `127.0.0.1:1234` → **НЕ отвечает**.
- Боевой GGUF на диске: `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf` (2,5 ГБ).
- Это **блокер этапа 1** (решение №21: LM Studio обязательна); команды подъёма — в плане 1.

### Репер MCP на VPS

- `.venv/bin/python Kod.py --mcp-probe` → **READY**: серверы **`time`** и **`weather`**
  подключены; всего инструментов **4** (`mcp.time.get_time`, `mcp.weather.search_locations`,
  `mcp.weather.get_forecast_metadata`, `mcp.weather.get_weather_forecast`); exit 0.
- Точка сравнения для этапа 10 (решение №18: MCP сохраняется).

### Регрессия

- `unit_runner.py` — **290 OK, 0 FAIL**; `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
  `check_acceptance.sh` — **39 из 43** (4 красных — недоступная Ollama, зафиксировано);
  `pytest -q` — **291 passed**.
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `dev/migr_log.md` — обнулён до шапки Ревизии 8 + записи «Подготовка» и «Этап 0».
- `dev/migr_plan_0.md` … `dev/migr_plan_12.md` — созданы (Ревизия 8).
- `rag/`, `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/` — **не изменены**.

### Коммит

- Предложен оператору (текст — в ШАГЕ 0.7 плана 0); выполнен оператором — хеш: _(ожидается)_.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 0→1

- ✅ (все пункты зелёные; п.4 «39 из 43» — не красный флаг, причина зафиксирована как
  ограничение среды)

---

## Этап 1 — Локальная LLM запущена (LM Studio + боевая модель) (цель: О1)

- Статус: ✅ завершён (2026-10-11)
- Было: LM Studio `127.0.0.1:1234` не отвечал; боевая модель на диске, но не загружена.
- Стало: сервер поднят оператором (`lms server start`), боевая модель загружена и отвечает.

### Живой прогон

- `lms server start` → `Success! Server is now running on port 1234`.
- `lms ps` → `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`, **IDLE, 2.54 GB,
  context 32768, parallel 4, Local**.
- `GET /v1/models` → содержит `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`.
- `POST /v1/chat/completions` × 3 (разной сложности):
  - Л1 «Скажи: ок» → **4,0 с**, 39 симв.;
  - Л2 (перечислить модули) → **36,0 с**, 830 симв.;
  - Л3 (объяснить функцию + риск) → **36,3 с**, 778 симв.
  Все ответы непустые; Л2/Л3 упёрлись в `max_tokens=256`.
- CLI-зачёт: `lms ls` (модель видна, `✓ LOADED`) + `lms ps` (загружена). Интерактивный
  `lms chat` не запускался (тяжёлая сессия на CPU) — по решению оператора зачёт по `ls`/`ps`.

### Офлайн без сети

- ✅ подтверждено: LM Studio — локальный сервис на loopback, интернет не используется.

### Метрики

- Латентность: короткий ответ ~4 с; длинный (до лимита 256 токенов) ~36 с (CPU, без GPU).
- RSS RAM: модель 2,54 ГБ — легко помещается в RAM 15 ГБ (доступно ~10).
- GPU: **неприменимо** (`nvidia-smi` отсутствует).

### Ограничение среды

- Ollama `127.0.0.1:11434` → **поднят оператором** (`sudo systemctl start ollama`; `bge-m3:latest`
  на месте, 1,2 ГБ). После подъёма гейт `check_acceptance.sh` → **43 из 43 зелёные (FAIL=0)** —
  прежние 4 красные RAG-проверки (№33/38/39/43) позеленели. Ограничение снято.

### Регрессия

- `unit_runner.py` — **290 OK, 0 FAIL**; `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
  `check_acceptance.sh` — **43 из 43** (после подъёма Ollama; было 39 из 43);
  `pytest -q` — **291 passed**.
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `dev/logs_reports/stages/local_llm_probe.md` — транскрипт живого прогона;
- `ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md` — справка;
- `.env.example` — переменные LM Studio/Ollama (без секретов);
- `dev/migr_log.md` — запись «Этап 1».

### Коммит

- Предложен оператору (текст — в ШАГЕ 1.6 плана 1); выполнен оператором — хеш: _(ожидается)_.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 1→2

- ✅ (все пункты зелёные; Ollama поднят, гейт 43 из 43)

---

## Этап 2 — `ModelRegistry` + локальные клиенты (цель: L1)

- Статус: ✅ завершён (2026-10-11)
- Было: только `RouterAIClient`/`MockClient`; реестра моделей нет; `Agent` создавал
  клиент напрямую в `Kod.py::build_agent`.
- Стало: `core/model_registry.py` (`ModelSpec`, `ModelRegistry`) + `OpenAICompatClient`
  (LM Studio, основной) + `OllamaClient` (альтернативный) + `models.json`; `Agent`
  получил `set_model`/`model_label`; `build_agent` строит клиент через реестр.

### Живой прогон

- `ModelRegistry.probe('lmstudio:…abliterated-Q6_K')` → `ok=True`, latency 3 мс.
- `ModelRegistry.build(...).complete([...])` → живой ответ `'Да'` (не mock).
- `probe('ollama:bge-m3')` → `ok=True`, version `0.35.1`.

### Офлайн без сети

- ✅ подтверждено: локальные клиенты ходят только на loopback (`ensure_loopback`).

### Метрики

- Латентность probe: LM Studio ~3 мс, Ollama ~1 мс.
- Живой ответ боевой модели: короткий (~секунды).

### Регрессия

- `unit_runner.py` — **302 OK, 0 FAIL** (было 290; +12 новых `test_llm_local.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **303 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `core/model_registry.py` — создан;
- `core/llm_client.py` — `OpenAICompatClient`, `OllamaClient`, `ensure_loopback`;
- `core/agent.py` — `set_model`/`model_label`;
- `Kod.py` — `--model`, `MODELS_PATH`, `build_agent(model_id=…)` через реестр;
- `models.json` — создан (секретов нет);
- `dev/tests_debug/unit/test_llm_local.py` — создан (12 тестов).

### Коммит

- Предложен оператору (текст — в ШАГЕ 2.6 плана 2); выполнен оператором — хеш: `e235ca6`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 2→3

- ✅ (все пункты зелёные; `Agent` не импортирует провайдеров — только `LLMClient`)

---

## Этап 3 — `/model` + отображение модели во всех CLI-сессиях (цель: L2)

- Статус: ✅ завершён (2026-10-11)
- Было: модель выбиралась только флагом `--model`; в CLI не было видно, какая
  модель/сервис подключены; `tokens.csv` и `Den_log.md` не несли модель.
- Стало: команда `/model` (`current`/`list`/`use`/`status`/`profile`); флаги
  `--model-list` (one-shot) и `--model-profile`; явное отображение модели —
  баннер `[Сессия] модель: …`, префикс реплики `[service/model]`, `model=` в
  `Den_log.md`, колонка `model` в `tokens.csv`.

### Живой прогон

- Одна сессия `cloud → lmstudio:…Q6_K → cloud` через `/model use` — 3 ответа,
  у каждого своя подпись (транскрипт `stages/local_llm_switch.md`).
- `/model list` — печатает все 4 спека реестра + отметку текущей.
- `/model status` — живой health-check (LM Studio `ok`, latency ~2 мс).

### Офлайн без сети

- ✅ подтверждено: `/model use` для локального сервиса делает probe по loopback;
  недоступный сервис → отказ с сохранением прежней модели.

### Метрики

- Локальный ответ боевой модели: короткий (~секунды, CPU).
- `/model list`/`/model status` токенов LLM не тратят (только HTTP-probe).

### Регрессия

- `unit_runner.py` — **310 OK, 0 FAIL** (было 302; +8 новых `test_model_switch.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **311 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `Kod.py` — флаги `--model-list`/`--model-profile`, `handle_model_command`,
  `model_banner`, `print_model_list`, префикс реплики, колонка `model` в CSV;
- `core/agent.py` — `model=` в записи ответа `Den_log.md`;
- `dev/tests_debug/unit/test_model_switch.py` — создан (9 тестов);
- `dev/logs_reports/stages/local_llm_switch.md` — транскрипт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 3.6 плана 3); выполнен оператором — хеш: `e5e98f4`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 3→4

- ✅ (все пункты зелёные; переключение не трогает `TaskStage`/память/`deliver`;
  без `--model` промпт байт-в-байт прежний)

---

## Этап 4 — Субагенты на локальных LLM (цель: L3)

- Статус: ✅ завершён (2026-10-11)
- Было: вспомогательных CLI-сессий нет; фразы «сделай локально в …» не
  распознавались; `Kod.py` умел только REPL.
- Стало: `core/subagents.py` (`SubagentRunner` + детерминированный анализатор
  фразы); флаг `--oneshot` (один обмен → ответ → выход); флаги `--subagent-run`,
  `--subagent-service`, `--local-only`; команда `/subagent run|list|log`;
  триггер-фраза «сделай локально в `<service>`: …» с подтверждением.

### Живой прогон

- Триггер-фраза «сделай локально в LM Studio: …» → подтверждение → субагент
  отработал на боевой модели (статус `ok`, ~6,5 с).
- Второй субагент через `/subagent run … --service lmstudio` — отдельная задача,
  статус `ok` (~6,4 с).
- Логи субагентов несут их собственную подпись модели
  (`model=lmstudio/…abliterated-Q6_K`); транскрипт `stages/local_llm_subagent.md`.

### Офлайн без сети

- ✅ подтверждено: субагент запускается только на локальном сервисе
  (`lmstudio`/`ollama`); облачный сервис при `local_only` → отказ до запуска.

### Метрики

- Латентность субагента (короткая задача, CPU): ~6,5 с.
- `/subagent list` токенов LLM не тратит.

### Регрессия

- `unit_runner.py` — **321 OK, 0 FAIL** (было 310; +10 новых `test_subagents.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **322 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `core/subagents.py` — создан (`SubagentRunner`, `detect_local_subagent_request`);
- `Kod.py` — `--oneshot`, `--subagent-run`, `--subagent-service`, `--local-only`,
  `run_oneshot`, `run_subagent`, `handle_subagent_command`, триггер-фраза;
- `dev/tests_debug/unit/test_subagents.py` — создан (10 тестов);
- `dev/logs_reports/stages/local_llm_subagent.md` — транскрипт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 4.6 плана 4); выполнен оператором — хеш: `9a69ddd`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 4→5

- ✅ (все пункты зелёные; `TaskStage` основной задачи не изменён — 0 переходов)

---

## Этап 5 — Локальная генерация в RAG (цель: G1)

- Статус: ✅ завершён (2026-10-12)
- Было: RAG-ответ генерировался облачной моделью (`RouterAIClient`); `RagService`
  не имел явного инжекта генератора; секции `generation` в `rag/config.json` не было.
- Стало: `RagService(cfg, llm=…)` принимает генератор (DI); `answer()` использует
  переданный `llm`, иначе — инжектированный; секция `generation` в конфиге
  (`provider`/`model`/`profile`); флаг `--local-gen` и команда `/gen local|cloud|status`;
  полностью локальный контур `--rag --local-gen` (эмбеддинги Ollama + retrieval +
  генерация локально).

### Живой прогон

- `--rag-ask "<вопрос>" --gen-provider lmstudio` на 3 вопросах по индексу Недели 5:
  ответ + источники `[doc_id#chunk_id]` + цитаты; опора `partial`/`hallucination`/`ok`;
  транскрипт `stages/rag_local_gen.md`.
- `/gen status` → `/gen local` → `/gen status` → `/rag ask`: переключение генератора
  RAG на lmstudio; одна точка — `agent.llm` и `rag_service.llm` совпадают;
  транскрипт `stages/rag_gen_command.md`.
- `--rag --local-gen`: баннер сессии несёт локальную модель, ответ с опорой `ok`;
  транскрипт `stages/rag_local_gen_full.md`.

### Офлайн без сети

- ✅ подтверждено: прогон при заблокированном внешнем доступе
  (`HTTP(S)_PROXY → 127.0.0.1:1`, loopback разрешён) — ответ получен локально,
  `exit=0`; транскрипт `stages/rag_local_gen_offline.md`.
- ✅ мониторинг соединений процесса (`ss -tnp`): внешних (не-loopback) соединений
  за прогон — **0**.

### Метрики

- Латентность локальной генерации (CPU, 3B Q6_K, профиль rag-strict 700 токенов):
  ~130–250 с на ответ; retrieval (bge-m3) — секунды.
- Таймаут боевой модели поднят 180 → 600 с (генерация 700 токенов на CPU ~180 с
  упиралась в прежний лимит).

### Регрессия

- `unit_runner.py` — **335 OK, 0 FAIL** (было 321; +14 новых `test_rag_local_gen.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **336 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `rag/service.py` — `__init__(cfg, log, llm, embedder)`, `answer` использует `self.llm`;
- `rag/config.py` — `GenerationConfig` + секция в `RagConfig`, env `AI9_GEN_PROVIDER`/`AI9_GEN_MODEL`, валидация;
- `rag/config.json` — секция `generation`;
- `Kod.py` — `--local-gen`, `--gen-provider`, `--gen-model`, `_build_gen_client`,
  `_build_gen_llm`, `handle_gen_command`, диспетчер `/gen`, строки справки;
- `models.json` — таймаут боевой модели 600 с;
- `dev/tests_debug/unit/test_rag_local_gen.py` — создан (14 тестов);
- `dev/logs_reports/stages/rag_local_gen.md`, `rag_gen_command.md`,
  `rag_local_gen_full.md`, `rag_local_gen_offline.md` — транскрипты живых прогонов.

### Коммит

- Предложен оператору (текст — в ШАГЕ 5.7 плана 5); выполнен оператором — хеш: `50e8d6a`.

### Перечитывание migr_plan.md

- ✅ (2026-10-12)

### Гейт 5→6

- ✅ (все пункты зелёные; внешних запросов нет; офлайн-прогон прошёл; индекс 117/9
  совпадает с конфигом)

---

## Этап 6 — Сравнение локальной и облачной генерации (цель: G2)

- Статус: ✅ завершён (2026-10-12)
- Было: `rag/compare.py` умел сравнивать только стратегии чанкинга и режимы ответа
  (`no_rag`/`rag`/`rag_filter`/`rag_filter_rewrite`); сравнения генераторов
  (локальный vs облачный) не было.
- Стало: `rag/compare.py` — `compare_generators(cfg, queries, generators, k, repeat)`
  и `render_generator_report(result)` (три оси: качество/скорость/стабильность);
  `Kod.py` — флаги `--rag-gen-compare` / `--gen-modes` / `--repeat` / `--gen-report`.
  Клиентов строит `Kod.py` (граница §5: `rag/` не импортирует `core/`), поэтому
  сравнение запускается из `Kod.py`, а не из `python -m rag.compare`.

### Живой прогон

- Команда: `python Kod.py --rag-gen-compare --gen-modes cloud,local --repeat 3`
  на 10 контрольных вопросах (`c01…c10`), один датасет, один retrieval, различается
  только генератор. Отчёт: `stages/rag_local_compare.md` (30 строк cloud + 30 local).
- Локальная генерация на CPU — долго: прогон занял ~1 ч 50 мин (фоново).

### Метрики (три оси)

- **Качество:** must_contain — cloud **0.6491**, local **0.6316** (локальная чуть
  уступает); источники — **30/30** у обоих; валидные ссылки — cloud **114/175**,
  local **47/58** (локальная ставит меньше ссылок, но доля валидных выше).
- **Скорость:** медиана — cloud **22.8 с**, local **175.9 с** (локальная медленнее
  в **7.7×**); p95 — cloud 41.7 с, local 297.4 с; ток/с — cloud 17.1, local 2.4.
- **Стабильность:** ошибки — cloud **1**, local **0**; согласованность (совпадение
  must_contain в 3 повторах) — **7/10** у обоих.
- **Вердикт:** локальная модель работоспособна (источники 30/30, 0 ошибок), но
  уступает облачной по must_contain и в 7.7× медленнее; ссылки ставит реже, но
  аккуратнее. Разбор расхождений: c01 (cloud must=2 vs local must=1), c10
  (cloud must=0 vs local must=1).

### Регрессия

- `unit_runner.py` — **345 OK, 0 FAIL** (было 335; +10 новых `test_rag_gen_compare.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **346 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `rag/compare.py` — `compare_generators`, `render_generator_report`, `GENERATOR_MODES`,
  `_citations`/`_citations_valid`, `_generator_summary`/`_generator_divergences`/`_generator_verdict`;
- `Kod.py` — `--rag-gen-compare`, `--gen-modes`, `--repeat`, `--gen-report`, `run_rag_gen_compare`;
- `dev/tests_debug/unit/test_rag_gen_compare.py` — создан (10 тестов);
- `dev/logs_reports/stages/rag_local_compare.md` — отчёт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 6.5 плана 6); выполнен оператором — хеш: `3a7361c`.

### Перечитывание migr_plan.md

- ✅ (2026-10-12)

### Гейт 6→7

- ✅ (отчёт с тремя осями есть; локальный режим работоспособен — 30/30 ответов с
  валидными источниками; вердикт + разбор расхождений есть; офлайн-регрессия зелёная;
  `requirements.txt` без изменений)

---

## Этап 7 — Профиль оптимизации: параметры + prompt-шаблон (цель: P1)

- Статус: ✅ завершён
- Было: параметры генерации не переопределялись профилем (`default` — пустой);
  prompt-шаблон блока [rag] был единым для облака и локальной модели; замер «до»
  отсутствовал.
- Стало: три профиля (`default`/`rag-strict`/`fast`) накладываются на спек и уходят
  в тело запроса (LM Studio — `temperature`/`max_tokens`/`top_p`; Ollama — `options`);
  строгий prompt-шаблон `render_local_rag_template` включается **только** для локальной
  модели при активном RAG; облачный промпт не затронут (renderer=None → общий блок).
- Живой прогон: `python Kod.py --rag-gen-compare --gen-modes local --gen-profile default
  --repeat 3` (боевая `Qwen2.5-Coder-3B-…-Q6_K` через LM Studio `127.0.0.1:1234`,
  loopback-only) → exit 0; отчёт `dev/logs_reports/stages/optimize_before.md`.
- Офлайн без сети: подтверждено (loopback-only; внешних запросов нет).
- Метрики (замер «до», профиль `default` + общий промпт): must_contain 0.5439;
  источники 30/30; ссылки валид. 50/68; медиана 247682.6 мс / p95 600100.6 мс;
  1.9 ток/с; ошибок 2; согласованность 3/10.
- Регрессия: unit_runner 360 OK / 0 FAIL; smoke SMOKE OK; scenario SCENARIO OK;
  check_acceptance 43 из 43 (FAIL=0); pytest 361 passed.
- Артефакты:
  - `core/prompt_builder.py` — `render_local_rag_template`, `LOCAL_RAG_INSTRUCTIONS`,
    `LOCAL_RAG_EXAMPLE`;
  - `core/model_registry.py` — `with_profile` бросает `KeyError` со списком профилей;
  - `core/agent.py` — поле `rag_block_renderer` (DI-шаблон блока [rag]);
  - `rag/service.py` — `answer`/`context_block` принимают `block_renderer`;
  - `rag/compare.py` — `compare_generators(..., block_renderers)`,
    `render_generator_report(..., title)`;
  - `Kod.py` — `_local_rag_renderer`, `_apply_local_rag_template`, флаги
    `--gen-profile`/`--local-template`, заголовок отчёта этапа 7;
  - `dev/tests_debug/unit/test_llm_optimize.py` — создан (15 тестов);
  - `dev/logs_reports/stages/optimize_before.md` — замер «до».
- Коммит: предложен оператору (текст — в ШАГЕ 7.5 плана 7); выполнен оператором — хеш: _(ожидается)_.
- Перечитывание migr_plan.md: ✅ (2026-10-12)
- Гейт 7→8: ✅ (три профиля загружаются; «до» замерено; параметры в теле запроса —
  тест зелёный; облачный промпт байт-в-байт прежний; офлайн-регрессия без изменений;
  `requirements.txt` без изменений; запись «Этап 7» + перечитывание плана)