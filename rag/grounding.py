# -*- coding: utf-8 -*-
"""Проверка опоры ответа на источники — реализация на этапе 9 (мастер-план §4).

На этапе 0 модуль объявлен как контракт. Вызов бросает NotImplementedError,
чтобы ни один потребитель не получил «тихую» заглушку вместо результата.
"""
from __future__ import annotations

STAGE = 9


def _todo(what: str):
    raise NotImplementedError(
        f"rag: {what} ещё не реализован (этап {STAGE} плана dev/migr_plan.md)")


def ground(answer: str, hits: list, cfg):
    _todo("grounding.ground")

