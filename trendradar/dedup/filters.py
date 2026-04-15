# coding=utf-8
"""
候选项拍平与回写
"""

from typing import Dict, List, Optional, Set

from .fact_extractor import extract_fact_signature
from .models import CandidateNews
from .normalizer import normalize_title, normalize_url


REGION_PRIORITY = {
    "hotlist": 0,
    "new_items": 1,
    "rss": 2,
    "rss_new_items": 3,
    "standalone": 4,
}


def flatten_candidates(
    stats: Optional[List[Dict]],
    new_titles: Optional[Dict],
    rss_items: Optional[List[Dict]],
    rss_new_items: Optional[List[Dict]],
    standalone_data: Optional[Dict],
    id_to_name: Optional[Dict] = None,
) -> List[CandidateNews]:
    candidates: List[CandidateNews] = []
    reverse_id_to_name = {value: key for key, value in (id_to_name or {}).items()}

    for group_idx, stat in enumerate(stats or []):
        for title_idx, title_data in enumerate(stat.get("titles", [])):
            source_name = title_data.get("source_name", "")
            source_id = title_data.get("source_id") or reverse_id_to_name.get(source_name, source_name)
            title = title_data.get("title", "")
            url = title_data.get("url", "")
            candidates.append(
                _build_candidate(
                    candidate_id=f"hotlist:{group_idx}:{title_idx}",
                    source_type="hotlist",
                    platform_id=source_id,
                    platform_name=source_name or source_id,
                    region_type="hotlist",
                    title=title,
                    url=url,
                    meta={
                        "group_index": group_idx,
                        "group_word": stat.get("word", ""),
                        "group_position": stat.get("position", 999),
                        "group_count": stat.get("count", 0),
                        "title_index": title_idx,
                        "title_payload": dict(title_data),
                    },
                )
            )

    for source_id, titles in (new_titles or {}).items():
        for title_idx, (title, title_data) in enumerate(titles.items()):
            candidates.append(
                _build_candidate(
                    candidate_id=f"new_items:{source_id}:{title_idx}",
                    source_type="hotlist",
                    platform_id=source_id,
                    platform_name=(id_to_name or {}).get(source_id, source_id),
                    region_type="new_items",
                    title=title,
                    url=title_data.get("url", ""),
                    meta={
                        "title_index": title_idx,
                        "title_payload": dict(title_data),
                    },
                )
            )

    _flatten_rss_group_candidates(candidates, rss_items or [], "rss")
    _flatten_rss_group_candidates(candidates, rss_new_items or [], "rss_new_items")

    if standalone_data:
        for platform_idx, platform in enumerate(standalone_data.get("platforms", [])):
            for item_idx, item in enumerate(platform.get("items", [])):
                candidates.append(
                    _build_candidate(
                        candidate_id=f"standalone:platform:{platform_idx}:{item_idx}",
                        source_type="hotlist",
                        platform_id=platform.get("id", ""),
                        platform_name=platform.get("name", ""),
                        region_type="standalone",
                        match_policy="exact",
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        meta={
                            "container_type": "platforms",
                            "group_index": platform_idx,
                            "group_id": platform.get("id", ""),
                            "group_name": platform.get("name", ""),
                            "title_index": item_idx,
                            "title_payload": dict(item),
                        },
                    )
                )

        for feed_idx, feed in enumerate(standalone_data.get("rss_feeds", [])):
            for item_idx, item in enumerate(feed.get("items", [])):
                candidates.append(
                    _build_candidate(
                        candidate_id=f"standalone:rss:{feed_idx}:{item_idx}",
                        source_type="rss",
                        platform_id=feed.get("id", ""),
                        platform_name=feed.get("name", ""),
                        region_type="standalone",
                        match_policy="exact",
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        meta={
                            "container_type": "rss_feeds",
                            "group_index": feed_idx,
                            "group_id": feed.get("id", ""),
                            "group_name": feed.get("name", ""),
                            "title_index": item_idx,
                            "title_payload": dict(item),
                        },
                    )
                )

    return sorted(
        candidates,
        key=lambda item: (
            REGION_PRIORITY.get(item.region_type, 999),
            item.meta.get("group_index", 999),
            item.meta.get("title_index", 999),
        ),
    )


