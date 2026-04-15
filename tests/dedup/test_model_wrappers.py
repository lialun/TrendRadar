# coding=utf-8

import os
import sys
import tempfile
import types
import unittest

from trendradar.dedup.embedder import LocalEmbedder
from trendradar.dedup.reranker import LocalReranker


class ModelWrapperTest(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("sentence_transformers", None)
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)

    def test_missing_model_path_disables_wrapper(self):
        embedder = LocalEmbedder("/tmp/missing-model")
        reranker = LocalReranker("/tmp/missing-reranker")

        self.assertFalse(embedder.is_available)
        self.assertFalse(reranker.is_available)

    def test_wrapper_retries_without_local_files_only_when_constructor_rejects_kwarg(self):
        module = types.ModuleType("sentence_transformers")
        calls = []

        class FakeSentenceTransformer:
            def __init__(self, model_path, **kwargs):
                calls.append(kwargs)
                if "local_files_only" in kwargs:
                    raise TypeError("unsupported")

            def encode(self, texts, show_progress_bar=False, convert_to_numpy=True):
                class FakeArray:
                    def tolist(self_inner):
                        return [[1.0] for _ in texts]

                return FakeArray()

        class FakeCrossEncoder:
            def __init__(self, model_path, **kwargs):
                calls.append(kwargs)
                if "local_files_only" in kwargs:
                    raise TypeError("unsupported")

            def predict(self, pairs):
                return [0.9 for _ in pairs]

        module.SentenceTransformer = FakeSentenceTransformer
        module.CrossEncoder = FakeCrossEncoder
        sys.modules["sentence_transformers"] = module

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = LocalEmbedder(tmpdir)
            reranker = LocalReranker(tmpdir)

        self.assertTrue(embedder.is_available)
        self.assertTrue(reranker.is_available)
        self.assertEqual("1", os.environ["HF_HUB_OFFLINE"])
        self.assertEqual("1", os.environ["TRANSFORMERS_OFFLINE"])
        self.assertIn({}, calls)
