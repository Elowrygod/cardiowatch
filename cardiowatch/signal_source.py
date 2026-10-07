"""
Блок приёма данных от датчика (Лабораторная работа № 2, п. 5).

Реализует единый интерфейс SignalSource с двумя вариантами источника,
как это было предусмотрено диаграммой классов в Лабораторной работе № 1:

  - PhysioNetSource     — чтение реальной записи ФПГ из датасета
                          Pulse Transit Time PPG Dataset (PhysioNet, формат WFDB);
  - SyntheticPpgSource  — математическая модель пульсовой волны
                          (см. отчёт по ЛР № 1, раздел 3.3, формулы 1-6).

Оба класса отдают данные одинаково — порциями (chunk) заданной длительности,
как это делал бы реальный оптический датчик смарт-часов.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Chunk:
    """Порция сырых данных, отданная источником за один вызов read_chunk()."""
    ppg: np.ndarray            # отсчёты ФПГ, В (условные единицы)
    acc: np.ndarray            # отсчёты акселерометра (N x 3) либо None
    t0: float                  # время начала порции, с
    fs: float                  # частота дискретизации источника, Гц


class SignalSource(ABC):
    """Общий интерфейс источника сигнала (см. UML, диаграмма классов ЛР № 1)."""

    @abstractmethod
    def sampling_rate(self) -> float:
        """Частота дискретизации источника, Гц."""

    @abstractmethod
    def read_chunk(self, seconds: float) -> Chunk:
        """Вернуть очередную порцию данных длительностью seconds секунд."""

    def reset(self) -> None:
        """Сбросить внутреннее состояние источника (по умолчанию — ничего)."""
        pass


# ---------------------------------------------------------------------------
#  Вариант 1. Реальные данные: PhysioNet Pulse Transit Time PPG Dataset 1.1.0
# ---------------------------------------------------------------------------
class PhysioNetSource(SignalSource):
    """
    Источник на основе реальной записи из датасета PhysioNet.

    Требует установленный пакет `wfdb` (pip install wfdb) и локально
    скачанную запись (например, s1_walk или s1_sit из Pulse Transit Time
    PPG Dataset). Скачать записи можно командой:

        wget -r -N -c -np https://physionet.org/files/pulse-transit-time-ppg/1.1.0/

    или через PhysioNetFileDownloader на странице датасета.

    Пример использования:

        src = PhysioNetSource("csv/s1_sit.csv", channel="pleth_1", fs=500.0)
        chunk = src.read_chunk(1.0)   # 1 секунда отсчётов
    """

    def __init__(self, record_path: str, channel: str = "pleth_1", fs: float = 500.0):
        self.record_path = record_path
        self.channel = channel
        self.fs = fs
        self._data = None
        self._pos = 0
        self._load()

    def _load(self) -> None:
        try:
            import wfdb  # type: ignore
            record = wfdb.rdrecord(self.record_path)
            idx = record.sig_name.index(self.channel)
            self._data = record.p_signal[:, idx].astype(np.float64)
            self.fs = float(record.fs)
        except ImportError:
            # Резервный вариант: запись в формате CSV с колонкой self.channel
            import csv
            path = self.record_path
            if not path.endswith(".csv"):
                path = path + ".csv"
            vals = []
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vals.append(float(row[self.channel]))
            self._data = np.asarray(vals, dtype=np.float64)

    def sampling_rate(self) -> float:
        return self.fs

    def read_chunk(self, seconds: float) -> Chunk:
        n = int(round(seconds * self.fs))
        end = min(self._pos + n, len(self._data))
        ppg = self._data[self._pos:end]
        t0 = self._pos / self.fs
        self._pos = end
        if len(ppg) < n:
            # запись закончилась — сообщаем вызывающему коду через короткий chunk
            pass
        return Chunk(ppg=ppg, acc=None, t0=t0, fs=self.fs)

    def reset(self) -> None:
        self._pos = 0


# ---------------------------------------------------------------------------
#  Вариант 2. Математическая модель ФПГ (генератор), см. отчёт ЛР № 1, 3.3
# ---------------------------------------------------------------------------
@dataclass
class PulseModelParams:
    """Параметры модели одного удара пульса P(t) и шумов (формулы 1-6 ЛР № 1)."""
    a1: float = 0.88          # амплитуда систолического пика
    a2: float = 0.15          # амплитуда дикротического изгиба
    sigma_rise: float = 0.22  # ширина фронта подъёма, с
    sigma_fall: float = 0.05  # ширина спада, с
    notch_offset: float = 0.25   # смещение изгиба относительно пика, с
    sigma_notch: float = 0.08    # ширина изгиба, с
    drift_amp: float = 0.05      # амплитуда дыхательного дрейфа
    drift_freq: float = 0.25     # частота дыхания, Гц
    noise_std: float = 0.03      # СКО белого шума (доля амплитуды)
    hrv_std: float = 0.03        # СКО вариабельности RR-интервалов, с


class SyntheticPpgSource(SignalSource):
    """
    Генератор сигнала ФПГ по математической модели.

    Позволяет прямо в конструкторе или методом set_heart_rate() задавать
    профиль ЧСС во времени — в том числе плавный переход "покой -> тахикардия",
    что необходимо для проверки быстродействия алгоритмов сглаживания (п. 4
    настоящей лабораторной работы).
    """

    def __init__(self, fs: float = 100.0, heart_rate_bpm=70.0,
                 params: PulseModelParams | None = None, seed: int = 42):
        self.fs = fs
        self.params = params or PulseModelParams()
        self._rng = np.random.default_rng(seed)
        self._t_cursor = 0.0
        self._beats: list[float] = [0.0]   # уже сгенерированные моменты ударов
        self._hr_fn = self._make_hr_fn(heart_rate_bpm)

    @staticmethod
    def _make_hr_fn(heart_rate_bpm):
        """heart_rate_bpm: число (постоянная ЧСС) либо функция t -> ЧСС(t)."""
        if callable(heart_rate_bpm):
            return heart_rate_bpm
        const = float(heart_rate_bpm)
        return lambda t: const

    def set_heart_rate(self, heart_rate_bpm) -> None:
        self._hr_fn = self._make_hr_fn(heart_rate_bpm)

    def sampling_rate(self) -> float:
        return self.fs

    def _single_beat(self, tau: np.ndarray) -> np.ndarray:
        """P(t) — модель одного удара, формула (2) отчёта ЛР № 1."""
        p = self.params
        sigma = np.where(tau <= 0, p.sigma_rise, p.sigma_fall)
        systolic = p.a1 * np.exp(-(tau ** 2) / (2 * sigma ** 2))
        notch = p.a2 * np.exp(-((tau + p.notch_offset) ** 2) / (2 * p.sigma_notch ** 2))
        return systolic + notch

    def read_chunk(self, seconds: float) -> Chunk:
        """Формирует очередную порцию отсчётов длительностью seconds секунд.

        Моменты ударов t_k наращиваются по формуле (5) отчёта ЛР № 1:
        RR_k = 60/ЧСС(t) + дельта_k, дельта_k ~ N(0, hrv_std).
        Список ударов расширяется один раз и далее только дополняется —
        это гарантирует непрерывность (одинаковые t_k при повторном чтении
        соседних чанков) в отличие от пересчёта с нуля на каждом вызове.
        """
        p = self.params
        n = int(round(seconds * self.fs))
        t = self._t_cursor + np.arange(n) / self.fs
        signal = np.zeros(n)

        while self._beats[-1] < t[-1] + 1.5:
            last = self._beats[-1]
            hr = max(self._hr_fn(last), 1.0)
            rr = 60.0 / hr + self._rng.normal(0, p.hrv_std)
            self._beats.append(last + max(rr, 0.25))

        for tk in self._beats:
            if tk < t[0] - 1.0 or tk > t[-1] + 1.0:
                continue
            tau = t - tk
            mask = np.abs(tau) < 1.0
            signal[mask] += self._single_beat(tau[mask])

        drift = p.drift_amp * np.sin(2 * np.pi * p.drift_freq * t)
        noise = self._rng.normal(0, p.noise_std, size=n)
        signal = signal + drift + noise

        self._t_cursor = t[-1] + 1.0 / self.fs
        return Chunk(ppg=signal, acc=None, t0=t[0], fs=self.fs)

    def reset(self) -> None:
        self._t_cursor = 0.0
        self._beats = [0.0]
