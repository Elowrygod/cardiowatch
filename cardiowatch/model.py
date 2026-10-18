"""
Нейросетевой классификатор риска (Лабораторная работа № 3).

Архитектура — простой полносвязный MLP (4 -> 8 -> 1), подобранная и
сверенная в отчёте по ЛР № 3: на тех же 600 синтетических сеансах, что
и логистическая регрессия из ЛР № 1, MLP 4-8-1 даёт ту же точность
(0,908), но чуть выше полноту (recall 0,88 против 0,85) — меньше
пропускает сеансы класса "повышенный риск". Более глубокая сеть
(4-16-8-1) результат не улучшает (переобучение на выборке такого
размера), поэтому выбран самый простой вариант.

Внешний контракт (predict_proba) совпадает с RiskClassifier из
диаграммы классов ЛР № 2 — поэтому замена classического
scikit-learn-классификатора на нейросеть не потребовала менять ничего
вокруг, только сам класс.
"""

from __future__ import annotations
import numpy as np
import torch                      # тензоры и автоматическое дифференцирование
import torch.nn as nn             # слои и функции потерь


class RiskNet(nn.Module):
    """MLP 4 -> 8 -> 1 с ReLU на скрытом слое и сигмоидой на выходе."""

    def __init__(self, n_features: int = 4, n_hidden: int = 8):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, n_hidden),   # входной слой: 4 признака -> 8 нейронов
            nn.ReLU(),                          # нелинейность скрытого слоя
            nn.Linear(n_hidden, 1),             # выходной слой: 8 -> 1 (логит риска)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)                      # возвращает логит (без сигмоиды — для устойчивого BCEWithLogitsLoss)


class RiskClassifier:
    """
    Обёртка вокруг RiskNet со стандартизацией признаков и удобным API,
    совпадающим по форме с scikit-learn (predict / predict_proba), —
    чтобы сервис мог обращаться к нейросети и к классической модели
    из ЛР № 1 одинаково, без привязки к конкретной библиотеке.
    """

    def __init__(self, mean: np.ndarray | None = None, std: np.ndarray | None = None):
        self.model = RiskNet()                              # сама сеть
        self.mean = mean if mean is not None else np.zeros(4)   # среднее для стандартизации признаков
        self.std = std if std is not None else np.ones(4)       # СКО для стандартизации признаков
        self.model.eval()                                    # инференс по умолчанию — без Dropout/BatchNorm (их и нет, но так правильно)

    def _scale(self, X: np.ndarray) -> torch.Tensor:
        Xs = (X - self.mean) / self.std                      # стандартизация теми же параметрами, что при обучении
        return torch.tensor(Xs, dtype=torch.float32)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """X: (n, 4) -> вероятность класса "повышенный риск", (n,)."""
        X = np.atleast_2d(X)
        with torch.no_grad():                                # инференс без накопления градиентов
            logits = self.model(self._scale(X)).squeeze(-1)
            proba = torch.sigmoid(logits)                    # логит -> вероятность
        return proba.numpy()

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X) >= threshold).astype(int)

    def save(self, path: str) -> None:
        torch.save({
            "state_dict": self.model.state_dict(),
            "mean": self.mean,
            "std": self.std,
        }, path)

    @classmethod
    def load(cls, path: str) -> "RiskClassifier":
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        clf = cls(mean=ckpt["mean"], std=ckpt["std"])
        clf.model.load_state_dict(ckpt["state_dict"])
        clf.model.eval()
        return clf
