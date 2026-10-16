"""
Буфер принятого сигнала и блок дискретизации/синхронизации выборки
(Лабораторная работа № 2, п. 6-7).
"""

from __future__ import annotations
from collections import deque               # альтернатива list с ограничением длины (упомянута в докстринге ниже)
from dataclasses import dataclass           # авто-генерация __init__ для простой структуры Window
import numpy as np                          # работа с массивами отсчётов
from scipy.signal import resample_poly      # полифазный ресемплинг с подавлением алиасинга


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
        self._data: list[float] = []            # все накопленные отсчёты одним списком
        self._t0: float | None = None           # время начала самого первого принятого отсчёта, с
        self._fs: float | None = None           # частота дискретизации поступающих данных, Гц

    def push(self, ppg: np.ndarray, t0: float, fs: float) -> None:
        if self._t0 is None:                    # запоминаем t0/fs только при самом первом вызове push()
            self._t0 = t0
            self._fs = fs
        self._data.extend(ppg.tolist())         # дописываем новую порцию отсчётов в конец буфера

    def __len__(self) -> int:
        return len(self._data)                  # позволяет писать len(buf) вместо buf.something()

    def duration_s(self) -> float:
        return len(self._data) / self._fs if self._fs else 0.0   # сколько секунд сигнала сейчас накоплено

    def as_array(self) -> np.ndarray:
        return np.asarray(self._data, dtype=np.float64)          # отдать весь буфер как numpy-массив для обработки

    def sampling_rate(self) -> float:
        return self._fs or 0.0                  # 0.0, если данных ещё не было (чтобы не вернуть None)


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
        self.fs_target = fs_target              # целевая частота дискретизации, к которой приводим любой вход

    def __call__(self, samples: np.ndarray, fs_in: float) -> np.ndarray:
        if abs(fs_in - self.fs_target) < 1e-6:  # частота уже совпадает — ресемплинг не нужен
            return samples
        from math import gcd
        up = int(round(self.fs_target * 100))   # числитель дроби fs_target/fs_in с точностью до 0,01 Гц
        down = int(round(fs_in * 100))           # знаменатель той же дроби
        g = gcd(up, down)                        # сокращаем дробь на НОД, чтобы resample_poly работал быстрее
        return resample_poly(samples, up // g, down // g)  # полифазный ресемплинг: интерполяция up/g, прореживание down/g раз


class WindowSegmenter:
    """
    Формирование окон фиксированной длины с перекрытием (п. 7).

    Использует параметры из отчёта ЛР № 1 (раздел 3.4): окно 8 с,
    шаг 2 с (перекрытие 75 %). Работает поверх RingBuffer и Resampler.
    """

    def __init__(self, win_s: float = 8.0, step_s: float = 2.0,
                 fs_target: float = 50.0):
        self.win_s = win_s                      # длительность одного окна, с
        self.step_s = step_s                    # шаг между началами соседних окон, с (меньше win_s => есть перекрытие)
        self.resampler = Resampler(fs_target)   # используем тот же Resampler для приведения каждого окна к fs_target
        self.fs_target = fs_target
        self._served_s = 0.0                    # сколько секунд буфера уже выдано окнами (курсор сегментации)

    def available_windows(self, buf: RingBuffer) -> list[Window]:
        """Вернуть все новые окна, которые уже можно сформировать из буфера."""
        windows: list[Window] = []              # сюда будем собирать все готовые окна за этот вызов
        fs_in = buf.sampling_rate()             # частота дискретизации данных в буфере (как они туда попали)
        if not fs_in:                           # буфер пока пуст — отдавать нечего
            return windows
        data = buf.as_array()                   # читаем весь накопленный сигнал один раз
        while (self._served_s + self.win_s) * fs_in <= len(data):   # пока в буфере хватает данных на ещё одно целое окно
            start = int(self._served_s * fs_in)                     # начало окна в отсчётах буфера
            end = int((self._served_s + self.win_s) * fs_in)        # конец окна в отсчётах буфера
            raw = data[start:end]                                   # сам срез — окно на исходной частоте fs_in
            resampled = self.resampler(raw, fs_in)                  # приводим окно к единой целевой частоте fs_target
            windows.append(Window(samples=resampled, t_start=self._served_s,
                                   fs=self.fs_target))               # сохраняем готовое окно с его временной привязкой
            self._served_s += self.step_s                           # сдвигаем курсор на шаг — так получается перекрытие
        return windows
