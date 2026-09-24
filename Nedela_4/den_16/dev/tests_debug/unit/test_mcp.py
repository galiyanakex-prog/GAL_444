# -*- coding: utf-8 -*-
"""Юнит-тесты MCP-слоя (День 16): контракты, discovery, реестр, фильтры, персистентность.

Всё на FakeMCPTransport — без сети, без подпроцесса и живого ключа
(Рекомендации_MCP_d16.txt). Временные файлы — только через tmp_path раннера.
"""
import asyncio
import json
import os
import sys
from dataclasses import FrozenInstanceError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor, default_validator
from core.state_machine import TaskStage
from core.tools import ToolCatalogSnapshot, ToolDescriptor, ToolProvider
from core.tool_registry import ToolRegistry
from integrations.mcp.config import MCPServerConfig, DEFAULT_SERVERS, load_servers_config
from integrations.mcp.gateway import MCPGateway
from integrations.mcp.provider import MCPToolProvider
from integrations.mcp.transport import FakeMCPTransport

# Каталог демо-сервера (канон задания Дня 16): три тула.
DEMO_TOOLS = [
    {"name": "get_time", "description": "Текущее время",
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "echo", "description": "Повтор текста",
     "inputSchema": {"type": "object",
                     "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "weather_stub", "description": "Погода (заглушка)",
     "inputSchema": {"type": "object",
                     "properties": {"location": {"type": "string"},
                                    "units": {"type": "string"}},
                     "required": ["location"]}},
]


def fake_server(server_id="demo", **kwargs):
    return MCPServerConfig(server_id=server_id, transport="stdio",
                           command=("python",), **kwargs)


def make_gateway(servers=None, transports=None, tools=None, **transport_kwargs):
    """Шлюз на FakeMCPTransport (без сети/подпроцесса)."""
    servers = list(servers or [fake_server()])
    if transports is None:
        sid = servers[0].server_id
        transports = {sid: FakeMCPTransport(DEMO_TOOLS if tools is None else tools,
                                            server_id=sid, **transport_kwargs)}
    return MCPGateway(servers, transports)


class _StaticProvider(ToolProvider):
    """Заглушка провайдера (коллизии/атомарность/валидация схемы — без MCP)."""

    def __init__(self, pid, tools):
        self._pid = pid
        self._tools = list(tools)

    def provider_id(self):
        return self._pid

    def discover(self):
        return list(self._tools)

    def set_tools(self, tools):
        self._tools = list(tools)


def make_agent(tmp_path, logs=None, mcp=False):
    """Агент den_15 (наследие) с опциональным MCP-слоем на fake-транспорте."""
    log = logs.append if logs is not None else None
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo, log=log)
    memory = MemoryManager(default_layers(store, log=log), log=log)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="u", log=log, executor=StubExecutor(),
                  validator=default_validator)
    if mcp:
        gateway = make_gateway()
        registry = ToolRegistry()
        registry.add_provider(MCPToolProvider(gateway))
        agent.mcp_gateway = gateway
        agent.tool_registry = registry
    return agent


# --- 1. Контракты -------------------------------------------------------------

def test_tool_descriptor_contract():
    tool = ToolDescriptor(name="mcp.demo.get_time", description="Текущее время",
                          input_schema={"type": "object"}, source="mcp",
                          provider="demo", original_name="get_time")
    assert tool.name == "mcp.demo.get_time"
    assert tool.source == "mcp"
    assert tool.provider == "demo"
    assert tool.original_name == "get_time"
    # policy-заделы дня 17+ заполняются дефолтами
    assert tool.risk_level == "unknown"
    assert tool.requires_confirmation is False
    assert tool.enabled is True
    assert set(tool.allowed_stages) == set(
        ["new", "planning", "plan_approved", "implementation", "validation"])


def test_contracts_frozen():
    tool = ToolDescriptor(name="mcp.demo.echo", description="d",
                          input_schema={"type": "object"}, source="mcp",
                          provider="demo", original_name="echo")
    try:
        tool.name = "другое"
        assert False, "ожидался FrozenInstanceError"
    except FrozenInstanceError:
        pass
    snap = ToolCatalogSnapshot(version=1, tools=())
    try:
        snap.version = 2
        assert False, "ожидался FrozenInstanceError"
    except FrozenInstanceError:
        pass


# --- 2. Discovery-нормализация -------------------------------------------------

