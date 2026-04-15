# coding=utf-8
"""
通知去重数据模型
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FactSignature:
    numbers: List[str] = field(default_factory=list)
    percentages: List[str] = field(default_factory=list)
    money: List[str] = field(default_factory=list)
    time: List[str] = field(default_factory=list)
    negation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "numbers": self.numbers,
            "percentages": self.percentages,
            "money": self.money,
            "time": self.time,
            "negation": self.negation,
        }


@dataclass
class CandidateNews:
    candidate_id: str
    source_type: str
    platform_id: str
    platform_name: str
    region_type: str
    match_policy: str
    title: str
    url: str = ""
    normalized_title: str = ""
    normalized_url: str = ""
    fact_signature: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoredRecord:
    source_type: str
    platform_id: str
    platform_name: str
    region_type: str
    match_policy: str
    title: str
    normalized_title: str
    url: str
    normalized_url: str
    fact_signature: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
