"""
Обучение нейросетевого классификатора риска (Лабораторная работа № 3).

Запускается один раз при сборке Docker-образа (см. Dockerfile): генерирует
тот же синтетический датасет из 600 сеансов, что и в ЛР № 1 (300 "норма" +
300 "повышенный риск", seed=42 — для воспроизводимости), извлекает признаки
ЧСС/SDNN/RMSSD/pNN50 через cardiowatch.features, обучает RiskNet (см.
cardiowatch/model.py) и сохраняет веса в model.pt, который затем копируется
в образ и загружается signal_service при старте контейнера.

Запуск вручную (для проверки):
    python3 train_model.py
"""

from __future__ import annotations
import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

from cardiowatch.signal_source import SyntheticPpgSource
from cardiowatch.features import window_features
from cardiowatch.model import RiskNet, RiskClassifier


def make_dataset(n_per_class: int = 300, seed: int = 42):
    """Та же процедура генерации, что и в отчёте по ЛР № 1, раздел 3.3."""
    rng = np.random.default_rng(seed)                     # один генератор на весь датасет -> воспроизводимость
    X, y = [], []
    for cls in (0, 1):                                    # 0 - норма, 1 - повышенный риск
        for _ in range(n_per_class):
            if cls == 0:
                hr = rng.normal(70, 7)
                sdnn = max(15.0, rng.normal(55, 15))
            else:
                hr = rng.normal(85, 8)
                sdnn = max(8.0, rng.normal(30, 12))
            hr = float(np.clip(hr, 45, 120))               # физиологические границы ЧСС
            src = SyntheticPpgSource(fs=100.0, heart_rate_bpm=hr,
                                      seed=int(rng.integers(0, 2**31 - 1)))
            src.params.hrv_std = sdnn / 1000.0 / 2.5        # перевод целевого SDNN в параметр модели (эмпирический коэффициент, см. отчёт ЛР №1)
            chunk = src.read_chunk(60.0)                     # 60-секундный сеанс, как в ЛР № 1
            feat = window_features(chunk.ppg, chunk.fs)
            if feat is None:                                 # сеанс, где пиков нашлось слишком мало — пропускаем
                continue
            X.append(feat)
            y.append(cls)
    return np.array(X), np.array(y)


def train(X: np.ndarray, y: np.ndarray, epochs: int = 300, lr: float = 0.01, seed: int = 42):
    torch.manual_seed(seed)                                  # воспроизводимость инициализации весов
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)

    mean, std = Xtr.mean(axis=0), Xtr.std(axis=0)            # параметры стандартизации считаем только по обучающей части
    Xtr_s = (Xtr - mean) / std
    Xte_s = (Xte - mean) / std

    ds = TensorDataset(torch.tensor(Xtr_s, dtype=torch.float32),
                        torch.tensor(ytr, dtype=torch.float32))
    dl = DataLoader(ds, batch_size=32, shuffle=True)          # мини-батчи по 32 сеанса

    net = RiskNet()
    opt = torch.optim.Adam(net.parameters(), lr=lr)           # Adam — устойчивый выбор по умолчанию для небольших MLP
    loss_fn = torch.nn.BCEWithLogitsLoss()                    # логистическая функция потерь прямо по логитам (устойчивее, чем Sigmoid+BCE раздельно)

    net.train()
    for epoch in range(epochs):
        for xb, yb in dl:
            opt.zero_grad()                                   # обнуляем градиенты перед новым шагом
            logits = net(xb).squeeze(-1)
            loss = loss_fn(logits, yb)
            loss.backward()                                   # обратное распространение ошибки
            opt.step()                                        # шаг градиентного спуска

    net.eval()
    clf = RiskClassifier(mean=mean, std=std)
    clf.model.load_state_dict(net.state_dict())

    proba = clf.predict_proba(Xte)
    pred = (proba >= 0.5).astype(int)
    metrics = dict(
        acc=accuracy_score(yte, pred), prec=precision_score(yte, pred),
        rec=recall_score(yte, pred), f1=f1_score(yte, pred), auc=roc_auc_score(yte, proba),
    )
    return clf, metrics


if __name__ == "__main__":
    print("Генерация обучающей выборки (600 сеансов, как в ЛР № 1)...")
    X, y = make_dataset()
    print(f"Готово: {X.shape[0]} сеансов, {X.shape[1]} признака(ов).")

    print("Обучение RiskNet (MLP 4-8-1)...")
    clf, metrics = train(X, y)
    print("Метрики на отложенной выборке (20%):")
    for k, v in metrics.items():
        print(f"  {k}: {v:.3f}")

    clf.save("model.pt")
    print("Модель сохранена в model.pt")