def test_provider_discover_normalization():
    tools = [
        {"name": "bare", "inputSchema": None},  # нет description, schema None → дефолты
        {"name": "full", "description": "Описание",
         "inputSchema": {"type": "object", "properties": {"x": {"type": "string"}}}},
    ]
    gateway = make_gateway(tools=tools)
    provider = MCPToolProvider(gateway)
    assert provider.provider_id() == "mcp"
    run_start = asyncio.run(gateway.start())
    assert run_start is None
    discovered = provider.discover()
    assert [t.name for t in discovered] == ["mcp.demo.bare", "mcp.demo.full"]
    bare, full = discovered
    assert bare.source == "mcp" and bare.provider == "demo"
    assert bare.original_name == "bare"
    assert bare.description == ""                    # дефолт описания
    assert bare.input_schema == {"type": "object"}   # дефолт схемы
    assert full.input_schema == {"type": "object", "properties": {"x": {"type": "string"}}}
    asyncio.run(gateway.stop())


# --- 3. Реестр ------------------------------------------------------------------

def test_registry_add_refresh_get():
    registry = ToolRegistry()
    gateway = make_gateway()
    registry.add_provider(MCPToolProvider(gateway))
    asyncio.run(gateway.start())
    snap = registry.refresh()
    assert snap.version == 1 and len(snap.tools) == 3
    tool = registry.get("mcp.demo.get_time")
    assert tool.provider == "demo" and tool.original_name == "get_time"
    try:
        registry.get("mcp.demo.nope")
        assert False, "ожидался KeyError"
    except KeyError as exc:
        assert "mcp.demo.get_time" in str(exc)   # перечень доступных в ошибке
    asyncio.run(gateway.stop())


def test_registry_unregister_leaves_catalog():
    registry = ToolRegistry()
    gateway = make_gateway()
    registry.add_provider(MCPToolProvider(gateway))
    asyncio.run(gateway.start())
    registry.refresh()
    registry.unregister_provider("mcp")
    snap = registry.refresh()
    assert snap.version == 2
    assert snap.tools == ()
    asyncio.run(gateway.stop())


def test_registry_excludes_invalid_schema():
    registry = ToolRegistry()
    bad = ToolDescriptor(name="local.bad", description="без схемы",
                         input_schema="не словарь", source="local",
                         provider="local", original_name="bad")
    good = ToolDescriptor(name="local.good", description="ок",
                          input_schema={"type": "object"}, source="local",
                          provider="local", original_name="good")
    registry.add_provider(_StaticProvider("local", [bad, good]))
    snap = registry.refresh()
    assert [t.name for t in snap.tools] == ["local.good"]


# --- 4. Коллизии -----------------------------------------------------------------

def test_cross_server_same_original_different_names():
    same = [{"name": "echo", "description": "Повтор текста",
             "inputSchema": {"type": "object"}}]
    gateway = MCPGateway([fake_server("alpha"), fake_server("beta")],
                         {"alpha": FakeMCPTransport(same, server_id="alpha"),
                          "beta": FakeMCPTransport(same, server_id="beta")})
    asyncio.run(gateway.start())
    tools = asyncio.run(gateway.discover())
    assert sorted(t.name for t in tools) == ["mcp.alpha.echo", "mcp.beta.echo"]
    asyncio.run(gateway.stop())


def test_qualified_collision_last_wins():
    registry = ToolRegistry()
    first = ToolDescriptor(name="local.dup", description="первый",
                           input_schema={"type": "object"}, source="local",
                           provider="local", original_name="dup")
    second = ToolDescriptor(name="local.dup", description="второй",
                            input_schema={"type": "object"}, source="local",
                            provider="local", original_name="dup")
    registry.add_provider(_StaticProvider("p1", [first]))
    registry.add_provider(_StaticProvider("p2", [second]))
    snap = registry.refresh()
    assert len(snap.tools) == 1                    # коллизия: один тул
    assert snap.tools[0].description == "второй"   # последний побеждает


# --- 5. Атомарность ---------------------------------------------------------------

def test_version_monotonic_snapshot_atomic():
    registry = ToolRegistry()
    tool_a = ToolDescriptor(name="local.a", description="v1",
                            input_schema={"type": "object"}, source="local",
                            provider="local", original_name="a")
    provider = _StaticProvider("local", [tool_a])
    registry.add_provider(provider)
    s1 = registry.refresh()
    assert s1.version == 1
    assert registry.snapshot() is s1
    # каталог изменился → refresh → новая версия; прежний snapshot остался целиком
    tool_b = ToolDescriptor(name="local.b", description="v2",
                            input_schema={"type": "object"}, source="local",
                            provider="local", original_name="b")
    provider.set_tools([tool_a, tool_b])
    s2 = registry.refresh()
    assert s2.version == 2 and len(s2.tools) == 2
    assert s1.version == 1 and len(s1.tools) == 1
    assert registry.snapshot() is s2
    # пустой discover → версия всё равно монотонно растёт
    provider.set_tools([])
    s3 = registry.refresh()
    assert s3.version == 3 and s3.tools == ()


