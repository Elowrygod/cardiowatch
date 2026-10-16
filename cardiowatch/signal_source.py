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
from abc import ABC, abstractmethod   # базовый класс и декоратор для абстрактных методов
from dataclasses import dataclass, field  # авто-генерация __init__/__repr__ для простых структур данных
import numpy as np                    # хранение и обработка отсчётов сигнала


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
        self.record_path = record_path   # путь к записи (без расширения — для wfdb, с .csv — для запасного варианта)
        self.channel = channel           # имя канала/колонки с нужным сигналом (обычно "pleth_1" — ФПГ)
        self.fs = fs                     # частота дискретизации по умолчанию; будет перезаписана реальным значением из записи
        self._data = None                # сюда попадёт весь сигнал целиком после _load()
        self._pos = 0                    # текущая позиция чтения внутри self._data, в отсчётах
        self._load()                     # сразу читаем запись в память при создании объекта

    def _load(self) -> None:
        try:
            import wfdb  # type: ignore                         # основной способ: библиотека PhysioNet для формата WFDB
            record = wfdb.rdrecord(self.record_path)             # читаем заголовок + все каналы записи
            idx = record.sig_name.index(self.channel)            # находим номер нужного канала по его имени
            self._data = record.p_signal[:, idx].astype(np.float64)  # вытаскиваем только этот канал как 1D-массив
            self.fs = float(record.fs)                           # берём настоящую частоту дискретизации записи
        except ImportError:
            # Резервный вариант: запись в формате CSV с колонкой self.channel
            import csv
            path = self.record_path
            if not path.endswith(".csv"):                        # на случай, если путь передан без расширения
                path = path + ".csv"
            vals = []                                             # сюда накапливаем значения канала построчно
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)                        # читаем CSV как словари {имя_колонки: значение}
                for row in reader:
                    vals.append(float(row[self.channel]))         # берём только нужную колонку и переводим в float
            self._data = np.asarray(vals, dtype=np.float64)       # превращаем список в numpy-массив для дальнейшей работы

    def sampling_rate(self) -> float:
        return self.fs                                            # просто отдаём сохранённую частоту дискретизации

    def read_chunk(self, seconds: float) -> Chunk:
        n = int(round(seconds * self.fs))                         # сколько отсчётов нужно вернуть за seconds секунд
        end = min(self._pos + n, len(self._data))                 # не выходим за пределы записи
        ppg = self._data[self._pos:end]                           # сам срез нужной длины
        t0 = self._pos / self.fs                                  # время начала этой порции относительно начала записи
        self._pos = end                                           # сдвигаем курсор чтения для следующего вызова
        if len(ppg) < n:
            # запись закончилась — сообщаем вызывающему коду через короткий chunk
            pass
        return Chunk(ppg=ppg, acc=None, t0=t0, fs=self.fs)        # у ФПГ-записи из PhysioNet нет акселерометра -> acc=None

    def reset(self) -> None:
        self._pos = 0                                             # вернуть курсор чтения в начало записи


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
        self.fs = fs                                     # частота дискретизации генерируемого сигнала, Гц
        self.params = params or PulseModelParams()       # параметры формы импульса и шумов (значения по умолчанию, если не заданы)
        self._rng = np.random.default_rng(seed)          # отдельный генератор случайных чисел — для воспроизводимости
        self._t_cursor = 0.0                             # время конца уже выданного сигнала, с
        self._beats: list[float] = [0.0]                 # уже сгенерированные моменты ударов
        self._hr_fn = self._make_hr_fn(heart_rate_bpm)   # функция t -> ЧСС(t), даже если задано одно число

    @staticmethod
    def _make_hr_fn(heart_rate_bpm):
        """heart_rate_bpm: число (постоянная ЧСС) либо функция t -> ЧСС(t)."""
        if callable(heart_rate_bpm):                     # если передали функцию — используем её как есть
            return heart_rate_bpm
        const = float(heart_rate_bpm)                    # если передали число — оборачиваем в функцию-константу
        return lambda t: const

    def set_heart_rate(self, heart_rate_bpm) -> None:
        self._hr_fn = self._make_hr_fn(heart_rate_bpm)   # позволяет сменить профиль ЧСС уже после создания источника

    def sampling_rate(self) -> float:
        return self.fs

    def _single_beat(self, tau: np.ndarray) -> np.ndarray:
        """P(t) — модель одного удара, формула (2) отчёта ЛР № 1."""
        p = self.params
        sigma = np.where(tau <= 0, p.sigma_rise, p.sigma_fall)   # разная ширина для фронта подъёма и спада (несимметричный импульс)
        systolic = p.a1 * np.exp(-(tau ** 2) / (2 * sigma ** 2))  # гауссиана систолического пика
        notch = p.a2 * np.exp(-((tau + p.notch_offset) ** 2) / (2 * p.sigma_notch ** 2))  # гауссиана дикротического изгиба со сдвигом
        return systolic + notch                                   # итоговая форма одного удара — сумма двух гауссиан

    def read_chunk(self, seconds: float) -> Chunk:
        """Формирует очередную порцию отсчётов длительностью seconds секунд.

        Моменты ударов t_k наращиваются по формуле (5) отчёта ЛР № 1:
        RR_k = 60/ЧСС(t) + дельта_k, дельта_k ~ N(0, hrv_std).
        Список ударов расширяется один раз и далее только дополняется —
        это гарантирует непрерывность (одинаковые t_k при повторном чтении
        соседних чанков) в отличие от пересчёта с нуля на каждом вызове.
        """
        p = self.params
        n = int(round(seconds * self.fs))                # число отсчётов в этой порции
        t = self._t_cursor + np.arange(n) / self.fs       # временная шкала порции (продолжает предыдущую)
        signal = np.zeros(n)                              # сюда будем суммировать вклад всех ударов

        while self._beats[-1] < t[-1] + 1.5:              # догенерируем удары с запасом в 1.5 с вперёд за конец порции
            last = self._beats[-1]                        # время последнего уже сгенерированного удара
            hr = max(self._hr_fn(last), 1.0)               # ЧСС в момент last (не даём уйти в 0 или отрицательные значения)
            rr = 60.0 / hr + self._rng.normal(0, p.hrv_std)  # RR-интервал = среднее значение + случайный разброс (вариабельность)
            self._beats.append(last + max(rr, 0.25))       # следующий удар — не раньше, чем через 0.25 с (ограничение физиологии)

        for tk in self._beats:                            # проходим по всем известным моментам ударов
            if tk < t[0] - 1.0 or tk > t[-1] + 1.0:        # пропускаем удары, которые точно не попадают в текущее окно
                continue
            tau = t - tk                                   # локальное время относительно момента удара tk
            mask = np.abs(tau) < 1.0                       # учитываем вклад удара только в пределах ±1 с от его центра
            signal[mask] += self._single_beat(tau[mask])   # накладываем форму одного удара P(t) на общий сигнал

        drift = p.drift_amp * np.sin(2 * np.pi * p.drift_freq * t)  # медленный дыхательный дрейф изолинии
        noise = self._rng.normal(0, p.noise_std, size=n)            # белый шум измерения
        signal = signal + drift + noise                             # итоговый модельный сигнал ФПГ

        self._t_cursor = t[-1] + 1.0 / self.fs            # запоминаем, где закончилась эта порция, для следующего вызова
        return Chunk(ppg=signal, acc=None, t0=t[0], fs=self.fs)

    def reset(self) -> None:
        self._t_cursor = 0.0                              # сбрасываем время
        self._beats = [0.0]                               # и список ударов — к исходному состоянию
