# -*- coding: utf-8 -*-
"""Фасад модуля для Kod.py (этап 8, R6) — публичный API §6.1 мастер-плана.

RagService — единственная точка входа для ядра агента: Kod.py/Agent работают
только с этим классом и не лезут в index/retrieval/embedding напрямую.

Границы (мастер-план §5):
  * rag/ НЕ импортирует core/ — форматирование блока живёт здесь, в rag/;
  * индекс и эмбеддер грузятся ЛЕНИВО (первый поиск/индексация), чтобы `--rag`
    без прогона не платил за загрузку;
  * любая ошибка RAG — деградация (пустая выдача), а не падение ответа агента.
"""
from __future__ import annotations

from rag.config import RagConfig
from rag.types import IngestReport


class RagService:
    """Фасад: ingest / search / context_block / stats / compare / evaluate / ground."""

    def __init__(self, cfg: RagConfig = None, log=None):
        self.cfg = (cfg or RagConfig.default()).validate()
        self.log = log or (lambda line: None)
        self._index = None
        self._embedder = None
        self._retriever = None
        self._loaded = False

    # ---------- ленивая загрузка ----------
    def _ensure_index(self):
        """Загрузить индекс с диска (один раз). Пустой/битый → пустой индекс."""
        if self._loaded:
            return self._index
        from rag.index import RagIndex
        self._index = RagIndex.load(self.cfg.index_dir, self.cfg)
        self._loaded = True
        return self._index

    def _ensure_embedder(self):
        if self._embedder is None:
            from rag.embedding import make_embedder
            self._embedder = make_embedder(self.cfg.embedding, log=self.log)
        return self._embedder

    def _ensure_retriever(self):
        if self._retriever is None:
            from rag.retrieval import Retriever
            index = self._ensure_index()
            # Эмбеддер нужен только dense/hybrid; для bm25 не поднимаем Ollama.
            embedder = (self._ensure_embedder()
                        if self.cfg.retrieval.mode in ("dense", "hybrid") else None)
            self._retriever = Retriever(index, self.cfg, embedder)
        return self._retriever

    @property
    def index(self):
        return self._ensure_index()

    # ---------- индексация ----------
    def ingest(self, paths=None) -> IngestReport:
        """Проиндексировать пути (дельтой) и сохранить индекс. paths=None → corpus.list."""
        from rag import corpus as corpus_mod
        from rag.index import RagIndex
        index = self._ensure_index()
        embedder = self._ensure_embedder()
        docs = corpus_mod.discover(paths, self.cfg)
        if index.needs_rebuild(self.cfg, embedder):
            # Расхождение версий/параметров — полный ребилд (инкрементация невалидна).
            index.meta = {}
        report = index.ingest(docs, self.cfg, embedder)
        index.save(self.cfg.index_dir)
        self._retriever = None          # сбросить ретривер: индекс изменился
        self.log(f"[RAG] ingest: +{report.added} ~{report.updated} "
                 f"-{report.removed} ={report.skipped}, чанков {report.chunks} "
                 f"за {report.seconds}s")
        return report

    # ---------- поиск ----------
    def search(self, query: str, k: int = None, mode: str = None,
               filters=None) -> list:
        """Топ-k чанков по запросу. Пустой индекс/ошибка → [] (деградация)."""
        if not query or not query.strip():
            return []
        k = k or self.cfg.retrieval.final_k
        try:
            retriever = self._ensure_retriever()
            return retriever.search(query, k=k, mode=mode, filters=filters)
        except Exception as error:            # RAG не роняет ответ агента
            self.log(f"[RAG] поиск не удался ({type(error).__name__}: {error}) — блок опущен")
            return []

    # ---------- блок промпта ----------
    def context_block(self, query: str = "", k: int = None, budget: int = None,
                      hits: list = None, mode: str = None) -> str:
        """Готовый текст блока [rag] (нумерованные источники + инструкция).

        `hits` передаются извне, чтобы на один запрос был ОДИН поиск (агент уже
        нашёл чанки и кладёт их в last_rag_hits). Иначе — ищем по `query`.
        """
        if hits is None:
            hits = self.search(query, k=k, mode=mode)
        if not hits:
            return ""
        budget = budget or self.cfg.budget.max_rag_tokens
        return _render_block(hits, budget)

    # ---------- статистика ----------
    def stats(self) -> dict:
        """Состояние индекса/модели/эмбеддера (для /rag stats)."""
        index = self._ensure_index()
        data = index.stats()
        data.update({
            "index_dir": self.cfg.index_dir,
            "strategy": self.cfg.chunking.strategy,
            "mode": self.cfg.retrieval.mode,
            "embedding_provider": self.cfg.embedding.provider,
            "ollama_url": self.cfg.embedding.url,
            "ollama_ready": _ollama_ready(self.cfg.embedding.url),
        })
        return data

    # ---------- метрики и сравнение (тонкие обёртки) ----------
    def evaluate(self, dataset: str = "rag/datasets/queries.jsonl", k: int = 5,
                 mode: str = None):
        from rag.eval import evaluate
        index = self._ensure_index()
        retriever = self._ensure_retriever()
        return evaluate(index, dataset, k=k, retriever=retriever,
                        mode=mode or self.cfg.retrieval.mode)

    def compare(self, strategies=("fixed", "structural"),
                modes=("bm25", "dense", "hybrid"),
                queries: str = "rag/datasets/queries.jsonl", k: int = 5):
        from rag.compare import compare
        return compare(self.cfg, list(strategies), list(modes), queries, k=k)

    # ---------- grounding (этап 9) ----------
    def ground(self, answer: str, hits: list = None, mode: str = None):
        raise NotImplementedError(
            "rag: RagService.ground ещё не реализован (этап 9 плана dev/migr_plan.md)")


