# coding=utf-8
"""
轻量事实抽取与冲突判断
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Dict

from .models import FactSignature


PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?%")
MONEY_PATTERN = re.compile(r"\d+(?:\.\d+)?(?:元|万元|亿元|美元|万亿美元|人民币)")
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
TIME_PATTERN = re.compile(
    r"(今天|今日|昨日|昨天|本月|本周|今年|去年|\d{4}年(?:\d{1,2}月)?|\d{1,2}月\d{1,2}日|Q[1-4]|q[1-4])",
    re.IGNORECASE,
)
NEGATION_PATTERN = re.compile(r"(未达|未能|未|不及|并非|不是|没有|否认)")


def extract_fact_signature(title: str) -> Dict:
    text = title or ""
    percentages = [_normalize_percentage(match) for match in PERCENT_PATTERN.findall(text)]
    money = [_normalize_money(match) for match in MONEY_PATTERN.findall(text)]
    time_matches = list(TIME_PATTERN.finditer(text))
    time_facts = [_normalize_time(match.group(0)) for match in time_matches]

    numbers = []
    for match in NUMBER_PATTERN.finditer(text):
        if _inside_time_span(match.span(), time_matches):
            continue
        number = match.group(0)
        normalized_number = _normalize_number(number)
        if normalized_number not in numbers and f"{normalized_number}%" not in percentages:
            numbers.append(normalized_number)

    signature = FactSignature(
        numbers=numbers,
        percentages=percentages,
        money=money,
        time=time_facts,
        negation=bool(NEGATION_PATTERN.search(text)),
    )
    return signature.to_dict()


def has_fact_conflict(left: Dict, right: Dict, strict_time_conflict: bool) -> bool:
    if left.get("negation", False) != right.get("negation", False):
        return True

    if _conflicting_values(left.get("percentages", []), right.get("percentages", [])):
        return True

    if _conflicting_values(left.get("money", []), right.get("money", [])):
        return True

    if _conflicting_values(left.get("numbers", []), right.get("numbers", [])):
        return True

    if strict_time_conflict and _conflicting_values(left.get("time", []), right.get("time", [])):
        return True

    return False


def _conflicting_values(left_values, right_values) -> bool:
    left_set = {value for value in left_values if value}
    right_set = {value for value in right_values if value}
    if not left_set or not right_set:
        return False
    return left_set.isdisjoint(right_set)


def _normalize_number(value: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return str(value).strip().lower()
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _normalize_percentage(value: str) -> str:
    raw = str(value).strip()
    return f"{_normalize_number(raw.rstrip('%'))}%"


def _normalize_money(value: str) -> str:
    raw = str(value).strip()
    match = re.match(r"(\d+(?:\.\d+)?)(.*)", raw)
    if not match:
        return raw.lower()
    number_part, unit_part = match.groups()
    return f"{_normalize_number(number_part)}{unit_part.lower()}"


def _normalize_time(value: str) -> str:
    raw = str(value).strip().lower()
    if raw.startswith("q") and len(raw) == 2:
        return raw

    year_month_match = re.match(r"(\d{4})年(\d{1,2})月$", raw)
    if year_month_match:
        year, month = year_month_match.groups()
        return f"{year}年{int(month):02d}月"

    month_day_match = re.match(r"(\d{1,2})月(\d{1,2})日$", raw)
    if month_day_match:
        month, day = month_day_match.groups()
        return f"{int(month):02d}月{int(day):02d}日"

    year_only_match = re.match(r"(\d{4})年$", raw)
    if year_only_match:
        return f"{year_only_match.group(1)}年"

    return raw


def _inside_time_span(span, time_matches) -> bool:
    start, end = span
    for time_match in time_matches:
        time_start, time_end = time_match.span()
        if start >= time_start and end <= time_end:
            return True
    return False
