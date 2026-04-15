# coding=utf-8

import os
import unittest

from trendradar.dedup.config import load_dedup_config


class DedupConfigTest(unittest.TestCase):
    def tearDown(self) -> None:
        for key in (
            "DEDUP_ENABLED",
            "DEDUP_WINDOW_HOURS",
            "DEDUP_TOP_K",
            "DEDUP_RERANK_THRESHOLD",
            "DEDUP_STRICT_TIME_CONFLICT",
            "DEDUP_EMBED_MODEL_PATH",
            "DEDUP_RERANK_MODEL_PATH",
        ):
            os.environ.pop(key, None)

    def test_env_overrides_and_defaults(self):
        os.environ["DEDUP_ENABLED"] = "true"
        os.environ["DEDUP_WINDOW_HOURS"] = "72"
        os.environ["DEDUP_EMBED_MODEL_PATH"] = "/models/dedup-embed"
        os.environ["DEDUP_RERANK_MODEL_PATH"] = "/models/dedup-rerank"

        cfg = load_dedup_config({"notification": {"dedup": {}}})

        self.assertTrue(cfg["ENABLED"])
        self.assertEqual(cfg["WINDOW_HOURS"], 72)
        self.assertEqual(cfg["TOP_K"], 20)
        self.assertEqual(cfg["RERANK_THRESHOLD"], 0.82)
        self.assertTrue(cfg["STRICT_TIME_CONFLICT"])
        self.assertEqual(cfg["EMBED_MODEL_PATH"], "/models/dedup-embed")
        self.assertEqual(cfg["RERANK_MODEL_PATH"], "/models/dedup-rerank")
