"""integrations/mcp/gateway.py — шлюз MCP (День 16).

Адаптер внешних возможностей, НЕ контролёр: не знает о TaskStage/профилях/
памяти (канон Рекомендации_MCP_d16.txt). Async внутри, синхронный фасад
(`MCPGatewaySync`) наружу — REPL остаётся синхронным.
"""

from __future__ import annotations

import asyncio
import threading
from enum import Enum

from core.tools import ToolDescriptor
from integrations.mcp.client import MCPClient
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import MCPConnectionError, MCPTransport


class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"    # часть серверов недоступна
    FAILED = "failed"


class MCPGateway:
    """Шлюз: состояние подключения по серверам + discovery с фильтром прав."""

    def __init__(self, servers: list[MCPServerConfig],
                 transports: dict[str, MCPTransport] | None = None) -> None:
        self._servers = list(servers)
        self._transports = dict(transports or {})
        self._clients: dict[str, MCPClient] = {}
        self._states: dict[str, MCPConnectionState] = {
            s.server_id: MCPConnectionState.DISCONNECTED for s in self._servers
        }

    # -- служебное -----------------------------------------------------------

    def _make_client(self, server: MCPServerConfig) -> MCPClient:
        transport = self._transports.get(server.server_id)
        if transport is None:
            from integrations.mcp.transport import StdioMCPTransport
            transport = StdioMCPTransport(
                server.server_id, server.command or ("python", "-m",
                                                     "integrations.mcp.demo_server"),
                server.timeout_seconds,
            )
        return MCPClient(server, transport=transport)

    def overall_state(self) -> MCPConnectionState:
        states = [s for s in self._states.values() if s is not MCPConnectionState.DISCONNECTED]
        if not states:
            return MCPConnectionState.DISCONNECTED
        if all(s is MCPConnectionState.READY for s in states):
            return MCPConnectionState.READY
        if any(s is MCPConnectionState.READY for s in states):
            return MCPConnectionState.DEGRADED
        return MCPConnectionState.FAILED

    # -- жизненный цикл -------------------------------------------------------

    async def start(self) -> None:
        """Подключение ко всем включённым серверам (сбой одного — не падение)."""
        for server in self._servers:
            if not server.enabled:
                continue
            self._states[server.server_id] = MCPConnectionState.CONNECTING
            client = self._make_client(server)
            try:
                await client.initialize()
                self._clients[server.server_id] = client
                self._states[server.server_id] = MCPConnectionState.READY
                print(f"[MCP] «{server.server_id}»: подключён (READY)")
            except MCPConnectionError as exc:
                self._states[server.server_id] = MCPConnectionState.FAILED
                print(f"[MCP] «{server.server_id}»: FAILED — {exc.reason}")

    async def stop(self) -> None:
        """Чистое закрытие всех соединений → DISCONNECTED (у всех серверов)."""
        for server_id, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception:
                pass
            print(f"[MCP] «{server_id}»: отключён")
        self._clients.clear()
        # FAILED-серверы не имеют клиента, но состояние тоже сбрасываем:
        # канон (arch_den_16.md §2.4): stop() → DISCONNECTED.
        for server_id in self._states:
            self._states[server_id] = MCPConnectionState.DISCONNECTED

    def status(self) -> dict:
        """Состояние по серверам (для /mcp status)."""
        return {
            "overall": self.overall_state().value,
            "servers": {
                sid: state.value for sid, state in self._states.items()
            },
        }

    # -- discovery -------------------------------------------------------------

    async def discover(self) -> list[ToolDescriptor]:
        """list_tools у серверов в READY → фильтр прав → ToolDescriptor[]."""
        result: list[ToolDescriptor] = []
        for server in self._servers:
            if not server.enabled:
                continue
            client = self._clients.get(server.server_id)
            if client is None:  # FAILED/DISCONNECTED — тулов нет (каталог честен)
                continue
            try:
                raw_tools = await client.list_tools()
            except MCPConnectionError as exc:
                self._states[server.server_id] = MCPConnectionState.FAILED
                print(f"[MCP] «{server.server_id}»: discovery не удался — {exc.reason}")
                continue
            for item in raw_tools:
                original = item["name"]
                # изоляция прав через тулинг (канон Суть_N4 §3.3)
                if original in server.denied_tools:
                    continue
                if server.allowed_tools and original not in server.allowed_tools:
                    continue
                result.append(ToolDescriptor(
                    name=f"mcp.{server.server_id}.{original}",
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema") or {"type": "object"},
                    source="mcp",
                    provider=server.server_id,
                    original_name=original,
                ))
        return result


class MCPGatewaySync:
    """Тонкий синхронный фасад над async-шлюзом (REPL / --mcp-probe).

    Один постоянный фоновый event loop на всё время жизни фасада: сессии
    `mcp` SDK привязаны к задачам loop'а, где прошёл initialize, поэтому
    отдельный `asyncio.run()` на каждый вызов зависал бы на list_tools.
    """

    def __init__(self, servers: list[MCPServerConfig],
                 transports: dict[str, MCPTransport] | None = None) -> None:
        self._gateway = MCPGateway(servers, transports)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-gateway-loop", daemon=True
        )
        self._thread.start()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def start(self) -> None:
        self._run(self._gateway.start())

    def stop(self) -> None:
        self._run(self._gateway.stop())

    def status(self) -> dict:
        return self._gateway.status()

    def discover(self) -> list[ToolDescriptor]:
        return self._run(self._gateway.discover())

    @property
    def gateway(self) -> MCPGateway:
        return self._gateway
