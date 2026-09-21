# -*- coding: utf-8 -*-
"""Юнит-тесты state machine: этапы, разрешённые/запрещённые переходы.

Мигрировано с задела дней 11–12 (Enum TaskState из 4 стадий) на канон Дня 13:
Enum этапов — TaskStage (6: 4 базовых + paused/failed как расширения), проверка
переходов — next_state()/ALLOWED_TRANSITIONS. Полный автомат (dataclass TaskState,
pause/resume, save/load, run_task) покрыт в test_fsm.py.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import TaskStage, ALLOWED_TRANSITIONS, next_state


def test_four_stages():
    # Канон: 4 базовых этапа присутствуют (расширяем, не сужаем) + paused/failed.
    base = {"planning", "execution", "validation", "done"}
    values = {s.value for s in TaskStage}
    assert base <= values
    assert values == base | {"paused", "failed"}


def test_allowed_transitions():
    assert next_state(TaskStage.PLANNING, TaskStage.EXECUTION)
    assert next_state(TaskStage.EXECUTION, TaskStage.VALIDATION)
    assert next_state(TaskStage.EXECUTION, TaskStage.PLANNING)
    assert next_state(TaskStage.VALIDATION, TaskStage.EXECUTION)
    assert next_state(TaskStage.VALIDATION, TaskStage.PLANNING)
    assert next_state(TaskStage.VALIDATION, TaskStage.DONE)


def test_forbidden_transitions():
    assert not next_state(TaskStage.PLANNING, TaskStage.DONE)
    assert not next_state(TaskStage.DONE, TaskStage.PLANNING)
    assert not next_state(TaskStage.PLANNING, TaskStage.VALIDATION)


def test_done_terminal():
    assert ALLOWED_TRANSITIONS[TaskStage.DONE] == set()


def test_paused_and_failed_extensions():
    # paused — выход только через resume_task() (не через transition): множество пустое.
    assert ALLOWED_TRANSITIONS[TaskStage.PAUSED] == set()
    # failed — восстановление только явным переходом в planning (/task retry).
    assert ALLOWED_TRANSITIONS[TaskStage.FAILED] == {TaskStage.PLANNING}
    # пауза допустима с любого рабочего этапа.
    for stage in (TaskStage.PLANNING, TaskStage.EXECUTION, TaskStage.VALIDATION):
        assert next_state(stage, TaskStage.PAUSED)
