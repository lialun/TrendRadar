# coding=utf-8
"""
标题与链接标准化
"""

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from trendradar.utils.url import normalize_url as _normalize_url


PROMO_PREFIXES = (
    "突发",
    "重磅",
    "快讯",
    "最新",
)


def normalize_title(title: str) -> str:
    if not title:
        return ""

    normalized = unicodedata.normalize("NFKC", str(title)).strip().lower()
    normalized = re.sub(r"[【\[].*?[】\]]", " ", normalized)
    prefix_pattern = r"^(?:" + "|".join(re.escape(prefix) for prefix in PROMO_PREFIXES) + r")\s*"
    normalized = re.sub(prefix_pattern, "", normalized)
    normalized = re.sub(r"https?://\S+", " ", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    return normalized


def normalize_url(url: str, platform_id: str = "") -> str:
    if not url:
        return ""
    # trendradar.utils.url.normalize_url already strips common tracking params
    # such as utm_* before returning the normalized URL.
    normalized = _normalize_url(url, platform_id)
    parts = urlsplit(normalized)
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
