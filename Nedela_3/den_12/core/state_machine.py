# -*- coding: utf-8 -*-
"""Задел под task state machine: TaskState + ALLOWED_TRANSITIONS.

В Дне 11 — только структура и хранение текущей стадии в рабочей памяти.
Логика переходов и проверка инвариантов — следующие дни недели 3.
"""
from enum import Enum


class TaskState(Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    DONE = "done"


# Разрешённые переходы (канон: planning → execution → validation → done).
ALLOWED_TRANSITIONS = {
    TaskState.PLANNING: {TaskState.EXECUTION},
    TaskState.EXECUTION: {TaskState.VALIDATION, TaskState.PLANNING},
    TaskState.VALIDATION: {TaskState.EXECUTION, TaskState.PLANNING},
    TaskState.DONE: set(),
}


def next_state(current: TaskState, target: TaskState) -> bool:
    """Проверяет, разрешён ли переход current → target (задел, логику не ведём)."""
    return target in ALLOWED_TRANSITIONS.get(current, set())