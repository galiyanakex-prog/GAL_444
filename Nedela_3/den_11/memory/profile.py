# -*- coding: utf-8 -*-
"""Профиль пользователя: style + constraints + context (персонализация).

Три составляющие по лекции (Суть_N3 §3.4): стиль, констрейнты, контекст.
Профиль — отдельная сущность, JSON в SQLite (ProfileRepository).
"""
from .base import MemoryLayer, MemoryContext, MemoryItem


class Profile(MemoryLayer):
    layer_name = "profile"
    scope = "user"

    def read(self, ctx: MemoryContext) -> dict:
        profile = self.store.load_profile(ctx.user_id)
        if profile is None:
            return {}
        return profile

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Профиль — merge: обновляем только переданные поля, остальное сохраняем.
        current = self.read(ctx) or {"id": ctx.user_id, "name": "", "style": {},
                                     "constraints": {}, "context": {}}
        updates = item.content if isinstance(item.content, dict) else {}
        for key, value in updates.items():
            if key in ("style", "constraints", "context") and isinstance(value, dict):
                current.setdefault(key, {}).update(value)
            else:
                current[key] = value
        path = self.store.save_profile(ctx.user_id, current)
        self.log(f"[Память] profile ← {list(updates.keys())} → {path} (JSON в SQLite)")
        return f"profile.json ({list(updates.keys())})"

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        profile = self.read(ctx)
        if not profile:
            return ""
        lines = []
        if profile.get("name"):
            lines.append(f"Имя: {profile['name']}")
        style = profile.get("style", {})
        if style:
            lines.append("Стиль: " + "; ".join(f"{k}: {v}" for k, v in style.items()))
        constraints = profile.get("constraints", {})
        if constraints:
            lines.append("Ограничения: " + "; ".join(f"{k}: {v}" for k, v in constraints.items()))
        context = profile.get("context", {})
        if context:
            lines.append("Контекст: " + "; ".join(f"{k}: {v}" for k, v in context.items()))
        return "\n".join(lines)
