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
            print("[Dedup][skip] 通知去重未启用，直接保留原始内容")
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
        input_counts = self._count_candidates(candidates)
        filtered_counts = {
            "exact": 0,
            "semantic": 0,
            "standalone_same_source": 0,
            "standalone_seen_in_complex": 0,
        }
        self._log_filter_start(input_counts, len(history_records))

        accepted_candidates: List[CandidateNews] = []
        accepted_ids = set()

        for candidate in candidates:
            duplicate_info = self._check_duplicate(candidate, accepted_candidates, history_records)
            if duplicate_info:
                reason = duplicate_info["reason"]
                filtered_counts[reason] = filtered_counts.get(reason, 0) + 1
                self._log_debug_duplicate(candidate, duplicate_info)
                continue
            accepted_candidates.append(candidate)
            accepted_ids.add(candidate.candidate_id)

        result = rebuild_filtered_payload(candidates, accepted_ids)
        remaining_counts = self._count_remaining_payload(result)
        self._log_filter_end(filtered_counts, remaining_counts)
        return result

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

        inserted = self.store.insert_records(records)
        hotlist_count = sum(1 for c in candidates if c.region_type == 'hotlist')
        new_items_count = sum(1 for c in candidates if c.region_type == 'new_items')
        rss_count = sum(1 for c in candidates if c.region_type == 'rss')
        rss_new_items_count = sum(1 for c in candidates if c.region_type == 'rss_new_items')
        standalone_count = sum(1 for c in candidates if c.region_type == 'standalone')
        window_hours = self.config.get("WINDOW_HOURS", 72)

        print(f"[Dedup][store] 已记录 {inserted} 条已发送内容，用于后续 {window_hours} 小时去重")
        if inserted > 0:
            print(f"  - 热榜：{hotlist_count} 条")
            print(f"  - 新增：{new_items_count} 条")
            print(f"  - RSS：{rss_count} 条")
            print(f"  - RSS 新增：{rss_new_items_count} 条")
            print(f"  - 独立展示区：{standalone_count} 条")
        return inserted

    def _check_duplicate(
        self,
        candidate: CandidateNews,
        accepted_candidates: List[CandidateNews],
        history_records: List[StoredRecord],
    ) -> Optional[Dict[str, Any]]:
        for accepted in accepted_candidates:
            require_same_source = (
                candidate.region_type == "standalone"
                and accepted.region_type == "standalone"
            )
            if is_exact_duplicate(candidate.__dict__, accepted.__dict__, require_same_source=require_same_source):
                if candidate.region_type == "standalone" and accepted.region_type == "standalone":
                    reason = "standalone_same_source"
                elif candidate.region_type == "standalone":
                    reason = "standalone_seen_in_complex"
                else:
                    reason = "exact"
                return {
                    "reason": reason,
                    "scope": "accepted",
                    "matched_title": accepted.title,
                    "matched_region": accepted.region_type,
                }

        for record in history_records:
            require_same_source = candidate.region_type == "standalone"
            if is_exact_duplicate(candidate.__dict__, record.__dict__, require_same_source=require_same_source):
                reason = "standalone_same_source" if candidate.region_type == "standalone" else "exact"
                return {
                    "reason": reason,
                    "scope": "history",
                    "matched_title": record.title,
                    "matched_region": record.region_type,
                }

        if candidate.region_type == "standalone":
            return None

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
                rerank_threshold=self.config.get("RERANK_THRESHOLD", 0.95),
                strict_time_conflict=self.config.get("STRICT_TIME_CONFLICT", True),
            ):
                return {
                    "reason": "semantic",
                    "scope": "semantic",
                    "matched_title": recalled_item.get("title", ""),
                    "score": round(score, 4),
                }

        return None

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

        window_hours = self.config.get('WINDOW_HOURS', 72)
        top_k = self.config.get('TOP_K', 20)
        rerank_threshold = self.config.get('RERANK_THRESHOLD', 0.98)
        strict_time = "是" if self.config.get('STRICT_TIME_CONFLICT', True) else "否"
        debug = "是" if self.config.get('DEBUG', False) else "否"

        print(f"[Dedup][init] 已启用通知去重")
        print(f"  - 时间窗口：{window_hours} 小时（在此时间内的内容会被检查重复）")
        print(f"  - 语义相似度阈值：{rerank_threshold}（越高越严格，越不容易判为重复）")
        print(f"  - 召回候选数：{top_k} 条（从历史中选出最相似的 {top_k} 条进行精确比对）")
        print(f"  - 严格时间冲突检查：{strict_time}")
        print(f"  - 调试日志：{debug}")

        if not self.embedder.is_available:
            error = getattr(self.embedder, "load_error", "") or "模型不可用"
            print(f"[Dedup][init] ⚠️  语义去重不可用：embedding 模型加载失败（{error}）")
            print(f"[Dedup][init] 当前仅使用精确去重（标题/URL 完全相同才判为重复）")

        if not self.reranker.is_available:
            error = getattr(self.reranker, "load_error", "") or "模型不可用"
            print(f"[Dedup][init] ⚠️  语义去重不可用：reranker 模型加载失败（{error}）")
            print(f"[Dedup][init] 当前仅使用精确去重（标题/URL 完全相同才判为重复）")

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

    def _log_filter_start(self, input_counts: Dict[str, int], history_count: int) -> None:
        print(f"[Dedup][scan] 本轮待检查 {input_counts['total']} 条内容")
        print(f"  - 热榜：{input_counts['hotlist']} 条")
        print(f"  - 新增：{input_counts['new_items']} 条")
        print(f"  - RSS：{input_counts['rss']} 条")
        print(f"  - RSS 新增：{input_counts['rss_new_items']} 条")
        print(f"  - 独立展示区：{input_counts['standalone']} 条")
        print(f"  - 历史记录：{history_count} 条")

    def _log_filter_end(self, filtered_counts: Dict[str, int], remaining_counts: Dict[str, int]) -> None:
        total_filtered = sum(filtered_counts.values())
        print(f"[Dedup][result] 本轮共过滤 {total_filtered} 条重复内容")
        if total_filtered > 0:
            print(f"  - 精确重复（标题/URL 完全相同）：{filtered_counts['exact']} 条")
            print(f"  - 语义重复（内容相似）：{filtered_counts['semantic']} 条")
            print(f"  - 独立区同源重复：{filtered_counts['standalone_same_source']} 条")
            print(f"  - 独立区与主区域重复：{filtered_counts['standalone_seen_in_complex']} 条")

        print(f"[Dedup][result] 本轮保留 {remaining_counts['total']} 条内容")
        if remaining_counts['total'] > 0:
            print(f"  - 热榜：{remaining_counts['hotlist']} 条")
            print(f"  - 新增：{remaining_counts['new_items']} 条")
            print(f"  - RSS：{remaining_counts['rss']} 条")
            print(f"  - RSS 新增：{remaining_counts['rss_new_items']} 条")
            print(f"  - 独立展示区：{remaining_counts['standalone']} 条")

    def _log_debug_duplicate(self, candidate: CandidateNews, duplicate_info: Dict[str, Any]) -> None:
        if not self.config.get("DEBUG", False):
            return

        # 区域类型映射
        region_map = {
            "hotlist": "热榜",
            "new_items": "新增",
            "rss": "RSS",
            "rss_new_items": "RSS新增",
            "standalone": "独立展示区"
        }
        region_name = region_map.get(candidate.region_type, candidate.region_type)

        # 原因映射
        reason_map = {
            "exact": "精确重复",
            "semantic": "语义重复",
            "standalone_same_source": "独立区同源重复",
            "standalone_seen_in_complex": "独立区与主区域重复"
        }
        reason_name = reason_map.get(duplicate_info['reason'], duplicate_info['reason'])

        # 构建日志
        print(f"[Dedup][debug] 已过滤 [{region_name}] {candidate.platform_id}")
        print(f"  标题：{candidate.title}")
        print(f"  原因：{reason_name}")
        print(f"  匹配：{duplicate_info.get('matched_title', '')}")
        if "score" in duplicate_info:
            print(f"  相似度：{duplicate_info['score']}")

    @staticmethod
    def _count_candidates(candidates: List[CandidateNews]) -> Dict[str, int]:
        counts = {
            "hotlist": 0,
            "new_items": 0,
            "rss": 0,
            "rss_new_items": 0,
            "standalone": 0,
            "total": len(candidates),
        }
        for candidate in candidates:
            counts[candidate.region_type] = counts.get(candidate.region_type, 0) + 1
        return counts

    @staticmethod
    def _count_remaining_payload(payload: Dict[str, Any]) -> Dict[str, int]:
        hotlist = sum(len(stat.get("titles", [])) for stat in payload.get("stats", []))
        new_items = sum(len(titles) for titles in payload.get("new_titles", {}).values())
        rss = sum(len(stat.get("titles", [])) for stat in (payload.get("rss_items") or []))
        rss_new_items = sum(len(stat.get("titles", [])) for stat in (payload.get("rss_new_items") or []))
        standalone = 0
        standalone_data = payload.get("standalone_data") or {}
        for platform in standalone_data.get("platforms", []):
            standalone += len(platform.get("items", []))
        for feed in standalone_data.get("rss_feeds", []):
            standalone += len(feed.get("items", []))
        return {
            "hotlist": hotlist,
            "new_items": new_items,
            "rss": rss,
            "rss_new_items": rss_new_items,
            "standalone": standalone,
            "total": hotlist + new_items + rss + rss_new_items + standalone,
        }
