# -*- coding: utf-8 -*-
"""L4 сценарные тесты задания: маршрутизация, дозированная доставка, интервью, resume.

Запуск: API_KEY=test-key $PY $TST/scenario.py
Использует MockClient и временный каталог — живых вызовов нет.
Сценарии (из Задание_Д11.txt и Суть_N3 §4.3):
  1. интервью-инициализация нового ID → создано дерево;
  2. «какие данные попадают в каждый слой» (маршрутизация remember);
  3. дозированная доставка (deliver без long_term);
  4. влияние памяти на ответы (сравнение с/без слоя);
  5. resume «с того же места».
"""
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent


def build(tmp):
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    builder = PromptBuilder("Ты ассистент")
    client = MockClient()
    return Agent(client, memory, builder, store, user_id="u")


def scenario_interview(tmp):
    """1. Новый ID → интервью → дерево users/<id>/... со всеми файлами."""
    agent = build(tmp)
    agent.initialize_user("alice", "Аня", {"style": "краткий",
                                           "constraints": "Python",
                                           "context": "магазин"})
    base = os.path.join(tmp, "users", "alice")
    assert os.path.isfile(os.path.join(base, "profile.json"))
    assert os.path.isfile(os.path.join(base, "long_term_memory.json"))
    assert os.path.isdir(os.path.join(base, "tasks", "Основная_задача", "sessions"))
    print("[scenario] интервью-инициализация OK")


def scenario_routing(tmp):
    """2. Какие данные в какой слой (явная маршрутизация)."""
    agent = build(tmp)
    agent.initialize_user("bob", "Боб", {"style": "x", "constraints": "y", "context": "z"})
    import storage.store as _s
    _s.safe_name  # noqa
    agent.respond("Мой стек — Python")
    ctx = MemoryContext("bob", agent.task, agent.session_id)
    short = agent.memory.layers["short_term"].read(ctx)
    longt = agent.memory.layers["long_term"].read(MemoryContext("bob"))
    work = agent.memory.layers["working"].read(ctx)
    prof = agent.memory.layers["profile"].read(MemoryContext("bob"))
    # Сообщение — в краткосрочной, профиль — отдельно, рабочая/долговременная — структура.
    assert len(short["messages"]) >= 2
    assert "name" in prof
    assert "tasks" in longt
    assert "current_state" in work
    print("[scenario] маршрутизация «какие данные куда» OK")


def scenario_dosed_delivery(tmp):
    """3. Дозированная доставка: без long_term слой не подмешивается."""
    agent = build(tmp)
    agent.initialize_user("carol", "К", {"style": "a", "constraints": "b", "context": "c"})
    agent.deliver = {"profile", "working", "short_term"}  # long_term опущен осознанно
    pctx = agent.build_context("вопрос")
    joined = " ".join(pctx.memory_blocks.keys())
    assert "long_term" not in joined
    messages = agent.prompts.build(pctx, agent.deliver)
    all_text = " ".join(m["content"] for m in messages)
    assert "long_term" not in all_text
    print("[scenario] дозированная доставка OK")


def scenario_influence(tmp):
    """4. Влияние памяти на ответы: с long_term и без (сравнение доставки слоя)."""
    agent = build(tmp)
    agent.initialize_user("dave", "Д", {"style": "a", "constraints": "b", "context": "c"})
    # Решение попадает в долговременную память пользователя dave.
    agent.memory.remember("long_term", MemoryContext("dave"),
                          content={"decisions": "PostgreSQL"}, source="system")
    q = "Какая СУБД выбрана?"
    # С long_term: блок долговременной памяти подмешивается в промт.
    agent.deliver = {"profile", "long_term", "working", "short_term"}
    block_full = agent.build_context(q).memory_blocks.get("long_term", "")
    # Без long_term: блок отсутствует (дозированная доставка).
    agent.deliver = {"profile", "working", "short_term"}
    block_cut = agent.build_context(q).memory_blocks.get("long_term", "")
    assert "PostgreSQL" in block_full
    assert "PostgreSQL" not in block_cut
    print("[scenario] влияние памяти на ответы OK")


def scenario_resume(tmp):
    """5. Resume: перезапуск продолжает «с того же места»."""
    agent1 = build(tmp)
    agent1.initialize_user("eve", "Е", {"style": "a", "constraints": "b", "context": "c"})
    agent1.save_state()
    task1 = agent1.task

    agent2 = build(tmp)
    agent2.load_state("eve")
    assert agent2.task == task1
    assert agent2.initialized
    print("[scenario] resume OK")


def main():
    tmp = tempfile.mkdtemp(prefix="den11_scn_")
    scenario_interview(tmp)
    scenario_routing(tmp)
    scenario_dosed_delivery(tmp)
    scenario_influence(tmp)
    scenario_resume(tmp)
    print("SCENARIO OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())