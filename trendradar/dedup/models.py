# coding=utf-8
"""
通知去重数据模型
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


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