# ---------------------------------------------------------------------------
# Форматирование блока [rag] живёт в rag/ (граница: rag/ не импортирует core/).
# Формат совпадает с core.prompt_builder.render_rag — единый вид блока в промте.
# ---------------------------------------------------------------------------
_BLOCK_INSTRUCTIONS = (
    "Инструкции:\n"
    "1. Отвечай по возможности по этим источникам; каждое утверждение помечай "
    "ссылкой вида [doc_id#chunk_id] из списка выше.\n"
    "2. Если в источниках ответа нет — прямо скажи об этом, не выдумывай.\n"
    "3. Источники могут противоречить друг другу — укажи это."
)


def _render_block(hits, budget: int = 1400, max_chars: int = 700) -> str:
    header = "Найденные источники (используй их и ставь ссылки на них):"
    lines = [header]
    used = max(1, len(header) // 4)
    placed = 0
    for num, hit in enumerate(hits, 1):
        ref = f"[{getattr(hit, 'doc_id', '')}#{getattr(hit, 'chunk_id', '')}]"
        where = getattr(hit, "source", "") or ""
        section = getattr(hit, "section", "") or ""
        title = getattr(hit, "title", "") or ""
        fragment = " ".join((getattr(hit, "text", "") or "").split())[:max_chars]
        entry = (f"{num}. {ref} {where}" + (f" · {title}" if title else "")
                 + (f" · раздел: {section}" if section else "")
                 + "\n    " + fragment)
        cost = max(1, len(entry) // 4)
        if used + cost > budget:
            continue
        lines.append(entry)
        used += cost
        placed += 1
    if not placed:
        return ""
    lines.append("")
    lines.append(_BLOCK_INSTRUCTIONS)
    return "\n".join(lines)


def _ollama_ready(url: str) -> bool:
    """Доступен ли локальный Ollama (для /rag stats; не поднимает сервис)."""
    import json
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=2) as resp:
            json.load(resp)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False