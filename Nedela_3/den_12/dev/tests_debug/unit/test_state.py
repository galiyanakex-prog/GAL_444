# -*- coding: utf-8 -*-
"""Юнит-тесты state machine: 4 стадии, разрешённые переходы."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import TaskState, ALLOWED_TRANSITIONS, next_state


def test_four_stages():
    assert {s.value for s in TaskState} == {"planning", "execution", "validation", "done"}


def test_allowed_transitions():
    assert next_state(TaskState.PLANNING, TaskState.EXECUTION)
    assert next_state(TaskState.EXECUTION, TaskState.VALIDATION)
    assert next_state(TaskState.EXECUTION, TaskState.PLANNING)
    assert next_state(TaskState.VALIDATION, TaskState.EXECUTION)
    assert next_state(TaskState.VALIDATION, TaskState.PLANNING)


def test_forbidden_transitions():
    assert not next_state(TaskState.PLANNING, TaskState.DONE)
    assert not next_state(TaskState.DONE, TaskState.PLANNING)
    assert not next_state(TaskState.PLANNING, TaskState.VALIDATION)


def test_done_terminal():
    assert ALLOWED_TRANSITIONS[TaskState.DONE] == set()