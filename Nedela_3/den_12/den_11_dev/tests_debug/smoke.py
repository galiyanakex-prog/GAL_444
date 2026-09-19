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
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent


def test_full_cycle_in_process():
    """Память → промт → агент → ответ на MockClient (in-process)."""
    tmp = tempfile.mkdtemp(prefix="den11_smoke_")
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
    """Полный цикл через den_11_Kod.py --mock: интервью → обмен → /memory → exit.

    Использует изолированный --memory-dir (/tmp) — прогон идемпотентен и не трогает
    рабочие users/ дня (§7.1, §2.1: тестовые артефакты — только /tmp).
    """
    tmp = tempfile.mkdtemp(prefix="den11_smoke_cli_")
    stdin = "cli_user\nИван\nкраткий\nPython\nобучение\nПривет!\n/memory\n/exit\n"
    env = dict(os.environ)
    env["API_KEY"] = "test-key"  # гарантируем MockClient-ветку
    proc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "den_11_Kod.py"),
         "--mock", "--memory-dir", os.path.join(tmp, "users")],
        input=stdin, capture_output=True, text=True, timeout=60, env=env,
        cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "Инициализация" in out, out
    assert "вижу" in out, out
    assert "[Память]" in out, out
    print("[smoke] CLI subprocess цикл OK (exit 0)")



def main():
    test_full_cycle_in_process()
    test_cli_subprocess()
    print("SMOKE OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
