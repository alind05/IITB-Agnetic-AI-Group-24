import re
from typing import Literal, Optional
from rank_bm25 import BM25Okapi
from .schemas import FilingPassage

SYNONYM_CLUSTERS: list[set[str]] = [
    {"operating", "margin", "profitability", "leverage", "income", "opex", "depreciation"},
    {"cloud", "azure", "gcp", "aws", "datacenter", "infrastructure", "capex", "compute"},
    {"ai", "artificial", "intelligence", "generative", "gpu", "tpu", "model", "inference"},
    {"risk", "antitrust", "doj", "regulation", "dma", "export", "litigation", "remedies"},
    {"cybersecurity", "security", "threat", "identity", "breach"},
    {"revenue", "growth", "monetization", "pricing", "arpu", "demand"},
]


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", text.lower())
    return [w for w in cleaned.split() if len(w) > 2]


def _expand_terms(tokens: list[str]) -> set[str]:
    expanded = set(tokens)
    for tok in tokens:
        for cluster in SYNONYM_CLUSTERS:
            if tok in cluster:
                expanded |= cluster
    return expanded


def hybrid_search_and_rerank(
    passages: list[FilingPassage],
    query: str,
    section_filter: Optional[Literal["Item 1A", "Item 7"]] = None,
    top_k: int = 5,
) -> list[FilingPassage]:
    pool = [p for p in passages if not section_filter or p.section == section_filter]
    if not pool:
        return []

    query_tokens = _tokenize(query)
    expanded_terms = _expand_terms(query_tokens)
    corpus_tokens = [_tokenize(f"{p.title} {p.text}") for p in pool]

    # 1. Lexical BM25 via rank_bm25
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = bm25.get_scores(query_tokens) if query_tokens else [0.0] * len(pool)

    # 2. Financial Concept Overlap + Recency Reranker
    semantic_scores: list[float] = []
    for idx, p in enumerate(pool):
        doc_set = set(corpus_tokens[idx])
        title_set = set(_tokenize(p.title))
        overlap = sum(
            (1.0 if term in doc_set else 0.0) + (1.5 if term in title_set else 0.0)
            for term in expanded_terms
        )
        recency = 1.2 if p.fiscalYear >= 2025 else (0.6 if p.fiscalYear >= 2024 else 0.0)
        semantic_scores.append(overlap / max(4, len(expanded_terms)) + recency)

    # 3. Reciprocal Rank Fusion (RRF)
    bm25_rank = sorted(range(len(pool)), key=lambda i: bm25_scores[i], reverse=True)
    sem_rank = sorted(range(len(pool)), key=lambda i: semantic_scores[i], reverse=True)

    rrf = [0.0] * len(pool)
    k = 10
    for rank, idx in enumerate(bm25_rank):
        rrf[idx] += 1.0 / (k + rank + 1)
    for rank, idx in enumerate(sem_rank):
        rrf[idx] += 1.0 / (k + rank + 1)

    ranked = sorted(
        [
            p.model_copy(update={"score": round(rrf[i] * 10, 3)})
            for i, p in enumerate(pool)
        ],
        key=lambda x: x.score or 0.0,
        reverse=True,
    )
    return ranked[:top_k]
