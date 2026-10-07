"""
Буфер принятого сигнала и блок дискретизации/синхронизации выборки
(Лабораторная работа № 2, п. 6-7).
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import numpy as np
from scipy.signal import resample_poly


class RingBuffer:
    """
    Простой накопительный буфер отсчётов сигнала (п. 6 задания).

    Данные добавляются порциями (Chunk.ppg) по мере поступления от
    источника и хранятся до тех пор, пока их не заберёт потребитель
    (блок сегментации на окна). Буфер не имеет ограничения по размеру —
    для учебной задачи этого достаточно; в реальном устройстве стоит
    ограничить максимальную длину (deque(maxlen=...)).
    """

    def __init__(self):
        self._data: list[float] = []
        self._t0: float | None = None
        self._fs: float | None = None

    def push(self, ppg: np.ndarray, t0: float, fs: float) -> None:
        if self._t0 is None:
            self._t0 = t0
            self._fs = fs
        self._data.extend(ppg.tolist())

    def __len__(self) -> int:
        return len(self._data)

    def duration_s(self) -> float:
        return len(self._data) / self._fs if self._fs else 0.0

    def as_array(self) -> np.ndarray:
        return np.asarray(self._data, dtype=np.float64)

    def sampling_rate(self) -> float:
        return self._fs or 0.0


@dataclass
class Window:
    """Окно сигнала фиксированной длины, готовое для извлечения признаков."""
    samples: np.ndarray   # отсчёты окна (после ресемплинга до fs_target)
    t_start: float        # время начала окна, с
    fs: float             # частота дискретизации окна, Гц


class Resampler:
    """
    Блок приведения сигнала к целевой частоте дискретизации (п. 7).

    Пример: запись PhysioNet снята с частотой 500 Гц, а вся дальнейшая
    обработка (фильтрация, признаки, нейросеть) рассчитана на 50 Гц —
    как и предусмотрено в отчёте по ЛР № 1 (раздел 3.4). Прореживание
    выполняется полифазным фильтром resample_poly, что одновременно
    подавляет алиасинг.
    """

    def __init__(self, fs_target: float = 50.0):
        self.fs_target = fs_target

    def __call__(self, samples: np.ndarray, fs_in: float) -> np.ndarray:
        if abs(fs_in - self.fs_target) < 1e-6:
            return samples
        from math import gcd
        up = int(round(self.fs_target * 100))
        down = int(round(fs_in * 100))
        g = gcd(up, down)
        return resample_poly(samples, up // g, down // g)


class WindowSegmenter:
    """
    Формирование окон фиксированной длины с перекрытием (п. 7).

    Использует параметры из отчёта ЛР № 1 (раздел 3.4): окно 8 с,
    шаг 2 с (перекрытие 75 %). Работает поверх RingBuffer и Resampler.
    """

    def __init__(self, win_s: float = 8.0, step_s: float = 2.0,
                 fs_target: float = 50.0):
        self.win_s = win_s
        self.step_s = step_s
        self.resampler = Resampler(fs_target)
        self.fs_target = fs_target
        self._served_s = 0.0   # сколько секунд буфера уже выдано окнами

    def available_windows(self, buf: RingBuffer) -> list[Window]:
        """Вернуть все новые окна, которые уже можно сформировать из буфера."""
        windows: list[Window] = []
        fs_in = buf.sampling_rate()
        if not fs_in:
            return windows
        data = buf.as_array()
        while (self._served_s + self.win_s) * fs_in <= len(data):
            start = int(self._served_s * fs_in)
            end = int((self._served_s + self.win_s) * fs_in)
            raw = data[start:end]
            resampled = self.resampler(raw, fs_in)
            windows.append(Window(samples=resampled, t_start=self._served_s,
                                   fs=self.fs_target))
            self._served_s += self.step_s
        return windows
