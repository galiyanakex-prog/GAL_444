# -*- coding: utf-8 -*-
"""Кэш результатов поиска — реализация на этапе 10 (мастер-план §4).

На этапе 0 модуль объявлен как контракт. Вызов бросает NotImplementedError,
чтобы ни один потребитель не получил «тихую» заглушку вместо результата.
"""
from __future__ import annotations

STAGE = 10


def _todo(what: str):
    raise NotImplementedError(
        f"rag: {what} ещё не реализован (этап {STAGE} плана dev/migr_plan.md)")


class SearchCache:
    def __init__(self, cfg):
        _todo("cache.SearchCache.__init__")

    def get(self, key: str):
        _todo("cache.SearchCache.get")

    def put(self, key: str, value) -> None:
        _todo("cache.SearchCache.put")

    def invalidate(self, doc_id: str = None) -> None:
        _todo("cache.SearchCache.invalidate")

    def stats(self) -> dict:
        _todo("cache.SearchCache.stats")

