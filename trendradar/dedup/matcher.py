# coding=utf-8
"""
去重判定器
"""

from math import sqrt
from typing import Any, Dict, Iterable, List

from .fact_extractor import has_fact_conflict


def is_exact_duplicate(
    left: Dict[str, Any],
    right: Dict[str, Any],
    require_same_source: bool = False,
) -> bool:
    if require_same_source and not _same_source(left, right):
        return False

    left_url = left.get("normalized_url", "")
    right_url = right.get("normalized_url", "")
    if left_url and right_url and left_url == right_url:
        return True

    left_title = left.get("normalized_title", "")
    right_title = right.get("normalized_title", "")
    return bool(left_title and right_title and left_title == right_title)


def is_standalone_duplicate(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return is_exact_duplicate(left, right, require_same_source=True)


def is_semantic_duplicate(
    current: Dict[str, Any],
    candidate: Dict[str, Any],
    rerank_score: float,
    rerank_threshold: float,
    strict_time_conflict: bool,
) -> bool:
    if rerank_score < rerank_threshold:
        return False
    return not has_fact_conflict(
        current.get("fact_signature", {}),
        candidate.get("fact_signature", {}),
        strict_time_conflict=strict_time_conflict,
    )


def select_top_k_candidates(
    current_embedding: List[float],
    candidate_records: Iterable[Dict[str, Any]],
    top_k: int,
) -> List[Dict[str, Any]]:
    ranked = []
    for record in candidate_records:
        embedding = record.get("embedding")
        if not embedding:
            continue
        similarity = _cosine_similarity(current_embedding, embedding)
        enriched = dict(record)
        enriched["_similarity"] = similarity
        ranked.append(enriched)

    ranked.sort(key=lambda item: item["_similarity"], reverse=True)
    return ranked[:top_k]


def _same_source(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return (
        left.get("source_type", "") == right.get("source_type", "")
        and left.get("platform_id", "") == right.get("platform_id", "")
    )


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
