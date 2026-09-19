# -*- coding: utf-8 -*-
"""Юнит-тесты модели памяти: 4 класса, явная маршрутизация, дозированная доставка."""
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager, default_layers, LAYER_ORDER


def make_memory(tmp_path):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    return MemoryManager(default_layers(store), log=lambda line: None)


def test_four_layers_present(tmp_path):
    memory = make_memory(tmp_path)
    assert set(memory.layers.keys()) == {"short_term", "working", "long_term", "profile"}
    # Каждый тип — свой класс со своим layer_name.
    names = {layer.layer_name for layer in memory.layers.values()}
    assert names == {"short_term", "working", "long_term", "profile"}


def test_remember_routes_explicitly(tmp_path):
    memory = make_memory(tmp_path)
    ctx = MemoryContext("u1", "task1", "s1")
    where = memory.remember("working", ctx, content={"description": "задача"}, source="system")
    assert "working_memory.json" in where
    data = memory.layers["working"].read(ctx)
    assert data["description"] == "задача"


def test_dosed_delivery(tmp_path):
    memory = make_memory(tmp_path)
    ctx = MemoryContext("u1", "task1", "s1")
    memory.remember("working", ctx, content={"description": "x"}, source="system")
    blocks = memory.build_blocks({"working"}, ctx)
    assert "working" in blocks
    assert "long_term" not in blocks  # слой опущен осознанно


def test_profile_in_sqlite(tmp_path):
    memory = make_memory(tmp_path)
    ctx = MemoryContext("u2")
    memory.remember("profile", ctx, content={"id": "u2", "name": "Аня",
                                             "style": {}, "constraints": {}, "context": {}},
                    source="system")
    profile = memory.layers["profile"].read(ctx)
    assert profile["name"] == "Аня"


def test_short_term_append_and_parent(tmp_path):
    memory = make_memory(tmp_path)
    ctx = MemoryContext("u3", "task1", "s1")
    item1 = MemoryItem("привет", role="user", source="user")
    item2 = MemoryItem("пока", role="assistant", source="model")
    memory.layers["short_term"].write(ctx, item1)
    memory.layers["short_term"].write(ctx, item2)
    session = memory.layers["short_term"].read(ctx)
    msgs = session["messages"]
    assert len(msgs) == 2
    assert msgs[1]["parent_id"] == msgs[0]["id"]


def test_report_snapshot(tmp_path):
    memory = make_memory(tmp_path)
    ctx = MemoryContext("u4", "task1", "s1")
    report = memory.report(ctx)
    for name in LAYER_ORDER:
        assert f"[{name}]" in report