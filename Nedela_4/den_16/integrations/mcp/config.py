"""integrations/mcp/config.py — конфигурация MCP-серверов (День 16).

Загрузка `users/<id>/integrations/mcp/servers.json` с дефолтами: битый или
отсутствующий файл не роняет приложение — возвращается конфиг по умолчанию
(демо-сервер, единственный в День 16).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

# Реальный MCP-сервер (погода) недели 4; переопределяется env-переменной.
WEATHER_MCP_URL = os.getenv("MCP_WEATHER_URL", "https://weatherapi.projecteol.ru/mcp/")


@dataclass(frozen=True)
class MCPServerConfig:
    """Конфиг одного MCP-сервера (изоляция прав через тулинг)."""

    server_id: str
    transport: str = "stdio"            # "stdio" | "http" (задел)
    command: tuple[str, ...] | None = None
    endpoint: str | None = None         # задел HTTP-транспорта
    enabled: bool = True
    trust_level: str = "low"
    allowed_tools: frozenset[str] = field(default_factory=frozenset)  # пусто = все
    denied_tools: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 30.0
    max_result_bytes: int = 65536


# Реальные серверы Дня 16 (Ревизия 2): основной — погодный HTTP-сервер недели;
# локальный демо-сервер (stdio) сохранён для детерминированных тестов.
DEFAULT_SERVERS: tuple[MCPServerConfig, ...] = (
    MCPServerConfig(
        server_id="weather",
        transport="http",
        endpoint=WEATHER_MCP_URL,
        enabled=True,
        trust_level="low",
    ),
    MCPServerConfig(
        server_id="demo",
        transport="stdio",
        # sys.executable: интерпретатор текущего процесса (venv недели) —
        # «python» в PATH этой системы отсутствует, демо-сервер не поднимался.
        command=(sys.executable, "-m", "integrations.mcp.demo_server"),
        enabled=False,   # по умолчанию активен реальный сервер; demo — для тестов
        trust_level="low",
    ),
)


def _parse_server(raw: dict) -> MCPServerConfig | None:
    """Словарь → MCPServerConfig; неизвестные ключи игнорируются."""
    if not isinstance(raw, dict) or not isinstance(raw.get("server_id"), str):
        return None
    command = raw.get("command")
    if isinstance(command, list):
        command = tuple(str(c) for c in command)
    elif isinstance(command, str):
        command = (command,)
    else:
        command = None
    allowed = raw.get("allowed_tools") or []
    denied = raw.get("denied_tools") or []
    return MCPServerConfig(
        server_id=raw["server_id"],
        transport=str(raw.get("transport", "stdio")),
        command=command,
        endpoint=raw.get("endpoint"),
        enabled=bool(raw.get("enabled", True)),
        trust_level=str(raw.get("trust_level", "low")),
        allowed_tools=frozenset(str(t) for t in allowed),
        denied_tools=frozenset(str(t) for t in denied),
        timeout_seconds=float(raw.get("timeout_seconds", 30.0)),
        max_result_bytes=int(raw.get("max_result_bytes", 65536)),
    )


def load_servers_config(path: str | None) -> list[MCPServerConfig]:
    """Загрузить конфиг серверов; отсутствующий/битый файл → [DEFAULT_SERVERS]."""
    if not path:
        return list(DEFAULT_SERVERS)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return list(DEFAULT_SERVERS)
    raw_servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(raw_servers, list):
        return list(DEFAULT_SERVERS)
    servers = [cfg for cfg in (_parse_server(r) for r in raw_servers) if cfg]
    return servers or list(DEFAULT_SERVERS)
