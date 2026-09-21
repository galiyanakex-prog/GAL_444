# -*- coding: utf-8 -*-
"""L4 сценарные тесты задания: маршрутизация, дозированная доставка, интервью, resume.

Запуск: API_KEY=test-key $PY $TST/scenario.py
Использует MockClient и временный каталог — живых вызовов нет.
Сценарии (из задания недели и Суть_N3 §4.3):
  1. интервью-инициализация нового ID → создано дерево;
  2. «какие данные попадают в каждый слой» (маршрутизация remember);
  3. дозированная доставка (deliver без long_term);
  4. влияние памяти на ответы (сравнение с/без слоя);
  5. resume «с того же места»;
  6. персонализация: два профиля → разный состав промта + авто-роутинг;
  7. пауза/продолжение задачи: снимок task_state.json по канону Дня 13,
     «перезапуск» → resume с того же шага без повторного плана → run → done.
"""
import json
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Все временные артефакты прогонов — только в dev/tests_debug/.tmp (не в /tmp и не в users/ дня).
TMP_ROOT = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor, default_validator
from core.state_machine import TaskStage


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


def scenario_personalization(tmp):
    """6. Персонализация: профили «Химик» и «Экономист» → разный состав промта.

    Один и тот же запрос даёт разный блок профиля (MockClient отражает блоки);
    auto_route переключает профиль по запросу — лог содержит «[Роутер]» и
    «[Агент] активный профиль».
    """
    logs = []
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=logs.append)
    memory = MemoryManager(default_layers(store, log=logs.append), log=logs.append)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="frank", log=logs.append)
    agent.initialize_user("frank", "Ф", {"style": "a", "constraints": "b", "context": "c"})

    chemist = {"id": "frank", "name": "Химик", "domain": "химия",
               "triggers": ["химия", "реактив", "реакция"],
               "style": {"answers": "строго по формулам"}, "constraints": {}, "context": {},
               "skills": [{"name": "spec", "instructions": "составь спеку ответа"}]}
    economist = {"id": "frank", "name": "Экономист", "domain": "экономика",
                 "triggers": ["бюджет", "цена"],
                 "style": {"answers": "считай выгоду"}, "constraints": {}, "context": {}}
    store.save_profile("frank", chemist, "chemist")
    store.save_profile("frank", economist, "economist")

    # Один и тот же запрос — разный состав промта для разных активных профилей.
    q = "расскажи про это"
    agent.switch_profile("chemist")
    block_chem = agent.build_context(q).memory_blocks.get("profile", "")
    answer_chem = agent.respond(q)
    agent.switch_profile("economist")
    block_eco = agent.build_context(q).memory_blocks.get("profile", "")
    answer_eco = agent.respond(q)
    assert "Химик" in block_chem and "Пайплайн скиллов:" in block_chem
    assert "Экономист" in block_eco
    assert block_chem != block_eco
    assert answer_chem != answer_eco

    # Авто-роутинг: запрос с триггером переключает профиль до сборки промта.
    agent.auto_route = True
    agent.respond("какая реакция идёт с реактивом?")
    assert agent.active_profile == "chemist"

    joined = "\n".join(logs)
    assert "[Роутер]" in joined
    assert "[Агент] активный профиль" in joined
    print("[scenario] персонализация (профили + роутер) OK")


def build_fsm(tmp, logs=None):
    """Агент с детерминированным StubExecutor (без сети) для сценария автомата."""
    log = logs.append if logs is not None else None
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=log)
    memory = MemoryManager(default_layers(store, log=log), log=log)
    return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                 user_id="u", log=log, executor=StubExecutor(),
                 validator=default_validator)


