"""
Блок предварительной обработки данных от датчика (Лабораторная работа № 2, п. 8).

Реализованы три независимых алгоритма сглаживания/фильтрации сигнала:

  1. simple_ema   — классическое экспоненциальное скользящее среднее
                    (формула из методички: EMA = P*alpha + EMAprev*(1-alpha));
  2. adaptive_ema — адаптивная EMA с "памятью и приоритетом новых данных"
                    (Kaufman's Adaptive Moving Average, KAMA);
  3. bandpass_filter — цифровой полосовой фильтр Баттерворта
                    (формула из методички: Yn = SUM Xn-j * Bj, реализована
                     через scipy.signal, что эквивалентно применению
                     набора коэффициентов Bj к скользящему окну отсчётов).
"""

from __future__ import annotations
import numpy as np
from scipy.signal import butter, filtfilt


def simple_ema(x: np.ndarray, alpha: float | None = None, n: int = 10) -> np.ndarray:
    """
    Классическое экспоненциальное скользящее среднее.

    EMA[k] = alpha*x[k] + (1-alpha)*EMA[k-1],  alpha = 2/(N+1)

    alpha и n — единый способ задать сглаживающий фактор: либо alpha
    напрямую, либо число периодов сглаживания N (тогда alpha = 2/(N+1),
    как рекомендовано в методичке).
    """
    if alpha is None:
        alpha = 2.0 / (n + 1)
    out = np.empty_like(x, dtype=np.float64)
    out[0] = x[0]
    for k in range(1, len(x)):
        out[k] = alpha * x[k] + (1 - alpha) * out[k - 1]
    return out


def adaptive_ema(x: np.ndarray, er_window: int = 10,
                  n_fast: int = 2, n_slow: int = 30) -> np.ndarray:
    """
    Адаптивная EMA с "памятью и приоритетом новых данных" (KAMA,
    Kaufman's Adaptive Moving Average).

    Идея: сглаживающий фактор alpha не постоянный, а на каждом шаге
    пересчитывается через "коэффициент эффективности" ER — отношение
    чистого смещения сигнала за последние er_window отсчётов к суммарному
    пройденному сигналом пути:

        ER[k] = |x[k] - x[k-w]| / SUM_{i=k-w+1}^{k} |x[i] - x[i-1]|

    ER близок к 1, если сигнал уверенно и монотонно движется в одну
    сторону (например, начало тахикардии) — тогда alpha приближается к
    "быстрому" alpha_fast, и фильтр быстро следует за новыми данными.
    ER близок к 0, если сигнал колеблется на месте (шум в покое) —
    тогда alpha приближается к "медленному" alpha_slow, и фильтр сильно
    сглаживает, подавляя шум и снижая число ложных тревог.

        alpha_fast = 2/(n_fast+1),  alpha_slow = 2/(n_slow+1)
        SC[k] = (ER[k]*(alpha_fast - alpha_slow) + alpha_slow)^2
        KAMA[k] = KAMA[k-1] + SC[k]*(x[k] - KAMA[k-1])
    """
    n = len(x)
    out = np.empty(n, dtype=np.float64)
    out[0] = x[0]
    a_fast = 2.0 / (n_fast + 1)
    a_slow = 2.0 / (n_slow + 1)

    diff = np.abs(np.diff(x))                      # |x[i]-x[i-1]|
    volatility = np.concatenate(([0.0], diff))      # выровнено по индексу k

    for k in range(1, n):
        w = min(er_window, k)
        change = abs(x[k] - x[k - w])
        vol = np.sum(volatility[k - w + 1:k + 1])
        er = change / vol if vol > 1e-12 else 0.0
        sc = (er * (a_fast - a_slow) + a_slow) ** 2
        out[k] = out[k - 1] + sc * (x[k] - out[k - 1])
    return out


def bandpass_filter(x: np.ndarray, fs: float, low_hz: float = 0.5,
                     high_hz: float = 8.0, order: int = 4) -> np.ndarray:
    """
    Цифровой полосовой фильтр Баттерворта (эквивалент Yn = SUM Xn-j*Bj
    из методички, коэффициенты Bj подбираются автоматически по частотам
    среза, а не задаются вручную).

    Полоса 0,5-8 Гц выбрана так же, как в отчёте по ЛР № 1 (раздел 3.4):
    подавляет дрейф изолинии (дыхание, движение) и высокочастотный шум,
    сохраняя форму пульсовой волны и дикротический изгиб.

    filtfilt применяет фильтр в прямом и обратном направлении, поэтому
    результат не имеет фазового сдвига (важно для точного определения
    моментов пиков на следующем этапе — оценке ЧСС).
    """
    nyq = fs / 2.0
    b, a = butter(order, [low_hz / nyq, high_hz / nyq], btype="band")
    return filtfilt(b, a, x)
