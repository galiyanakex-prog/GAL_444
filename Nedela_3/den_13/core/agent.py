# -*- coding: utf-8 -*-
"""Оркестратор Agent: идентификация, интервью, цикл «сообщение → память → промт → LLM».

Жизненный цикл (канон arch_den_11 §2.7):
  старт → идентификация user_id → загрузка профиля + long-term + список задач;
  новый id → интервью (style/constraints/context) → создание users/<id>/... и
  первая задача по смыслу сессии;
цикл:
  сообщение → remember(...) по типам → PromptBuilder(deliver=...) →
  LLMClient.complete → ответ; переход на другую задачу фиксируется отметкой +
  новой задачей со ссылкой на сессию-источник.

Агент не владеет файлами/БД напрямую: работает через MemoryManager и PromptBuilder
(инкапсуляция через фасады, arch_prim R3).
"""
import os
from dataclasses import asdict
from datetime import datetime
from uuid import uuid4

from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager
from storage.store import safe_name
from core.prompt_builder import PromptBuilder
from core.llm_client import LLMClient
from core.profile_router import ProfileRouter
from core.state_machine import (
    TaskStage, TaskState, run_task, pause_task, resume_task, transition,
)


class PromptContext:
    """Контекст, который PromptBuilder собирает в список сообщений."""

    def __init__(self, query: str, memory_blocks: dict, summary: str = "",
                 short_term_messages: list = None):
        self.query = query
        self.memory_blocks = memory_blocks
        self.summary = summary
        self.short_term_messages = short_term_messages or []


class LLMExecutor:
    """Инжектируемая зависимость автомата: LLM составляет план и наполняет шаги.

    Канон arch_den_13 §2.4: `run_task(state, executor, validator)` принимает executor
    с методами `.plan(objective) -> list[str]` и `.execute(step) -> Any`. Здесь LLM
    строит список шагов (по одному в строке) и выполняет каждый шаг запросом с блоком
    рабочей памяти (этап/шаг/действие). В тестах инжектится детерминированная заглушка.
    """

    def __init__(self, llm: LLMClient, agent: "Agent" = None, log=None):
        self.llm = llm
        self.agent = agent
        self.log = log or (lambda line: None)

    def plan(self, objective: str) -> list:
        """Просит LLM разбить цель на шаги; парсит ответ в список строк."""
        messages = [
            {"role": "system", "content":
                "Ты планировщик. Разбей задачу на 2-4 коротких шага. "
                "Выведи только список: по одному шагу в строке, без нумерации и пояснений."},
            {"role": "user", "content": objective},
        ]
        answer = self.llm.complete(messages)
        if not answer:
            return ["Выполнить задачу"]
        steps = [line.strip(" -•\t") for line in str(answer).splitlines() if line.strip()]
        return steps or ["Выполнить задачу"]

    def execute(self, step: str):
        """Выполняет один шаг: LLM-запрос с блоком рабочей памяти (этап/шаг/действие)."""
        messages = [
            {"role": "system", "content":
                "Ты исполнитель. Работай строго в рамках текущего шага, не перепрыгивая этапы."},
            {"role": "user", "content": step},
        ]
        # Подмешиваем блок working (этап/шаг/ожидаемое действие), если агент доступен.
        if self.agent is not None and getattr(self.agent, "user_id", None):
            try:
                ctx = MemoryContext(self.agent.user_id, self.agent.task,
                                    self.agent.session_id,
                                    profile_id=self.agent.active_profile or "")
                block = self.agent.memory.layers["working"].as_prompt_block(ctx)
                messages.insert(1, {"role": "system", "content": block})
            except Exception:
                pass
        result = self.llm.complete(messages)
        return result if result is not None else f"Результат шага: {step}"


def default_validator(results: list) -> bool:
    """Заглушка валидатора из `Задание_Д13.txt`: результат непустой → успех."""
    return len(results) > 0


class StubExecutor:
    """Детерминированная заглушка исполнителя (режим --mock, тесты, сценарии).

    Тот же контракт, что у `LLMExecutor` (`.plan`/`.execute`), но без сети: план из
    трёх шагов по цели, результат шага — предсказуемая строка. Позволяет проверять
    жизненный цикл автомата (шаги, пауза, продолжение) независимо от ответов LLM.
    """

    def plan(self, objective: str) -> list:
        goal = (objective or "задача").strip().rstrip(".")
        return [f"Собрать данные: {goal}", "Обработать данные", "Проверить результат"]

    def execute(self, step: str):
        return f"Результат шага: {step}"


