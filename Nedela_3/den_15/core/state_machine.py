# -*- coding: utf-8 -*-
"""Task State Machine — конечный автомат состояния задачи (День 13).

Задел дней 11–12 (Enum из 4 стадий + next_state()) развёрнут в полный автомат
по канону `Задание_Д13.txt` и `ND/arch/arch_den_13.md` §2.2–2.5:

  * TaskStage  — enum из 6 этапов (4 базовых + paused/failed как расширения);
  * TaskState  — dataclass состояния (этап / текущий шаг / ожидаемое действие);
  * ALLOWED_TRANSITIONS + transition() — единственная точка смены этапа;
  * pause_task()/resume_task() — пауза на любом рабочем этапе и продолжение
    с того же места (без повторного плана и без повторных объяснений);
  * save_state()/load_state() — персистентность в JSON (переживает перезапуск);
  * run_task() — один проход автомата (planning → execution → validation → done).

Главная идея задания: LLM составляет план и наполняет шаги, но отдельный
Python-код управляет жизненным циклом задачи через явные переходы.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional


class TaskStage(str, Enum):
    """Этап задачи. 4 базовых (канон) + paused/failed — расширения, не замены."""

    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    PAUSED = "paused"        # расширение: пауза на любом рабочем этапе
    DONE = "done"
    FAILED = "failed"        # расширение: ошибка валидации/исполнения


@dataclass
class TaskState:
    """Формализованное состояние задачи (канон `Задание_Д13.txt`).

    В любой момент явно записаны: этап (stage), текущий шаг (current_step +
    steps), ожидаемое действие (expected_action).
    """

    task_id: str
    objective: str

    stage: TaskStage = TaskStage.PLANNING
    current_step: int = 0
    steps: list = field(default_factory=list)

    expected_action: Optional[str] = None
    results: list = field(default_factory=list)

    previous_stage: Optional[TaskStage] = None   # куда вернуться после паузы
    error: Optional[str] = None


# Разрешённые переходы (канон: planning → execution → validation → done;
# paused/failed — расширения). Единственная карта, которую проверяет transition().
ALLOWED_TRANSITIONS = {
    TaskStage.PLANNING:   {TaskStage.EXECUTION, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.EXECUTION:  {TaskStage.VALIDATION, TaskStage.PLANNING,
                           TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.VALIDATION: {TaskStage.DONE, TaskStage.EXECUTION, TaskStage.PLANNING,
                           TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PAUSED:     set(),                    # выход только через resume_task()
    TaskStage.DONE:       set(),                    # терминальная
    TaskStage.FAILED:     {TaskStage.PLANNING},     # восстановление — явный /task retry
}


def _noop(line: str) -> None:
    """Пустой логгер по умолчанию (модуль не зависит от печати)."""
    return None


def transition(state: TaskState, target: TaskStage, log: Callable = None) -> bool:
    """Единственная точка смены этапа: проверка ALLOWED_TRANSITIONS + лог.

    Возвращает True, если переход разрешён и выполнен; False — если запрещён
    (состояние не меняется, в лог пишется ворнинг). «Код запрещает, промт
    рекомендует»: запрещённый переход не выполняется никогда.
    """
    log = log or _noop
    allowed = ALLOWED_TRANSITIONS.get(state.stage, set())
    if target not in allowed:
        log(f"[Автомат] переход запрещён: {state.stage.value} → {target.value}")
        return False
    previous = state.stage
    state.stage = target
    log(f"[Автомат] {previous.value} → {target.value}")
    return True


def next_state(current: TaskStage, target: TaskStage) -> bool:
    """Тонкая обёртка (обратная совместимость с заделом дней 11–12).

    Проверяет, разрешён ли переход этапа current → target, без изменения
    состояния. Используется старым test_state.py до его миграции (Этап 6).
    """
    return target in ALLOWED_TRANSITIONS.get(current, set())


def pause_task(state: TaskState) -> TaskState:
    """Пауза на любом рабочем этапе. paused — НЕ потеря состояния.

    Сохраняет previous_stage и позицию шага; идемпотентна (повторная пауза — no-op).
    expected_action НЕ перезаписывается: канонический test_pause_and_resume
    (`Задание_Д13.txt`) и JSON-снимок paused в том же первоисточнике требуют, чтобы
    после resume ожидаемое действие было восстановлено («Собрать информацию», а не
    служебная строка). Факт паузы несёт сам stage == PAUSED.
    """
    if state.stage == TaskStage.PAUSED:
        return state
    state.previous_stage = state.stage
    state.stage = TaskStage.PAUSED
    return state


def resume_task(state: TaskState) -> TaskState:
    """Продолжение после паузы — возврат в previous_stage с того же шага.

    Идемпотентна: если задача не на паузе — no-op (состояние не меняется).
    current_step и expected_action не трогаются — планирование не перестраивается.
    """
    if state.stage != TaskStage.PAUSED:
        return state
    state.stage = state.previous_stage or TaskStage.EXECUTION
    state.previous_stage = None
    return state


def save_state(state: TaskState, filename: str) -> None:
    """Сохраняет состояние в JSON (канон задания).

    Enum сериализуются в .value (stage, previous_stage); ensure_ascii=False,
    indent=2 — человекочитаемый снимок на диске.
    """
    data = asdict(state)
    data["stage"] = state.stage.value
    data["previous_stage"] = state.previous_stage.value if state.previous_stage else None
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_state(filename: str) -> Optional[TaskState]:
    """Загружает состояние из JSON после «перезапуска».

    Обратная конверсия строк в TaskStage. Битый/отсутствующий файл → None
    (не роняет приложение: задача стартует с PLANNING).
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        data["stage"] = TaskStage(data["stage"])
        if data.get("previous_stage"):
            data["previous_stage"] = TaskStage(data["previous_stage"])
        return TaskState(**data)
    except (ValueError, KeyError, TypeError):
        return None


def run_task(state: TaskState, executor, validator: Callable, log: Callable = None) -> TaskState:
    """Один проход автомата (канон `Задание_Д13.txt` «Пример основного цикла»).

    executor — объект с .plan(objective) -> list[str] и .execute(step) -> Any
    (живая LLM или детерминированная заглушка); validator(results) -> bool.
    Каждый вызов = один атомарный шаг; завершённые шаги НЕ повторяются.
    """
    log = log or _noop

    if state.stage == TaskStage.PLANNING:
        # План составляет LLM (или MockClient); код только принимает список шагов.
        state.steps = list(executor.plan(state.objective))
        state.current_step = 0
        state.expected_action = "Перейти к выполнению"
        transition(state, TaskStage.EXECUTION, log)

    elif state.stage == TaskStage.EXECUTION:
        if state.current_step >= len(state.steps):
            state.expected_action = "Проверить результаты"
            transition(state, TaskStage.VALIDATION, log)
            return state
        step = state.steps[state.current_step]
        result = executor.execute(step)          # здесь агент вызывает инструмент/LLM
        state.results.append(result)
        state.current_step += 1
        # Ожидаемое действие — СЛЕДУЮЩИЙ шаг (семантика JSON-снимка из
        # `Задание_Д13.txt`: current_step=1 ↔ expected_action=steps[1]).
        if state.current_step < len(state.steps):
            state.expected_action = state.steps[state.current_step]
        else:
            state.expected_action = "Проверить результаты"

    elif state.stage == TaskStage.VALIDATION:
        if validator(state.results):
            state.expected_action = None
            transition(state, TaskStage.DONE, log)
        else:
            state.error = "Проверка результата не пройдена"
            transition(state, TaskStage.FAILED, log)

    return state
