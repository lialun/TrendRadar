# coding=utf-8
"""
本地 embedding 模型包装
"""

import os
from pathlib import Path
from typing import List


class LocalEmbedder:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None
        self.is_available = False
        self.load_error = ""
        self._load_model()

    def _load_model(self) -> None:
        if not self.model_path or not Path(self.model_path).exists():
            return
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        try:
            from sentence_transformers import SentenceTransformer

            try:
                self._model = SentenceTransformer(self.model_path, local_files_only=True)
            except TypeError:
                self._model = SentenceTransformer(self.model_path)
            self.is_available = True
        except Exception as exc:
            self._model = None
            self.is_available = False
            self.load_error = str(exc)
        else:
            self.load_error = ""

    def encode(self, texts: List[str]) -> List[List[float]]:
        if not self.is_available or not texts:
            return []
        vectors = self._model.encode(
            texts,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vectors.tolist()
