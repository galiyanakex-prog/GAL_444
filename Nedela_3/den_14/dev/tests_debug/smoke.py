# -*- coding: utf-8 -*-
"""L3 смоук-тест: полный цикл память→prompt→agent→CLI на MockClient.

Запуск: API_KEY=test-key $PY $TST/smoke.py
Выход 0 — цикл отработал; 1 — падение.
Не использует сеть: прогон через MockClient и подпроцесс CLI в --mock.
"""
import os
import subprocess
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


def test_full_cycle_in_process():
    """Память → промт → агент → ответ на MockClient (in-process)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_", dir=TMP_ROOT)
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    builder = PromptBuilder("Ты ассистент")
    agent = Agent(MockClient(), memory, builder, store, user_id="smoke_user")
    agent.initialize_user("smoke_user", "Т", {"style": "краткий",
                                              "constraints": "Python",
                                              "context": "тест"})
    answer = agent.respond("Привет, как дела?")
    assert answer is not None
    assert "вижу" in answer  # MockClient отражает контекст
    # Сообщение ушло в краткосрочную память.
    session = memory.layers["short_term"].read(
        MemoryContext("smoke_user", "Основная_задача", agent.session_id))
    assert len(session["messages"]) >= 2
    print("[smoke] in-process цикл OK")


def test_cli_subprocess():
    """Полный цикл через Kod.py --mock: интервью → обмен → /memory → exit.

    Использует изолированный --memory-dir (tests_debug/.tmp) — прогон идемпотентен и
    не трогает рабочие users/ дня (§7.1, §2.1: тестовые артефакты — только .tmp).
    Логи тоже изолированы (--log/--token-log в tmp): дефолты Kod.py пишут в корень проекта.
    """
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_cli_", dir=TMP_ROOT)
    stdin = "cli_user\nИван\nкраткий\nPython\nобучение\nПривет!\n/memory\n/exit\n"
    env = dict(os.environ)
    env["API_KEY"] = "test-key"  # гарантируем MockClient-ветку
    proc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "Kod.py"),
         "--mock", "--memory-dir", os.path.join(tmp, "users"),
         "--log", os.path.join(tmp, "log.md"),
         "--token-log", os.path.join(tmp, "tokens.csv")],
        input=stdin, capture_output=True, text=True, timeout=60, env=env,
        cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "Инициализация" in out, out
    assert "вижу" in out, out
    assert "[Память]" in out, out
    print("[smoke] CLI subprocess цикл OK (exit 0)")


def test_fsm_in_process():
    """Жизненный цикл автомата in-process: plan → step → pause → resume → run → done."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_fsm_", dir=TMP_ROOT)
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))

    def build():
        return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                     user_id="fsm_user", executor=StubExecutor(),
                     validator=default_validator)

    agent = build()
    agent.initialize_user("fsm_user", "Ф", {"style": "a", "constraints": "b", "context": "c"})
    agent.start_task("Найди три Python-фреймворка и сравни их")
    agent.step_task()                       # planning → execution
    assert agent.task_state.stage == TaskStage.EXECUTION
    agent.step_task()                       # шаг 0 выполнен
    assert agent.pause() is True
    assert agent.task_state.stage == TaskStage.PAUSED

    restarted = build()                     # «перезапуск» — тот же memory-dir
    restarted.load_state("fsm_user")
    assert restarted.task_state.stage == TaskStage.PAUSED
    assert restarted.resume() is True
    assert restarted.task_state.current_step == 1   # продолжение с того же шага
    restarted.run_to_end()
    assert restarted.task_state.stage == TaskStage.DONE
    assert len(restarted.task_state.results) == 3
    print("[smoke] жизненный цикл автомата in-process OK")


def test_cli_fsm_subprocess():
    """CLI-прогон команд жизненного цикла: /plan /step /pause /resume /run /state."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_cli_fsm_", dir=TMP_ROOT)
    stdin = ("cli_user\nИван\nкраткий\nPython\nобучение\n"
             "/plan Тестовая цель\n/step\n/pause\n/resume\n/run\n/state\n/exit\n")
    env = dict(os.environ)
    env["API_KEY"] = "test-key"
    proc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "Kod.py"),
         "--mock", "--memory-dir", os.path.join(tmp, "users"),
         "--log", os.path.join(tmp, "log.md"),
         "--token-log", os.path.join(tmp, "tokens.csv")],
        input=stdin, capture_output=True, text=True, timeout=60, env=env,
        cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    for marker in ("[План]", "[Шаг]", "[Пауза]", "[Продолжение]", "[Прогон]",
                   "[Состояние задачи]"):
        assert marker in out, (marker, out)
    assert "Этап: done" in out, out
    print("[smoke] CLI команды жизненного цикла OK (exit 0)")


def main():
    test_full_cycle_in_process()
    test_cli_subprocess()
    test_fsm_in_process()
    test_cli_fsm_subprocess()
    print("SMOKE OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
