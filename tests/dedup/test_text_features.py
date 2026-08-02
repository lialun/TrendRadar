# coding=utf-8

import unittest

from trendradar.dedup.fact_extractor import extract_fact_signature, has_fact_conflict
from trendradar.dedup.normalizer import normalize_title, normalize_url


class TextFeatureTest(unittest.TestCase):
    def test_title_normalization(self):
        self.assertEqual(
            "apple发布新款iphone18",
            normalize_title("【突发】Apple 发布新款 iPhone 18！"),
        )

    def test_fact_conflict_blocks_cpi_update(self):
        left = extract_fact_signature("法国本月CPI为2%")
        right = extract_fact_signature("法国今天CPI为3%")
        self.assertTrue(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_fact_normalization_treats_equivalent_values_as_equal(self):
        left = extract_fact_signature("法国2026年4月CPI为2.0%")
        right = extract_fact_signature("法国2026年04月CPI为2%")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_time_numbers_do_not_become_general_number_conflicts(self):
        left = extract_fact_signature("法国2026年4月CPI公布")
        right = extract_fact_signature("法国2025年4月CPI公布")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=False))

    def test_url_normalization(self):
        self.assertEqual(
            "https://example.com/path?id=1",
            normalize_url("https://Example.com/path/?id=1#fragment"),
        )
        self.assertEqual(
            "https://example.com/path?id=1",
            normalize_url("https://example.com/path/?id=1&utm_source=x#fragment"),
        )

    def test_negation_conflict(self):
        left = extract_fact_signature("法国CPI未达2%")
        right = extract_fact_signature("法国CPI为2%")
        self.assertTrue(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_non_negation_phrase_does_not_trigger_conflict(self):
        left = extract_fact_signature("市场不久后将公布数据")
        right = extract_fact_signature("市场将公布数据")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_city_name_with_wu_does_not_trigger_negation(self):
        left = extract_fact_signature("无锡发布新政策")
        right = extract_fact_signature("无锡发布新政策解读")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_new_number_in_current_counts_as_new_development(self):
        """current has a specific number the historical record lacks → new development → conflict.

        This prevents a follow-up story (e.g. "8 tankers diverted") from being silently
        deduped against a vague earlier report (e.g. "Houthis announce blockade") that
        never mentioned a concrete number.
        """
        left = extract_fact_signature("已有8艘沙特油轮被迫改变航线绕行好望角")
        right = extract_fact_signature("胡塞武装宣布对沙特实施海上封锁")
        self.assertTrue(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_historical_more_specific_than_current_is_not_conflict(self):
        """historical record is more specific than current article → no conflict.

        If the current article is a vague summary of something the historical record
        covered in detail, we do not declare a conflict – the current may legitimately
        be a brief re-mention of the same event.
        """
        left = extract_fact_signature("胡塞武装宣布对沙特实施海上封锁")
        right = extract_fact_signature("已有8艘沙特油轮被迫改变航线绕行好望角")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=True))

    def test_same_numbers_in_both_is_not_conflict(self):
        """Both sides mention the same number → consistent, no conflict."""
        left = extract_fact_signature("8艘沙特油轮改变航线")
        right = extract_fact_signature("沙特8艘油轮绕行好望角")
        self.assertFalse(has_fact_conflict(left, right, strict_time_conflict=True))
