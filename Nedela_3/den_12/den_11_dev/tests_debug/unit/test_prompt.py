# -*- coding: utf-8 -*-
"""Юнит-тесты PromptBuilder: блоки, дозированная доставка, бюджет."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.prompt_builder import PromptBuilder


class FakeCtx:
    def __init__(self, query, memory_blocks, summary="", short_term_messages=None):
        self.query = query
        self.memory_blocks = memory_blocks
        self.summary = summary
        self.short_term_messages = short_term_messages or []


def make_builder():
    return PromptBuilder("Ты ассистент", token_estimator=lambda t: max(1, len(t) // 4))


def test_blocks_order():
    builder = make_builder()
    ctx = FakeCtx("вопрос", {"profile": "Имя: Аня", "long_term": "Факт"})
    messages = builder.build(ctx, {"profile", "long_term"})
    texts = [m["content"] for m in messages]
    assert texts[0] == "Ты ассистент"
    assert any("профиль" in t.lower() or "Имя" in t for t in texts)
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "вопрос"


def test_dosed_delivery_cut_layer():
    builder = make_builder()
    ctx = FakeCtx("вопрос", {"profile": "Имя", "long_term": "Факт", "working": "Задача"})
    # Без long_term — слой опущен осознанно.
    messages = builder.build(ctx, {"profile", "working"})
    joined = " ".join(m["content"] for m in messages)
    assert "Факт" not in joined
    assert "Имя" in joined


def test_budget_trims_optional():
    builder = make_builder()
    ctx = FakeCtx("вопрос", {"profile": "Имя: Аня"})
    # Бюджет 1 токен: роль + текущий запрос проходят, profile (опциональный) — нет.
    messages = builder.build(ctx, {"profile"}, budget=1)
    joined = " ".join(m["content"] for m in messages)
    assert "Имя" not in joined
    assert messages[-1]["content"] == "вопрос"


def test_summary_block():
    builder = make_builder()
    ctx = FakeCtx("вопрос", {"profile": "Имя"}, summary="Саммари префикса")
    messages = builder.build(ctx, {"profile", "summary"})
    joined = " ".join(m["content"] for m in messages)
    assert "Саммари префикса" in joined