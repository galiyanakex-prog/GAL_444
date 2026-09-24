"""integrations/mcp/transport.py — транспорты MCP (День 16).

ABC + stdio-транспорт (обёртка над `mcp` SDK) + детерминированная заглушка
`FakeMCPTransport` для тестов без сети и без подпроцесса.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MCPConnectionError(Exception):
    """Сбой соединения/вызова MCP: не None, не молчание."""

    def __init__(self, server_id: str, reason: str):
        self.server_id = server_id
        self.reason = reason
        super().__init__(f"MCP «{server_id}»: {reason}")


class MCPTransport(ABC):
    """Транспорт одного MCP-сервера (async — нативно для SDK)."""

    @abstractmethod
    async def initialize(self) -> dict:
        """Handshake: protocol version + capabilities → dict состояния."""

    @abstractmethod
    async def list_tools(self) -> list[dict]:
        """Сырые описания тулов: [{name, description, inputSchema}, ...]."""

    async def call_tool(self, name: str, arguments: dict) -> object:
        """Задел дня 17+ (tools/call)."""
        raise NotImplementedError("tools/call — задел дня 17+")

    @abstractmethod
    async def close(self) -> None:
        """Чистое закрытие соединения."""


class FakeMCPTransport(MCPTransport):
    """Детерминированная заглушка: фиксированный список тулов + программируемые
    отказы/таймаут/is_error/смена каталога. Без сети и без подпроцесса."""

    def __init__(
        self,
        tools: list[dict] | None = None,
        *,
        fail_initialize: bool = False,
        fail_list_tools: bool = False,
        timeout: bool = False,
        server_id: str = "fake",
    ) -> None:
        self._tools: list[dict] = list(tools or [])
        self._fail_initialize = fail_initialize
        self._fail_list_tools = fail_list_tools
        self._timeout = timeout
        self._server_id = server_id
        self._initialized = False

    def set_tools(self, tools: list[dict]) -> None:
        """Смена каталога (для теста обновлений)."""
        self._tools = list(tools)

    async def initialize(self) -> dict:
        if self._fail_initialize:
            raise MCPConnectionError(self._server_id, "handshake не удался")
        if self._timeout:
            raise MCPConnectionError(self._server_id, "таймаут handshake")
        self._initialized = True
        return {"protocolVersion": "2025-06-18", "serverInfo": {"name": self._server_id}}

    async def list_tools(self) -> list[dict]:
        if not self._initialized:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        if self._fail_list_tools:
            raise MCPConnectionError(self._server_id, "list_tools не удался")
        if self._timeout:
            raise MCPConnectionError(self._server_id, "таймаут list_tools")
        return [dict(t) for t in self._tools]

    async def close(self) -> None:
        self._initialized = False


class StdioMCPTransport(MCPTransport):
    """stdio-транспорт: подпроцесс по `command` из конфига, обёртка над `mcp` SDK.

    Фактический API SDK (mcp 2.2.0) — `mcp.client.stdio.stdio_client` +
    `mcp.ClientSession`; ошибки SDK → MCPConnectionError.
    """

    def __init__(self, server_id: str, command: tuple[str, ...],
                 timeout_seconds: float = 30.0) -> None:
        self._server_id = server_id
        self._command = command
        self._timeout = timeout_seconds
        self._session = None
        self._streams = None

    async def initialize(self) -> dict:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:  # SDK недоступен
            raise MCPConnectionError(self._server_id, f"SDK недоступен: {exc}") from exc

        params = StdioServerParameters(
            command=self._command[0], args=list(self._command[1:])
        )
        try:
            self._streams = stdio_client(params)
            read, write = await self._streams.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            init = await self._session.initialize()
        except Exception as exc:
            await self.close()
            raise MCPConnectionError(self._server_id, f"handshake не удался: {exc}") from exc
        return {
            "protocolVersion": getattr(init, "protocolVersion", None)
            or (init.get("protocolVersion") if isinstance(init, dict) else None),
            "serverInfo": getattr(init, "serverInfo", None)
            or (init.get("serverInfo") if isinstance(init, dict) else None),
        }

    async def list_tools(self) -> list[dict]:
        if self._session is None:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        try:
            result = await self._session.list_tools()
        except Exception as exc:
            raise MCPConnectionError(self._server_id, f"list_tools не удался: {exc}") from exc
        tools = getattr(result, "tools", None) or (result.get("tools") if isinstance(result, dict) else [])
        raw: list[dict] = []
        for t in tools:
            name = getattr(t, "name", None) or (t.get("name") if isinstance(t, dict) else None)
            desc = getattr(t, "description", None) or (t.get("description") if isinstance(t, dict) else "")
            schema = getattr(t, "inputSchema", None) or (t.get("inputSchema") if isinstance(t, dict) else {"type": "object"})
            raw.append({"name": name, "description": desc or "", "inputSchema": schema or {"type": "object"}})
        return raw

    async def close(self) -> None:
        for obj in (self._session, self._streams):
            if obj is not None:
                try:
                    await obj.__aexit__(None, None, None)
                except Exception:
                    pass
        self._session = None
        self._streams = None
