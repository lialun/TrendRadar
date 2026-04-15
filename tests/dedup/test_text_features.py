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
