"""core/tools.py — внутренняя модель инструментов агента (День 16).

Контракты без MCP SDK и без сети: модель MCP не протекает в core.
`ToolDescriptor` — модель агента, а не MCP; имена квалифицируются
(`mcp.<server>.<tool>` | `local.<tool>`).

Поля `risk_level` / `allowed_stages` / `requires_confirmation` — задел
policy pipeline (день 17+): в День 16 заполняются дефолтами.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# 5 рабочих стадий дня 15 (строками — контракты не зависят от state_machine;
# задел policy-фильтра инструментов по стадиям)
ALL_WORKING_STAGES: frozenset[str] = frozenset(
    {
        "new",
        "planning",
        "plan_approved",
        "implementation",
        "validation",
    }
)


@dataclass(frozen=True)
class ToolDescriptor:
    """Один инструмент в форме, понятной агенту (внутренняя модель)."""

    name: str                       # квалифицированное: "mcp.demo.get_time" | "local.echo"
    description: str
    input_schema: dict
    source: str                     # "local" | "mcp"
    provider: str                   # server_id (mcp) | "local"
    original_name: str              # имя тула на сервере ("get_time")
    # заделы policy pipeline (день 17+)
    risk_level: str = "unknown"
    allowed_stages: frozenset[str] = field(default_factory=lambda: ALL_WORKING_STAGES)
    requires_confirmation: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class ToolCallRequest:
    """Запрос вызова инструмента (tools/call)."""

    name: str
    arguments: dict = field(default_factory=dict)
    call_id: str = ""               # id в протоколе tool-use (для связки с LLM)


@dataclass(frozen=True)
class ToolExecutionResult:
    """Результат вызова инструмента.

    `raw` — сырой ответ: только текущий execution context, никогда в память.
    """

    execution_id: str
    tool: str
    status: str                     # ToolExecutionState
    summary: str
    raw: object | None = None
    is_error: bool = False
    call_id: str = ""


class ToolExecutionState(str, Enum):
    """Инфраструктурные состояния вызова инструмента (НЕ TaskStage)."""

    REQUESTED = "requested"
    DENIED = "denied"
    WAITING_CONFIRMATION = "waiting_confirmation"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class ToolProvider(ABC):
    """Единый интерфейс источников инструментов (local, mcp, …)."""

    @abstractmethod
    def provider_id(self) -> str:
        """Идентификатор источника (например, "mcp")."""

    @abstractmethod
    def discover(self) -> list[ToolDescriptor]:
        """Обнаружить инструменты источника → список дескрипторов."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class ToolCatalogSnapshot:
    """Атомарная версия каталога инструментов.

    Реестр хранит текущий snapshot целиком; обновление — только полным
    snapshot (никогда «по одному инструменту»): один запрос модели никогда
    не видит «половину старого и половину нового» каталога.
    """

    version: int
    tools: tuple[ToolDescriptor, ...]
    created_at: str = field(default_factory=_now_iso)
