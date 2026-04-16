# coding=utf-8
"""
Realtime websocket dedup adapter.
"""

from __future__ import annotations

from typing import Tuple

from trendradar.dedup.models import CandidateNews
from trendradar.dedup.normalizer import normalize_title, normalize_url
from trendradar.dedup.fact_extractor import extract_fact_signature
from trendradar.websocket.models import RealtimeEvent


class RealtimeDedupAdapter:
    def __init__(self, dedup_service):
        self.dedup_service = dedup_service

    def build_candidate(self, event: RealtimeEvent) -> CandidateNews:
        dedup_text = event.dedup_text
        return CandidateNews(
            candidate_id=f"{event.channel}:{event.source_message_id or event.dedup_key or event.event_type}",
            source_type="websocket",
            platform_id=event.channel,
            platform_name=event.channel,
            region_type="websocket_realtime",
            match_policy="exact_or_semantic",
            title=dedup_text,
            dedup_key=event.dedup_key,
            url=event.detail_url,
            normalized_title=normalize_title(dedup_text),
            normalized_url=normalize_url(event.detail_url),
            fact_signature=extract_fact_signature(dedup_text),
            meta=dict(event.meta),
        )

    def check(self, event: RealtimeEvent, now_str) -> Tuple[CandidateNews, dict | None]:
        candidate = self.build_candidate(event)
        duplicate = self.dedup_service.check_realtime_candidate(candidate, now_str)
        return candidate, duplicate

    def record_sent(self, candidate: CandidateNews, now_str=None) -> int:
        return self.dedup_service.record_realtime_candidate(candidate, now_str)
