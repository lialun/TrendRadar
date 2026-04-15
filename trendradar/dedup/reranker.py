# coding=utf-8
"""
本地 reranker 模型包装
"""

import os
from pathlib import Path
from typing import List, Tuple


class LocalReranker:
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
            from sentence_transformers import CrossEncoder

            try:
                self._model = CrossEncoder(self.model_path, local_files_only=True)
            except TypeError:
                self._model = CrossEncoder(self.model_path)
            self.is_available = True
        except Exception as exc:
            self._model = None
            self.is_available = False
            self.load_error = str(exc)
        else:
            self.load_error = ""

    def score_pairs(self, pairs: List[Tuple[str, str]]) -> List[float]:
        if not self.is_available or not pairs:
            return []
        scores = self._model.predict(pairs)
        return [float(score) for score in scores]
