# -*- coding: utf-8 -*-
"""Юнит-тесты агента (на MockClient): интервью, маршрутизация, resume, переход задач."""
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent


def make_agent(tmp_path, user_id=None):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    builder = PromptBuilder("Ты ассистент")
    client = MockClient()
    agent = Agent(client, memory, builder, store, user_id=user_id)
    return agent


def test_interview_initialization(tmp_path):
    agent = make_agent(tmp_path)
    answers = {"style": "краткий", "constraints": "Python", "context": "обучение"}
    agent.initialize_user("u1", "Иван", answers)
    assert agent.user_id == "u1"
    assert agent.initialized
    profile = agent.memory.layers["profile"].read(
        __import__("memory.base", fromlist=["MemoryContext"]).MemoryContext("u1"))
    assert profile["name"] == "Иван"
    # Каноническое дерево создано.
    assert (tmp_path / "users" / "u1" / "profile.json").exists()
    assert (tmp_path / "users" / "u1" / "long_term_memory.json").exists()


def test_respond_routes_memory(tmp_path):
    from memory.base import MemoryContext
    agent = make_agent(tmp_path)
    agent.initialize_user("u2", "Аня", {"style": "x", "constraints": "y", "context": "z"})
    answer = agent.respond("Какая у меня задача?")
    assert answer is not None
    # Сообщение и ответ легли в краткосрочную память (session.json).
    session = agent.memory.layers["short_term"].read(
        MemoryContext("u2", agent.task, agent.session_id))
    assert len(session["messages"]) >= 2


def test_resume_known_user(tmp_path):
    from memory.base import MemoryContext
    agent1 = make_agent(tmp_path, user_id="u3")
    agent1.initialize_user("u3", "Боб", {"style": "a", "constraints": "b", "context": "c"})
    agent1.save_state()

    # Новый агент (эмуляция перезапуска процесса).
    agent2 = make_agent(tmp_path, user_id="u3")
    agent2.load_state("u3")
    assert agent2.initialized
    assert agent2.task == agent1.task


def test_switch_task(tmp_path):
    from memory.base import MemoryContext
    agent = make_agent(tmp_path)
    agent.initialize_user("u4", "Дан", {"style": "a", "constraints": "b", "context": "c"})
    old_task = agent.task
    agent.switch_task("Новая_задача")
    assert agent.task == "Новая_задача"
    # Новая задача появилась в долговременной памяти со ссылкой на сессию.
    lt = agent.memory.layers["long_term"].read(MemoryContext("u4"))
    names = [t.get("name") for t in lt["tasks"] if isinstance(t, dict)]
    assert "Новая_задача" in names