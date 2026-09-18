# -*- coding: utf-8 -*-
"""Рабочая память: пересчитываемое состояние задачи, НЕ лог сообщений.

Содержит (канон куратора): описание задачи, ссылки на сессии+таймкоды,
резюме жизненного цикла, структурированные блоки decisions/constraints/facts/
open_questions, плюс текущую стадию task state machine.
"""
from .base import MemoryLayer, MemoryContext, MemoryItem


class WorkingMemory(MemoryLayer):
    layer_name = "working"
    scope = "task"

    def read(self, ctx: MemoryContext) -> dict:
        return self.store.read_working(ctx.user_id, ctx.task)

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Рабочая память — состояние: пересчитываем/обновляем, а не дописываем.
        data = self.read(ctx)
        # item.content — словарь {поле: значение}, которым обновляем рабочую память.
        updates = item.content if isinstance(item.content, dict) else {}
        for key, value in updates.items():
            if key == "current_state":
                data[key] = value
            elif key in ("refs", "decisions", "constraints", "facts", "open_questions"):
                # Списки: refs дополняются, остальные — append нового элемента.
                if key == "refs":
                    data.setdefault(key, []).append(value)
                else:
                    data.setdefault(key, []).append({"text": value, "source_message_id": item.source_message_id})
            else:
                # description / lifecycle_summary и прочие скалярные поля.
                data[key] = value
        path = self.store.write_working(ctx.user_id, ctx.task, data)
        self.log(f"[Память] working ← {list(updates.keys())} → {path}")
        return f"working_memory.json {list(updates.keys())}"

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        data = self.read(ctx)
        lines = [f"Задача: {data.get('description') or (ctx.task or '(без названия)')}"]
        if data.get("lifecycle_summary"):
            lines.append(f"Резюме жизненного цикла: {data['lifecycle_summary']}")
        for field, label in (
            ("decisions", "Решения"),
            ("constraints", "Ограничения"),
            ("facts", "Факты"),
            ("open_questions", "Открытые вопросы"),
        ):
            items = data.get(field, [])
            if items:
                joined = "; ".join(item.get("text", item) for item in items)
                lines.append(f"{label}: {joined}")
        if data.get("current_state"):
            lines.append(f"Стадия задачи: {data['current_state']}")
        return "\n".join(lines)