def scenario_pause_resume(tmp):
    """7. Пауза/продолжение задачи (канон Дня 13, arch §4.3).

    /plan → шаг 0 выполнен → /pause → снимок task_state.json по канону задания →
    «перезапуск» (новый Agent, тот же memory-dir) → /resume с того же шага без
    повторного плана → /run → done. Лог содержит «[Автомат]».
    """
    logs = []
    agent1 = build_fsm(tmp, logs)
    agent1.initialize_user("gina", "Г", {"style": "a", "constraints": "b", "context": "c"})

    # /plan «Найди три Python-фреймворка и сравни их» → planning → execution (план из 3 шагов).
    agent1.start_task("Найди три Python-фреймворка и сравни их")
    agent1.step_task()                 # planning → execution (построен план)
    assert agent1.task_state.stage == TaskStage.EXECUTION
    assert len(agent1.task_state.steps) == 3
    agent1.step_task()                 # шаг 0 выполнен
    assert agent1.task_state.current_step == 1 and len(agent1.task_state.results) == 1

    # /pause → снимок на диске.
    assert agent1.pause() is True
    task_name = agent1.task
    snap_path = agent1.store.task_state_path("gina", task_name)
    assert os.path.isfile(snap_path)
    with open(snap_path, encoding="utf-8") as file:
        raw = json.load(file)
    # Канон снимка из `Задание_Д13.txt`: paused, previous_stage=execution, шаг 1, 1 результат.
    assert raw["stage"] == "paused"
    assert raw["previous_stage"] == "execution"
    assert raw["current_step"] == 1
    assert len(raw["results"]) == 1

    # «Перезапуск»: новый Agent поверх того же memory-dir читает снимок.
    agent2 = build_fsm(tmp, logs)
    agent2.load_state("gina")
    assert agent2.task_state is not None
    assert agent2.task_state.stage == TaskStage.PAUSED
    assert agent2.task_state.current_step == 1

    # /resume → продолжение с шага 1, план НЕ перестроен, задача НЕ переспрошена.
    assert agent2.resume() is True
    assert agent2.task_state.stage == TaskStage.EXECUTION
    assert agent2.task_state.current_step == 1
    assert len(agent2.task_state.steps) == 3

    # /run → done; завершённый шаг 0 не повторяется (results без дублей).
    agent2.run_to_end()
    assert agent2.task_state.stage == TaskStage.DONE
    assert len(agent2.task_state.results) == 3 == len(set(agent2.task_state.results))

    assert "[Автомат]" in "\n".join(logs)
    print("[scenario] пауза/продолжение задачи (task_state.json + перезапуск) OK")


def scenario_invariant_conflict(tmp):
    """8. Конфликт запроса и инварианта (День 14): отказ, объяснение, изменение правила.

    /invariant add framework.django → запрос «перепиши API на FastAPI» → агент
    ОТКАЗЫВАЕТ, называет framework.django и предлагает альтернативу; /check показывает
    нарушение; /invariant set --yes меняет правило; повторный запрос проходит. Лог
    содержит строки «[Инварианты]».
    """
    from core.invariants import Invariant
    logs = []
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=logs.append)
    memory = MemoryManager(default_layers(store, log=logs.append), log=logs.append)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="ivan", log=logs.append, executor=StubExecutor())
    agent.initialize_user("ivan", "И", {"style": "a", "constraints": "b", "context": "c"})

    # /invariant add framework.django architecture "Использовать Django"
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Использовать Django, а не FastAPI"))

    # Запрос конфликтует с инвариантом → отказ с объяснением и альтернативой.
    before = agent.tool_calls
    result = agent.propose_and_check("перепиши API на FastAPI")
    assert result["allowed"] is False
    assert agent.tool_calls == before                    # инструмент не вызван
    assert "framework.django" in result["message"]
    assert "альтернатив" in result["message"].lower()

    # /check "перейти на FastAPI" → нарушение видно без исполнения.
    action = agent.propose_action("перейти на FastAPI")
    assert agent.check_invariants(action)

    # Инвариант попадает в промт (явный учёт в рассуждениях).
    joined = "\n".join(m["content"] for m in agent.prompts.build(agent.build_context("q"), agent.deliver))
    assert "[invariants]" in joined and "framework.django" in joined

    # /invariant set framework.django "..." --yes → правило изменено (требует подтверждения);
    # без --yes — PermissionError (критерий 30).
    try:
        agent.update_invariant("framework.django", "Использовать FastAPI", authorized=False)
        assert False, "ожидался PermissionError"
    except PermissionError:
        pass
    agent.update_invariant("framework.django", "Использовать FastAPI", authorized=True)
    assert agent.constraints.by_id("framework.django").description == "Использовать FastAPI"

    # Чтобы запрос «перейти на FastAPI» прошёл, правило меняется явно: прежнее
    # отключается, добавляется новое (архитектурное решение не меняется обычной фразой).
    agent.toggle_invariant("framework.django", False)
    agent.add_invariant(Invariant(id="framework.fastapi", category="architecture",
                                  description="Использовать FastAPI"))
    result2 = agent.propose_and_check("перейти на FastAPI")
    assert result2["allowed"] is True

    assert "[Инварианты]" in "\n".join(logs)
    print("[scenario] конфликт запроса и инварианта (отказ + изменение) OK")


def main():
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="scn_", dir=TMP_ROOT)
    scenario_interview(tmp)
    scenario_routing(tmp)
    scenario_dosed_delivery(tmp)
    scenario_influence(tmp)
    scenario_resume(tmp)
    scenario_personalization(tmp)
    scenario_pause_resume(tmp)
    scenario_invariant_conflict(tmp)
    print("SCENARIO OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())