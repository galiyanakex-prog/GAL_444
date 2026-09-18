# -*- coding: utf-8 -*-
"""Сборка промта явными блоками + дозированная доставка + токен-бюджет.

Порядок блоков (канон):
  [system: роль] → [system: профиль] → [system: долговременная] →
  [system: рабочая] → [system: summary общего префикса, опц.] →
  [messages: краткосрочная] → [user: текущий запрос] → [резерв].

Набор включаемых слоёв — параметр deliver: set[str]. Минимум один режим с
урезанным набором (часть типов памяти опущена осознанно).
"""
from typing import Optional

# Канонический порядок блоков промта.
BLOCK_ORDER = ("role", "profile", "long_term", "working", "summary", "short_term", "current")


class PromptBuilder:
    def __init__(self, role_prompt: str, token_estimator=None):
        self.role_prompt = role_prompt
        self.token_estimator = token_estimator or (lambda text: max(1, len(text) // 4))

    def build(self, ctx, deliver: set, budget: Optional[int] = None) -> list:
        """Собирает список сообщений API по блокам в каноническом порядке.

        deliver — набор имён слоёв памяти для включения. budget — лимит токенов
        (при превышении блоки урезаются по порядку, начиная с необязательных).
        """
        messages = []

        # Блоки собираем в порядке BLOCK_ORDER с флагом «обязательность» (для бюджета).
        blocks = []

        # 1. Роль.
        blocks.append(("role", True, {"role": "system", "content": self.role_prompt}))

        # 2..5. Слои памяти (profile/long_term/working/short_term) — только если в deliver.
        layers = getattr(ctx, "memory_blocks", {})
        for name in ("profile", "long_term", "working"):
            if name in deliver and name in layers:
                blocks.append((name, False, {"role": "system", "content": f"[{name}]\n{layers[name]}"}))

        # 6. Summary общего префикса (опционально).
        summary = getattr(ctx, "summary", "")
        if summary and "summary" in deliver:
            blocks.append(("summary", False, {"role": "system", "content": f"Саммари:\n{summary}"}))

        # 7. Краткосрочная память (сообщения) — если включена.
        short_term = getattr(ctx, "short_term_messages", [])
        if "short_term" in deliver:
            for m in short_term:
                blocks.append(("short_term", False, {"role": m["role"], "content": m["content"]}))

        # 8. Текущий запрос.
        blocks.append(("current", True, {"role": "user", "content": ctx.query}))

        # Применяем блоки с учётом бюджета: обязательные идут всегда.
        used = 0
        for name, required, msg in blocks:
            tokens = self.token_estimator(msg["content"])
            if budget is not None and not required and used + tokens > budget:
                # Урезанный режим: необязательный блок опускается осознанно.
                continue
            messages.append(msg)
            used += tokens

        return messages
