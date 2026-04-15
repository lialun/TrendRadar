# coding=utf-8
"""
通知去重总控服务
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .embedder import LocalEmbedder
from .filters import flatten_candidates, rebuild_filtered_payload
from .matcher import is_exact_duplicate, is_semantic_duplicate, select_top_k_candidates
from .models import CandidateNews, StoredRecord
from .reranker import LocalReranker
from .store import DedupStore


class DedupService:
    def __init__(
        self,
        base_dir: str,
        config: Dict,
        embedder: Optional[LocalEmbedder] = None,
        reranker: Optional[LocalReranker] = None,
    ):
        self.base_dir = base_dir
        self.config = config
        self.store: Optional[DedupStore] = None
        self.embedder = embedder or LocalEmbedder(config.get("EMBED_MODEL_PATH", ""))
        self.reranker = reranker or LocalReranker(config.get("RERANK_MODEL_PATH", ""))
        self._log_model_availability()

    @classmethod
    def from_components(
        cls,
        base_dir: str,
        config: Dict,
        embedder=None,
        reranker=None,
    ) -> "DedupService":
        return cls(base_dir=base_dir, config=config, embedder=embedder, reranker=reranker)

    def filter_before_send(
        self,
        stats: Optional[List[Dict]],
        new_titles: Optional[Dict],
        rss_items: Optional[List[Dict]],
        rss_new_items: Optional[List[Dict]],
        standalone_data: Optional[Dict],
        now_str: Any,
        id_to_name: Optional[Dict] = None,
    ) -> Dict:
        if not self.config.get("ENABLED", False):
            return {
                "stats": stats or [],
                "new_titles": new_titles or {},
                "rss_items": rss_items,
                "rss_new_items": rss_new_items,
                "standalone_data": standalone_data,
            }

        candidates = flatten_candidates(
            stats=stats,
            new_titles=new_titles,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            standalone_data=standalone_data,
            id_to_name=id_to_name,
        )
        history_records = self._load_recent_records(now_str)
        self._attach_embeddings(candidates)

        accepted_candidates: List[CandidateNews] = []
        accepted_ids = set()

        for candidate in candidates:
            if self._is_duplicate(candidate, accepted_candidates, history_records):
                continue
            accepted_candidates.append(candidate)
            accepted_ids.add(candidate.candidate_id)

        return rebuild_filtered_payload(candidates, accepted_ids)

    def record_after_send(
        self,
        stats: Optional[List[Dict]],
        new_titles: Optional[Dict],
        rss_items: Optional[List[Dict]],
        rss_new_items: Optional[List[Dict]],
        standalone_data: Optional[Dict],
        now_str: Any = None,
        id_to_name: Optional[Dict] = None,
    ) -> int:
        if not self.config.get("ENABLED", False):
            return 0

        self._ensure_store()
        now_value = now_str if now_str is not None else datetime.now()
        now_ts = DedupStore._to_epoch_seconds(now_value)
        expires_ts = now_ts + int(
            timedelta(hours=self.config.get("WINDOW_HOURS", 72)).total_seconds()
        )
        candidates = flatten_candidates(
            stats=stats,
            new_titles=new_titles,
            rss_items=rss_items,
            rss_new_items=rss_new_items,
            standalone_data=standalone_data,
            id_to_name=id_to_name,
        )
        self._attach_embeddings(candidates)

        records = []
        for candidate in candidates:
            records.append(
                {
                    "source_type": candidate.source_type,
                    "platform_id": candidate.platform_id,
                    "platform_name": candidate.platform_name,
                    "region_type": candidate.region_type,
                    "match_policy": candidate.match_policy,
                    "title": candidate.title,
                    "normalized_title": candidate.normalized_title,
                    "url": candidate.url,
                    "normalized_url": candidate.normalized_url,
                    "fact_signature_json": json.dumps(candidate.fact_signature, ensure_ascii=False),
                    "embedding_blob": self._encode_embedding(candidate.embedding),
                    "sent_at": now_ts,
                    "expires_at": expires_ts,
                }
            )

        return self.store.insert_records(records)

    def _is_duplicate(
        self,
        candidate: CandidateNews,
        accepted_candidates: List[CandidateNews],
        history_records: List[StoredRecord],
    ) -> bool:
        for accepted in accepted_candidates:
            require_same_source = (
                candidate.region_type == "standalone"
                and accepted.region_type == "standalone"
            )
            if is_exact_duplicate(candidate.__dict__, accepted.__dict__, require_same_source=require_same_source):
                return True

        for record in history_records:
            require_same_source = candidate.region_type == "standalone"
            if is_exact_duplicate(candidate.__dict__, record.__dict__, require_same_source=require_same_source):
                return True

        if candidate.region_type == "standalone":
            return False

        semantic_candidates = []
        for accepted in accepted_candidates:
            if accepted.region_type == "standalone":
                continue
            semantic_candidates.append(
                {
                    "title": accepted.title,
                    "fact_signature": accepted.fact_signature,
                    "embedding": accepted.embedding,
                }
            )
        for record in history_records:
            if record.region_type == "standalone":
                continue
            semantic_candidates.append(
                {
                    "title": record.title,
                    "fact_signature": record.fact_signature,
                    "embedding": record.embedding,
                }
            )

        if not candidate.embedding or not self.reranker.is_available:
            return False

        recalled = select_top_k_candidates(
            candidate.embedding,
            semantic_candidates,
            top_k=self.config.get("TOP_K", 20),
        )
        pairs = [(candidate.title, item["title"]) for item in recalled]
        scores = self.reranker.score_pairs(pairs)
        for recalled_item, score in zip(recalled, scores):
            if is_semantic_duplicate(
                current={
                    "title": candidate.title,
                    "fact_signature": candidate.fact_signature,
                },
                candidate=recalled_item,
                rerank_score=score,
                rerank_threshold=self.config.get("RERANK_THRESHOLD", 0.82),
                strict_time_conflict=self.config.get("STRICT_TIME_CONFLICT", True),
            ):
                return True

        return False

    def _load_recent_records(self, now_str: str) -> List[StoredRecord]:
        self._ensure_store()
        rows = self.store.fetch_recent_records(now_str, self.config.get("WINDOW_HOURS", 72))
        records: List[StoredRecord] = []
        for row in rows:
            records.append(
                StoredRecord(
                    source_type=row.get("source_type", ""),
                    platform_id=row.get("platform_id", ""),
                    platform_name=row.get("platform_name", ""),
                    region_type=row.get("region_type", ""),
                    match_policy=row.get("match_policy", ""),
                    title=row.get("title", ""),
                    normalized_title=row.get("normalized_title", ""),
                    url=row.get("url", ""),
                    normalized_url=row.get("normalized_url", ""),
                    fact_signature=self._decode_fact_signature(row.get("fact_signature_json", "{}")),
                    embedding=self._decode_embedding(row.get("embedding_blob")),
                )
            )
        return records

    def _attach_embeddings(self, candidates: List[CandidateNews]) -> None:
        if not self.embedder.is_available:
            return
        complex_candidates = [item for item in candidates if item.region_type != "standalone"]
        if not complex_candidates:
            return
        vectors = self.embedder.encode([item.title for item in complex_candidates])
        for item, vector in zip(complex_candidates, vectors):
            item.embedding = vector

    def _ensure_store(self) -> None:
        if self.store is None:
            self.store = DedupStore(self.base_dir)
            self.store.initialize()

    def _log_model_availability(self) -> None:
        if not self.config.get("ENABLED", False):
            return

        if not self.embedder.is_available:
            error = getattr(self.embedder, "load_error", "") or "model unavailable"
            print(f"[Dedup] embedding model unavailable, semantic dedup disabled: {error}")

        if not self.reranker.is_available:
            error = getattr(self.reranker, "load_error", "") or "model unavailable"
            print(f"[Dedup] reranker model unavailable, semantic dedup disabled: {error}")

    @staticmethod
    def _encode_embedding(embedding):
        if not embedding:
            return None
        return json.dumps(embedding).encode("utf-8")

    @staticmethod
    def _decode_embedding(blob):
        if not blob:
            return None
        if isinstance(blob, bytes):
            return json.loads(blob.decode("utf-8"))
        if isinstance(blob, str):
            return json.loads(blob)
        return None

    @staticmethod
    def _decode_fact_signature(raw_value):
        if isinstance(raw_value, str):
            return json.loads(raw_value)
        return {}
