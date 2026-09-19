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
from datetime import datetime
from uuid import uuid4

from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager
from core.prompt_builder import PromptBuilder
from core.llm_client import LLMClient


class PromptContext:
    """Контекст, который PromptBuilder собирает в список сообщений."""

    def __init__(self, query: str, memory_blocks: dict, summary: str = "",
                 short_term_messages: list = None):
        self.query = query
        self.memory_blocks = memory_blocks
        self.summary = summary
        self.short_term_messages = short_term_messages or []


class Agent:
    ROLES = {
        "short_term": "user",   # краткосрочная пишет реплики user/assistant
    }

    def __init__(self, llm: LLMClient, memory: MemoryManager, prompts: PromptBuilder,
                 store, user_id: str = None, default_task: str = None, log=None):
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

    # --- Цикл: сообщение → память → промт → LLM → ответ --------------------------
    def build_context(self, query: str) -> PromptContext:
        """Составляет PromptContext: блоки памяти + краткосрочная история."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id)

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
        ctx_mem = MemoryContext(self.user_id, self.task, self.session_id)
        message_id = f"M{self.message_counter}"

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