class Agent:
    ROLES = {
        "short_term": "user",   # краткосрочная пишет реплики user/assistant
    }

    def __init__(self, llm: LLMClient, memory: MemoryManager, prompts: PromptBuilder,
                 store, user_id: str = None, default_task: str = None, log=None,
                 executor=None, validator=None):
        self.llm = llm
        self.memory = memory
        self.prompts = prompts
        self.store = store
        self.log = log or (lambda line: None)

        # Идентификация: user_id определяется на старте (ввод или --user).
        self.user_id = user_id
        self.default_task = default_task or "Основная_задача"
        self.task = self.default_task
        self.deliver = {"profile", "long_term", "working", "short_term"}

        # Персонализация: активный профиль сессии (None → default), авто-роутинг
        # и детерминированный роутер профилей (только если у store есть репозиторий).
        self.active_profile = None
        self.auto_route = False
        self.router = ProfileRouter(store, log=self.log) \
            if getattr(store, "profile_repo", None) is not None else None

        # Состояние задачи (День 13): формализованный автомат. None — задачи ещё нет.
        # executor/validator — инжектируемые зависимости автомата (arch §2.4):
        # по умолчанию LLM составляет план и наполняет шаги, валидатор — заглушка.
        self.task_state = None
        self.executor = executor or LLMExecutor(llm, agent=self, log=self.log)
        self.validator = validator or default_validator

        # Текущая сессия (для краткосрочной памяти).
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Счётчик сообщений для source_message_id.
        self.message_counter = 0
        # Пользователь уже инициализирован (профиль создан)?
        self.initialized = False

    # --- Идентификация и интервью-инициализация ----------------------------------
    def identify(self, requested_user: str = None) -> str:
        """Возвращает user_id; при новом ID запускает интервью и создаёт дерево."""
        profile_repo = self.store.profile_repo
        user_id = requested_user or self.user_id

        if user_id and profile_repo is not None and profile_repo.exists(user_id):
            self.user_id = user_id
            self.initialized = True
            return user_id

        # Новый или незаданный ID → интервью.
        if not user_id:
            user_id = requested_user or self.user_id

        # Интервью предполагает интерактивный ввод; здесь он вызывается через CLI.
        # Агент предоставляет интервью-вопросы и сохраняет ответы.
        return user_id or ""

    def interview_questions(self) -> list:
        """Три вопроса персонализации (стиль / констрейнты / контекст)."""
        return [
            ("style", "Какой стиль ответов предпочитаете? (краткий/подробный, формальный/разговорный)"),
            ("constraints", "Какие ограничения учесть? (стек, темы-табу, языки)"),
            ("context", "Какой контекст задачи? (чем занимаетесь, цель)"),
        ]

    def initialize_user(self, user_id: str, name: str, answers: dict) -> None:
        """Создаёт профиль, дерево задач и первую задачу по смыслу сессии."""
        self.user_id = user_id
        self.store.ensure_user(user_id)

        profile = {
            "id": user_id,
            "name": name,
            "style": {"answers": answers.get("style", "")},
            "constraints": {"answers": answers.get("constraints", "")},
            "context": {"answers": answers.get("context", "")},
        }
        # Профиль — через слой profile (явная маршрутизация).
        self.memory.remember(
            "profile", MemoryContext(user_id), content=profile, source="system"
        )

        # Первая задача по смыслу сессии + долговременная память (ссылка на задачи).
        first_task = self.default_task
        self.memory.remember(
            "working",
            MemoryContext(user_id, first_task, self.session_id),
            content={"description": "Первая задача (по смыслу первой сессии)"},
            source="system",
        )
        self.memory.remember(
            "long_term",
            MemoryContext(user_id),
            content={"tasks": {"name": first_task, "ref": f"tasks/{first_task}"}},
            source="system",
        )
        self.task = first_task
        self.initialized = True
        self.log(f"[Агент] Пользователь {user_id} инициализирован (интервью пройдено)")

    def load_state(self, user_id: str) -> None:
        """Загрузка памяти пользователя: профиль + long-term + список задач."""
        self.user_id = user_id
        long_term = self.memory.layers["long_term"].read(MemoryContext(user_id))
        tasks = long_term.get("tasks", [])
        if tasks:
            first = tasks[0]
            self.task = first.get("name", first) if isinstance(first, dict) else first
        self.initialized = True
        # Подтягиваем формализованное состояние активной задачи (если оно есть).
        self.load_task_state()

    # --- Персонализация: активный профиль ----------------------------------------
    def switch_profile(self, profile_id: str) -> bool:
        """Переключает активный профиль сессии. False — если профиля нет."""
        known = [pid for pid, _ in self.store.list_profiles(self.user_id)]
        if profile_id not in known:
            return False
        self.active_profile = profile_id
        self.log(f"[Агент] активный профиль: {profile_id}")
        return True

    # --- Жизненный цикл задачи (Task State Machine, День 13) ----------------------
    def load_task_state(self) -> None:
        """Загружает TaskState активной задачи из task_state.json (или None).

        Вызывается при load_state(user_id) и switch_task(): переключение задачи
        подтягивает её собственное состояние («продолжение с того же места»).
        """
        if not self.user_id:
            self.task_state = None
            return
        data = self.store.read_task_state(self.user_id, self.task)
        if not data:
            self.task_state = None
            return
        try:
            data["stage"] = TaskStage(data["stage"])
            if data.get("previous_stage"):
                data["previous_stage"] = TaskStage(data["previous_stage"])
            self.task_state = TaskState(**data)
            self.log(f"[Автомат] загружено состояние «{self.task}»: {self.task_state.stage.value} "
                     f"(шаг {self.task_state.current_step}/{len(self.task_state.steps)})")
        except (ValueError, KeyError, TypeError):
            self.task_state = None

    def _persist_task_state(self) -> None:
        """Единая точка персистентности: сейв task_state.json + зеркало current_state."""
        if self.task_state is None or not self.user_id:
            return
        data = asdict(self.task_state)
        data["stage"] = self.task_state.stage.value
        data["previous_stage"] = (self.task_state.previous_stage.value
                                  if self.task_state.previous_stage else None)
        self.store.write_task_state(self.user_id, self.task, data)
        # Зеркало стадии в working_memory.json (обратная совместимость с днями 11–12).
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        self.memory.layers["working"].write(
            ctx, MemoryItem(content={"current_state": self.task_state.stage.value},
                            source="system"))

    def start_task(self, objective: str) -> TaskState:
        """Новая задача: task_id по цели, stage=PLANNING, отметки в памяти, сейв."""
        task_id = safe_name(objective) or self.default_task
        self.task_state = TaskState(task_id=task_id, objective=objective,
                                    stage=TaskStage.PLANNING)
        # Отметка в рабочей и долговременной памяти (механика switch_task дня 11).
        self.memory.remember(
            "working", MemoryContext(self.user_id, self.task, self.session_id),
            content={"description": objective}, source="system")
        self.memory.remember(
            "long_term", MemoryContext(self.user_id),
            content={"tasks": {"name": self.task, "ref": f"tasks/{self.task}"}},
            source="system")
        self._persist_task_state()
        self.log(f"[Автомат] новая задача «{objective}» → {self.task_state.stage.value}")
        return self.task_state

    def step_task(self) -> TaskState:
        """Один проход автомата (run_task) + персистентность. None — задачи нет."""
        if self.task_state is None:
            self.log("[Автомат] /step: нет активной задачи (сначала /plan <цель>)")
            return None
        run_task(self.task_state, self.executor, self.validator, log=self.log)
        self._persist_task_state()
        return self.task_state

    def run_to_end(self, max_passes: int = 50) -> TaskState:
        """Крутить автомат до done/failed/paused (с защитой от бесконечного цикла)."""
        if self.task_state is None:
            self.log("[Автомат] /run: нет активной задачи (сначала /plan <цель>)")
            return None
        passes = 0
        while (self.task_state.stage not in
               (TaskStage.DONE, TaskStage.FAILED, TaskStage.PAUSED)
               and passes < max_passes):
            run_task(self.task_state, self.executor, self.validator, log=self.log)
            self._persist_task_state()
            passes += 1
        return self.task_state

    def pause(self) -> bool:
        """Пауза на любом рабочем этапе. False — если задачи нет / не на рабочем этапе."""
        if self.task_state is None:
            self.log("[Автомат] /pause: нет активной задачи")
            return False
        if self.task_state.stage in (TaskStage.PAUSED, TaskStage.DONE, TaskStage.FAILED):
            self.log(f"[Автомат] /pause: нельзя pause на этапе "
                     f"{self.task_state.stage.value}")
            return False
        pause_task(self.task_state)
        self._persist_task_state()
        self.log(f"[Автомат] пауза (вернуться к: "
                 f"{self.task_state.previous_stage.value})")
        return True

    def resume(self) -> bool:
        """Продолжение с того же этапа и шага, без повторного плана/объяснений."""
        if self.task_state is None:
            self.log("[Автомат] /resume: нет активной задачи")
            return False
        if self.task_state.stage != TaskStage.PAUSED:
            self.log(f"[Автомат] /resume: задача не на паузе "
                     f"(этап {self.task_state.stage.value})")
            return False
        resume_task(self.task_state)
        self._persist_task_state()
        self.log(f"[Автомат] продолжение: этап {self.task_state.stage.value}, "
                 f"шаг {self.task_state.current_step}/{len(self.task_state.steps)}")
        return True

    def retry_task(self) -> bool:
        """Восстановление из failed → planning (единственный выход из FAILED)."""
        if self.task_state is None or self.task_state.stage != TaskStage.FAILED:
            self.log("[Автомат] /task retry: задача не в состоянии failed")
            return False
        transition(self.task_state, TaskStage.PLANNING, log=self.log)
        self.task_state.steps = []
        self.task_state.results = []
        self.task_state.current_step = 0
        self.task_state.error = None
        self.task_state.expected_action = None
        self._persist_task_state()
        return True

    # --- Цикл: сообщение → память → промт → LLM → ответ --------------------------
    def build_context(self, query: str) -> PromptContext:
        """Составляет PromptContext: блоки памяти + краткосрочная история."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id,
                            profile_id=self.active_profile or "")

        # Дозированная доставка: блоки только для выбранных слоёв.
        blocks = self.memory.build_blocks(self.deliver, ctx)

        # Краткосрочная память — сообщения как список role/content.
        short_term = self.memory.layers["short_term"].read(ctx)
        short_messages = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in short_term.get("messages", [])[-10:]
        ]

        summary = self.store.read_sessions_resume(self.user_id, self.task)
        return PromptContext(query, blocks, summary=summary, short_term_messages=short_messages)

    def respond(self, user_message: str) -> str:
        """Полный цикл обработки одного сообщения пользователя."""
        self.message_counter += 1
        message_id = f"M{self.message_counter}"

        # 0. Авто-роутинг: профиль выбирается ДО сборки промта — активный профиль
        #    подключён к каждому запросу (персонализация).
        if self.auto_route and self.router is not None:
            candidate = self.router.route(self.user_id, user_message)
            if candidate and candidate != (self.active_profile or ""):
                self.switch_profile(candidate)

        # 1. Явное сохранение сообщения в краткосрочную память (source=user).
        self.remember_message("user", user_message, message_id)

        # 2. Сборка промта (дозированная доставка: только слои из self.deliver).
        prompt_ctx = self.build_context(user_message)
        messages = self.prompts.build(prompt_ctx, self.deliver)

        # 3. Ответ LLM.
        answer = self.llm.complete(messages)
        if answer is None:
            return None

        # 4. Сохранение ответа и обновление рабочей памяти (жизненный цикл).
        self.remember_message("assistant", answer, message_id + "a")
        self.log(f"[Агент] {message_id}: ответ получен (доставка: {sorted(self.deliver)})")
        return answer

    def remember_message(self, role: str, content: str, message_id: str) -> str:
        """Сохраняет реплику в краткосрочную память (append-only)."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        item = MemoryItem(
            content=content, source="user" if role == "user" else "model",
            scope="session", owner=self.user_id, source_message_id=message_id,
            role=role,
        )
        return self.memory.layers["short_term"].write(ctx, item)

    def switch_task(self, new_task: str, reason: str = "") -> None:
        """Переход на принципиально другую задачу: отметка в сессии + новая задача.

        Канон куратора: в текущей сессии ставится отметка о переходе, создаётся
        новая задача со ссылкой на сессию-источник.
        """
        old_task = self.task
        old_session = self.session_id

        # Отметка перехода в рабочей памяти текущей задачи.
        ctx_old = MemoryContext(self.user_id, old_task, old_session)
        self.memory.remember(
            "working", ctx_old,
            content={"open_questions": f"Переход на задачу «{new_task}» (сессия {old_session})"},
            source="system",
        )

        # Новая задача со ссылкой на сессию-источник.
        self.memory.remember(
            "working",
            MemoryContext(self.user_id, new_task, self.session_id),
            content={"description": f"Новая задача «{new_task}» (из сессии {old_session})"},
            source="system",
        )
        self.memory.remember(
            "long_term",
            MemoryContext(self.user_id),
            content={"tasks": {"name": new_task, "ref": f"tasks/{new_task}", "source_session": old_session}},
            source="system",
        )

        self.task = new_task
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Переключение задачи подтягивает её собственное состояние (arch §2.8).
        self.load_task_state()
        self.log(f"[Агент] Переход на задачу «{new_task}» (источник: сессия {old_session})")

    def save_state(self) -> None:
        """Сохранение состояния: рабочая память + resume-заметка."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        self.memory.remember(
            "working", ctx,
            content={"lifecycle_summary": f"Сессия {self.session_id} продолжена "
                     f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
            source="system",
        )
        self.store.write_sessions_resume(
            self.user_id, self.task,
            f"# Резюме сессий задачи «{self.task}»\n\nПоследняя сессия: {self.session_id}\n",
        )
        # Персистентность автомата: resume переживает перезапуск процесса (arch §2.5).
        self._persist_task_state()