# --- 6. Недоступный сервер ----------------------------------------------------------

def test_overall_states_all_paths():
    # нет активных серверов → disconnected
    gateway = make_gateway()
    assert gateway.status()["overall"] == "disconnected"
    # все READY → ready
    asyncio.run(gateway.start())
    assert gateway.status()["overall"] == "ready"
    asyncio.run(gateway.stop())
    # смесь READY + FAILED → degraded
    mixed = MCPGateway([fake_server("a"), fake_server("b")],
                       {"a": FakeMCPTransport(DEMO_TOOLS, server_id="a"),
                        "b": FakeMCPTransport([], fail_initialize=True, server_id="b")})
    asyncio.run(mixed.start())
    assert mixed.status()["overall"] == "degraded"
    # все FAILED → failed
    broken = make_gateway(fail_initialize=True)
    asyncio.run(broken.start())
    assert broken.status()["overall"] == "failed"


def test_failed_server_isolated():
    gateway = MCPGateway([fake_server("good"), fake_server("bad")],
                         {"good": FakeMCPTransport(DEMO_TOOLS, server_id="good"),
                          "bad": FakeMCPTransport([], fail_initialize=True, server_id="bad")})
    asyncio.run(gateway.start())   # сбой одного — не падение процесса
    status = gateway.status()
    assert status["servers"]["good"] == "ready"
    assert status["servers"]["bad"] == "failed"
    assert status["overall"] == "degraded"
    tools = asyncio.run(gateway.discover())   # живой сервер отдаёт тулы
    assert {t.name for t in tools} == {"mcp.good.get_time", "mcp.good.echo",
                                       "mcp.good.weather_stub"}
    asyncio.run(gateway.stop())
    assert gateway.status()["overall"] == "disconnected"


def test_discover_failure_marks_failed():
    gateway = make_gateway(fail_list_tools=True)
    asyncio.run(gateway.start())
    assert gateway.status()["overall"] == "ready"
    assert asyncio.run(gateway.discover()) == []   # тулов нет, не падение
    assert gateway.status()["overall"] == "failed"


# --- 7. Фильтр прав -------------------------------------------------------------------

def test_denied_tools_filtered():
    server = fake_server("demo", denied_tools=frozenset({"echo"}))
    gateway = MCPGateway([server], {"demo": FakeMCPTransport(DEMO_TOOLS, server_id="demo")})
    asyncio.run(gateway.start())
    names = [t.name for t in asyncio.run(gateway.discover())]
    assert "mcp.demo.echo" not in names
    assert "mcp.demo.get_time" in names
    asyncio.run(gateway.stop())


def test_allowed_tools_narrows():
    # непустой allowed сужает каталог; denied сильнее allowed (изоляция прав)
    server = fake_server("demo", allowed_tools=frozenset({"get_time", "echo"}),
                         denied_tools=frozenset({"echo"}))
    gateway = MCPGateway([server], {"demo": FakeMCPTransport(DEMO_TOOLS, server_id="demo")})
    asyncio.run(gateway.start())
    names = [t.name for t in asyncio.run(gateway.discover())]
    assert names == ["mcp.demo.get_time"]
    asyncio.run(gateway.stop())


# --- 8. Персистентность ----------------------------------------------------------------

def test_catalog_persistence_roundtrip(tmp_path):
    store = Store(str(tmp_path / "users"))
    gateway = make_gateway()
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    asyncio.run(gateway.start())
    snap = registry.refresh()
    # сериализация — та же, что в /mcp refresh (Kod.py)
    data = {
        "schema_version": 1,
        "version": snap.version,
        "tools": [{
            "name": t.name, "description": t.description,
            "input_schema": t.input_schema, "source": t.source,
            "provider": t.provider, "original_name": t.original_name,
            "risk_level": t.risk_level,
            "allowed_stages": sorted(t.allowed_stages),
            "requires_confirmation": t.requires_confirmation,
            "enabled": t.enabled,
        } for t in snap.tools],
        "created_at": snap.created_at,
    }
    store.save_tool_catalog("mcpu", data)
    loaded = store.read_tool_catalog("mcpu")
    assert loaded["schema_version"] == 1
    assert loaded["version"] == snap.version
    assert {t["name"] for t in loaded["tools"]} == {t.name for t in snap.tools}
    # восстановление дескрипторов из снимка (каталог переживает перезапуск)
    restored = [ToolDescriptor(name=t["name"], description=t["description"],
                               input_schema=t["input_schema"], source=t["source"],
                               provider=t["provider"], original_name=t["original_name"])
                for t in loaded["tools"]]
    assert {t.original_name for t in restored} == {"get_time", "echo", "weather_stub"}
    asyncio.run(gateway.stop())


