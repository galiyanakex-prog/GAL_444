# ПРОМТ_agent — создание оркестратора Agent (core/agent.py)

## 1. Цель и граница
Создать stateful-оркестратор (арх §2.7):
```
старт → идентификация user_id → известный ID: загрузка профиля+long-term+список задач;
         новый ID: интервью (style/constraints/context) → создание users/<id>/… + первая задача;
цикл: сообщение → remember(...) по типам → PromptBuilder(deliver=...) → LLMClient.complete → ответ;
переход на другую задачу → отметка + новая задача со ссылкой на сессию-источник;
exit → сохранение состояния (resume «с того же места»).
```
Что НЕ делаем: не пишем REPL/команды (это `Kod.py`), не трогаем state machine
(отдельный модуль); агент НЕ касается файлов/БД напрямую — только через фасады
(`MemoryManager`, `PromptBuilder`, `LLMClient`, `Store`).

## 2. Вход (зависимость: memory/manager.py, core/llm_client.py, core/prompt_builder.py готовы)
- `ND/arch/arch_den_11.md` §2.7 (жизненный цикл).
- `Nedela_3/Суть_N3.md` §4.2 (интервью, разделение задач, resume) и §4.8 п.5.
- Контракт `memory/base.py` (MemoryContext, MemoryItem), `memory/manager.py`.

## 3. Контракты (сигнатуры)
```python
# PromptContext объявлен ЗДЕСЬ (владелец); PromptBuilder его импортирует.
class PromptContext:
    def __init__(self, query: str, memory_blocks: dict, summary: str = "",
                 short_term_messages: list = None)

class Agent:
    def __init__(self, llm: LLMClient, memory: MemoryManager, prompts: PromptBuilder,
                 store, user_id=None, default_task=None, log=None)
    # поля: user_id, task, deliver (set, default все 4 слоя), session_id (генерируется),
    #        message_counter (для source_message_id), initialized (bool)
    def identify(self, requested_user=None) -> str          # новый/известный ID
    def interview_questions(self) -> list                   # [(стиль, Q), (констрейнты, Q), (контекст, Q)]
    def initialize_user(self, user_id, name, answers: dict)  # профиль + дерево + первая задача
    def load_state(self, user_id)                            # профиль + long-term + список задач + active task
    def build_context(self, query) -> PromptContext          # memory.build_blocks(deliver) + short_term + summary
    def respond(self, user_message) -> str                   # полный цикл; None при сбое LLM
    def remember_message(self, role, content, message_id) -> str
    def switch_task(self, new_task, reason="")               # отметка в сессии + новая задача (ссылка на источник)
    def save_state(self)                                     # working.lifecycle_summary + sessions_resume.md
```

### 3.1 Обязательная механика (иначе п.6–п.8, п.12 не закрыты)
- **Идентификация (п.6)**: `user_id` задаётся `--user` или спрашивается ДО загрузки
  памяти. Решение «новый/известный» — по `store.profile_repo.exists(user_id)`.
- **Интервью (п.7)**: новый ID → три вопроса (стиль/констрейнты/контекст) → профиль
  (id + name, дополняется позже) → дерево `users/<id>/…` → первая задача по смыслу сессии.
- **Явная маршрутизация (п.4)**: всякий занос только через `memory.remember(layer, ...)`;
  никакого «автосохранения всего подряд». Сообщение пользователя → ShortTermMemory
  (source="user"), ответ модели → ShortTermMemory (source="model").
- **Понятие таски (п.8)**: `respond` кладёт промты в текущую задачу; `switch_task`
  ставит отметку перехода в рабочей памяти старой задачи, создаёт новую задачу в
  `working_memory.json` + запись в `long_term_memory.json` со ссылкой на сессию-источник.
- **Resume (п.12)**: `save_state`/`load_state` переживают перезапуск процесса — рабочая
  память, список задач и профиль восстанавливаются, история сессии читается из файлов.

## 4. Выход (scope — только этот файл)
- `core/agent.py`.

## 5. Критерий готовности
`$PY $TST/unit_runner.py` — `test_agent.py` зелёный (exit 0). Сценарии (на MockClient,
без живого ключа): интервью нового ID создаёт дерево; respond маршрутизирует сообщение
и ответ в session.json; load_state известного ID восстанавливает task; switch_task
фиксирует переход и ссылку на источник; resume «с того же места».

## 6. Правила дня
Отчёт — `logs_reports/stages/stage_06_agent.md` (✅). Цикл отладки — §6.1.
Приёмка — §7 п.6 (идентификация), п.7 (интервью), п.8 (таска + переход), п.12 (resume).