def rebuild_filtered_payload(candidates: List[CandidateNews], accepted_ids: Set[str]) -> Dict:
    stats_groups: Dict[int, Dict] = {}
    new_titles: Dict[str, Dict] = {}
    rss_groups: Dict[int, Dict] = {}
    rss_new_groups: Dict[int, Dict] = {}
    standalone_platform_groups: Dict[int, Dict] = {}
    standalone_rss_groups: Dict[int, Dict] = {}
    saw_standalone = any(item.region_type == "standalone" for item in candidates)

    for candidate in candidates:
        if candidate.candidate_id not in accepted_ids:
            continue

        if candidate.region_type == "hotlist":
            group_index = candidate.meta["group_index"]
            group = stats_groups.setdefault(
                group_index,
                {
                    "word": candidate.meta.get("group_word", ""),
                    "count": 0,
                    "position": candidate.meta.get("group_position", 999),
                    "titles": [],
                },
            )
            group["titles"].append(candidate.meta["title_payload"])
            group["count"] = len(group["titles"])
        elif candidate.region_type == "new_items":
            platform_titles = new_titles.setdefault(candidate.platform_id, {})
            platform_titles[candidate.title] = dict(candidate.meta["title_payload"])
        elif candidate.region_type in {"rss", "rss_new_items"}:
            target_groups = rss_groups if candidate.region_type == "rss" else rss_new_groups
            group_index = candidate.meta["group_index"]
            group = target_groups.setdefault(
                group_index,
                {
                    "word": candidate.meta.get("group_word", ""),
                    "count": 0,
                    "position": candidate.meta.get("group_position", 999),
                    "titles": [],
                },
            )
            group["titles"].append(candidate.meta["title_payload"])
            group["count"] = len(group["titles"])
        elif candidate.region_type == "standalone":
            container_type = candidate.meta.get("container_type")
            target_groups = (
                standalone_platform_groups if container_type == "platforms" else standalone_rss_groups
            )
            group_index = candidate.meta["group_index"]
            group = target_groups.setdefault(
                group_index,
                {
                    "id": candidate.meta.get("group_id", ""),
                    "name": candidate.meta.get("group_name", ""),
                    "items": [],
                },
            )
            group["items"].append(candidate.meta["title_payload"])

    payload = {
        "stats": [stats_groups[idx] for idx in sorted(stats_groups.keys())],
        "new_titles": new_titles,
        "rss_items": [rss_groups[idx] for idx in sorted(rss_groups.keys())] or None,
        "rss_new_items": [rss_new_groups[idx] for idx in sorted(rss_new_groups.keys())] or None,
    }
    payload["standalone_data"] = None
    if saw_standalone:
        payload["standalone_data"] = {
            "platforms": [
                standalone_platform_groups[idx]
                for idx in sorted(standalone_platform_groups.keys())
                if standalone_platform_groups[idx]["items"]
            ],
            "rss_feeds": [
                standalone_rss_groups[idx]
                for idx in sorted(standalone_rss_groups.keys())
                if standalone_rss_groups[idx]["items"]
            ],
        }
    return payload


def _flatten_rss_group_candidates(candidates: List[CandidateNews], groups: List[Dict], region_type: str) -> None:
    for group_idx, stat in enumerate(groups):
        for title_idx, title_data in enumerate(stat.get("titles", [])):
            source_name = title_data.get("source_name", "")
            source_id = title_data.get("feed_id", source_name)
            title = title_data.get("title", "")
            candidates.append(
                _build_candidate(
                    candidate_id=f"{region_type}:{group_idx}:{title_idx}",
                    source_type="rss",
                    platform_id=source_id,
                    platform_name=source_name or source_id,
                    region_type=region_type,
                    title=title,
                    url=title_data.get("url", ""),
                    meta={
                        "group_index": group_idx,
                        "group_word": stat.get("word", ""),
                        "group_position": stat.get("position", 999),
                        "group_count": stat.get("count", 0),
                        "title_index": title_idx,
                        "title_payload": dict(title_data),
                    },
                )
            )


def _build_candidate(
    candidate_id: str,
    source_type: str,
    platform_id: str,
    platform_name: str,
    region_type: str,
    title: str,
    url: str,
    meta: Dict,
    match_policy: str = "semantic",
) -> CandidateNews:
    return CandidateNews(
        candidate_id=candidate_id,
        source_type=source_type,
        platform_id=platform_id,
        platform_name=platform_name,
        region_type=region_type,
        match_policy=match_policy,
        title=title,
        url=url,
        normalized_title=normalize_title(title),
        normalized_url=normalize_url(url, platform_id),
        fact_signature=extract_fact_signature(title),
        meta=meta,
    )