def test_catalog_missing_or_broken_is_empty(tmp_path):
    store = Store(str(tmp_path / "users"))
    # отсутствующий файл → None → пустой каталог
    assert store.read_tool_catalog("nobody") is None
    # битый файл → None (не падение)
    broken = store.tool_catalog_path("broken")
    os.makedirs(os.path.dirname(broken), exist_ok=True)
    with open(broken, "w", encoding="utf-8") as fh:
        fh.write("{ не json")
    assert store.read_tool_catalog("broken") is None


# --- 9. MCP не трогает состояние ----------------------------------------------------------

def test_mcp_does_not_touch_task_state(tmp_path):
    agent = make_agent(tmp_path, mcp=True)
    agent.initialize_user("mcp9", "М", {"style": "a", "constraints": "b", "context": "c"})
    agent.start_task("Проверка неизменности автомата")
    agent.step_task()
    assert agent.task_state.stage is TaskStage.PLANNING
    stage_before = agent.task_state.stage
    log_before = len(agent.task_state.transition_log)

    # полный цикл MCP поверх живого автомата: connect → discover → refresh → stop
    gateway = agent.mcp_gateway
    asyncio.run(gateway.start())
    assert len(agent.tool_registry.refresh().tools) == 3
    asyncio.run(gateway.discover())
    asyncio.run(gateway.stop())

    # инструмент ≠ переход: стадия и журнал автомата не изменились
    assert agent.task_state.stage == stage_before
    assert len(agent.task_state.transition_log) == log_before


# --- 10. MCP off по умолчанию ----------------------------------------------------------------

def test_mcp_off_by_default(tmp_path):
    agent = make_agent(tmp_path)   # без MCP — как запуск без --mcp
    agent.initialize_user("mcp10", "Н", {"style": "a", "constraints": "b", "context": "c"})
    assert agent.mcp_gateway is None
    assert agent.tool_registry is None
    # поведение = den_15: обычный цикл память → промт → LLM
    assert agent.respond("какая у меня задача?") is not None


# --- 11. Конфиг --------------------------------------------------------------------------------

def test_load_servers_config_fallbacks(tmp_path):
    defaults = list(DEFAULT_SERVERS)
    assert load_servers_config(None) == defaults
    assert load_servers_config(str(tmp_path / "nope.json")) == defaults
    broken = tmp_path / "broken.json"
    broken.write_text("{не json", encoding="utf-8")
    assert load_servers_config(str(broken)) == defaults
    no_key = tmp_path / "no_key.json"
    no_key.write_text(json.dumps({"other": []}), encoding="utf-8")
    assert load_servers_config(str(no_key)) == defaults
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"servers": []}), encoding="utf-8")
    assert load_servers_config(str(empty)) == defaults


def test_load_servers_config_valid_ignores_unknown(tmp_path):
    path = tmp_path / "servers.json"
    path.write_text(json.dumps({
        "servers": [{"server_id": "s1", "transport": "stdio", "command": ["a", "b"],
                     "denied_tools": ["secret"], "allowed_tools": [],
                     "unknown_future_key": 42}]}), encoding="utf-8")
    servers = load_servers_config(str(path))
    assert len(servers) == 1
    cfg = servers[0]
    assert cfg.server_id == "s1"
    assert cfg.command == ("a", "b")
    assert cfg.denied_tools == frozenset({"secret"})


def test_default_servers_and_store_roundtrip(tmp_path):
    # дефолт: демо-сервер через sys.executable («python» в PATH отсутствует)
    cfg = DEFAULT_SERVERS[0]
    assert cfg.server_id == "demo" and cfg.transport == "stdio"
    assert cfg.command[0] == sys.executable
    assert cfg.command[-1] == "integrations.mcp.demo_server"
    # конфиг серверов переживает перезапуск (Store → load_servers_config)
    store = Store(str(tmp_path / "users"))
    assert store.read_mcp_servers("u") is None
    store.write_mcp_servers("u", {"servers": [
        {"server_id": "s1", "transport": "stdio",
         "command": [sys.executable, "-m", "x"]}]})
    servers = load_servers_config(store.mcp_servers_path("u"))
    assert servers[0].server_id == "s1"
    assert servers[0].command == (sys.executable, "-m", "x")
