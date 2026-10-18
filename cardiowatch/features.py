"""
Блок извлечения признаков и детекции пиков (Лабораторная работа № 3).

Логика перенесена без изменений из отчёта по ЛР № 1 (раздел 3.4-3.5):
полосовой фильтр -> поиск систолических пиков -> RR-интервалы ->
ЧСС, SDNN, RMSSD, pNN50. Здесь она оформлена как переиспользуемый
модуль, чтобы им пользовались и signal_service.py (потоковая обработка
в контейнере), и train_model.py (генерация обучающей выборки).
"""

from __future__ import annotations
import numpy as np
from scipy.signal import find_peaks

from .preprocessing import bandpass_filter   # тот же фильтр, что и в ЛР № 2

FEATURE_NAMES = ["hr", "sdnn", "rmssd", "pnn50"]  # фиксированный порядок признаков -> вход сети


def detect_peaks(ppg: np.ndarray, fs: float, min_rr_s: float = 0.4,
                  prominence: float = 0.5) -> np.ndarray:
    """Систолические пики на отфильтрованном сигнале (ЛР № 1, раздел 3.4)."""
    xf = bandpass_filter(ppg, fs=fs, low_hz=0.5, high_hz=5.0)   # та же полоса, что и в ЛР № 1
    z = (xf - xf.mean()) / xf.std()                              # нормировка перед поиском пиков
    idx, _ = find_peaks(z, distance=int(min_rr_s * fs), prominence=prominence)
    return idx


def rr_features(peak_idx: np.ndarray, fs: float) -> np.ndarray | None:
    """ЧСС, SDNN, RMSSD, pNN50 по индексам пиков. None, если пиков мало для оценки."""
    if len(peak_idx) < 4:                      # меньше 4 пиков -> меньше 3 RR-интервалов, оценка ненадёжна
        return None
    rr = np.diff(peak_idx) / fs * 1000.0        # RR-интервалы, мс
    hr = 60000.0 / rr.mean()                    # ЧСС, уд/мин
    sdnn = rr.std(ddof=1)                       # общая вариабельность ритма, мс
    d = np.diff(rr)                             # разности соседних RR
    rmssd = np.sqrt(np.mean(d ** 2))            # быстрая составляющая ВСР, мс
    pnn50 = 100.0 * np.mean(np.abs(d) > 50)     # доля "скачков" RR больше 50 мс, %
    return np.array([hr, sdnn, rmssd, pnn50], dtype=np.float64)


def window_features(ppg: np.ndarray, fs: float) -> np.ndarray | None:
    """Признаки по одному окну сырых отсчётов ФПГ (детекция пиков + rr_features)."""
    idx = detect_peaks(ppg, fs)
    return rr_features(idx, fs)
