"""
Демонстрационный скрипт для Лабораторной работы № 2.

Прогоняет синтетический источник данных через весь пайплайн:
  источник -> буфер -> дискретизация/сегментация -> предобработка,
и строит графики, иллюстрирующие работу каждого блока.

Запуск:  python demo.py
Результат: PNG-файлы в папке ./plots
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy.fft import rfft, rfftfreq

from cardiowatch.signal_source import SyntheticPpgSource, PulseModelParams
from cardiowatch.buffer import RingBuffer, WindowSegmenter, Resampler
from cardiowatch.preprocessing import simple_ema, adaptive_ema, bandpass_filter

OUT = os.path.join(os.path.dirname(__file__), "plots")
os.makedirs(OUT, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 140,
    "font.size": 10,
    "axes.grid": True,
    "grid.alpha": 0.3,
})


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print("saved", path)


# ---------------------------------------------------------------------------
# 1. Сырой сигнал источника (покой, ЧСС = 70 уд/мин)
# ---------------------------------------------------------------------------
src = SyntheticPpgSource(fs=100.0, heart_rate_bpm=70.0, seed=1)
chunk = src.read_chunk(10.0)
t = chunk.t0 + np.arange(len(chunk.ppg)) / chunk.fs

fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(t, chunk.ppg, color="#1f77b4", lw=1.1)
ax.set_title("Сырой сигнал источника (покой, ЧСС = 70 уд/мин, fs = 100 Гц)")
ax.set_xlabel("Время, с")
ax.set_ylabel("Амплитуда, у.е.")
save(fig, "01_raw_signal.png")

# ---------------------------------------------------------------------------
# 2. Простая EMA при разных N
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(t, chunk.ppg, color="#bbbbbb", lw=0.9, label="Сырой сигнал")
for n, color in zip([5, 15, 30], ["#2ca02c", "#ff7f0e", "#d62728"]):
    ema = simple_ema(chunk.ppg, n=n)
    ax.plot(t, ema, color=color, lw=1.4, label=f"EMA, N={n}")
ax.set_title("Сглаживание простой EMA при разных периодах N")
ax.set_xlabel("Время, с")
ax.set_ylabel("Амплитуда, у.е.")
ax.legend(loc="upper right", fontsize=8)
save(fig, "02_simple_ema.png")

# ---------------------------------------------------------------------------
# 3. Полосовой фильтр Баттерворта: до / после
# ---------------------------------------------------------------------------
filtered = bandpass_filter(chunk.ppg, fs=chunk.fs, low_hz=0.5, high_hz=8.0)

fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
axes[0].plot(t, chunk.ppg, color="#d62728", lw=1.0)
axes[0].set_title("До фильтрации (сырой сигнал + шум)")
axes[0].set_ylabel("Амплитуда, у.е.")
axes[1].plot(t, filtered, color="#1f77b4", lw=1.2)
axes[1].set_title("После полосового фильтра Баттерворта (0,5–8 Гц)")
axes[1].set_xlabel("Время, с")
axes[1].set_ylabel("Амплитуда, у.е.")
save(fig, "03_bandpass_before_after.png")

# ---------------------------------------------------------------------------
# 4. Спектр сигнала (FFT) до и после фильтрации
# ---------------------------------------------------------------------------
def spectrum(x, fs):
    n = len(x)
    freqs = rfftfreq(n, d=1.0 / fs)
    mag = np.abs(rfft(x)) / n
    return freqs, mag

f_raw, m_raw = spectrum(chunk.ppg, chunk.fs)
f_filt, m_filt = spectrum(filtered, chunk.fs)

fig, ax = plt.subplots(figsize=(8, 3.2))
ax.plot(f_raw, m_raw, color="#d62728", lw=1.0, label="До фильтрации")
ax.plot(f_filt, m_filt, color="#1f77b4", lw=1.2, label="После фильтрации")
ax.set_xlim(0, 20)
ax.set_title("Спектр сигнала до и после полосовой фильтрации")
ax.set_xlabel("Частота, Гц")
ax.set_ylabel("Амплитуда спектра")
ax.legend(fontsize=8)
save(fig, "04_spectrum.png")

# ---------------------------------------------------------------------------
# 5. Полосовой фильтр применяется к сырой форме волны — он подавляет
#    дикротический изгиб на этапе поиска пиков, поэтому именно фильтр,
#    а не EMA/KAMA, отвечает за корректное выделение пиков (проверено
#    экспериментально: EMA/KAMA поверх сырой волны не убирают "ступеньку",
#    и наивный поиск пиков даёт двойные срабатывания на каждый удар).
#    Правильное место для EMA и адаптивной EMA — сглаживание уже
#    ИЗВЛЕЧЁННОГО ряда ЧСС между последовательными ударами: там они решают
#    свою прямую задачу — подавление шума измерения при сохранении
#    быстрой реакции на реальное изменение тренда.
# ---------------------------------------------------------------------------
def hr_profile(t):
    # плавный, но выраженный переход 70 -> 140 уд/мин на 15-й секунде
    return 70.0 + 70.0 / (1.0 + np.exp(-(t - 15.0) / 1.0))


def true_beats(hr_fn, duration_s, hrv_std, seed):
    """Истинные моменты ударов сердца по формуле (5) отчёта ЛР № 1."""
    rng = np.random.default_rng(seed)
    beats = [0.0]
    while beats[-1] < duration_s:
        hr = max(hr_fn(beats[-1]), 1.0)
        rr = 60.0 / hr + rng.normal(0, hrv_std)
        beats.append(beats[-1] + max(rr, 0.25))
    return np.asarray(beats)


rng_meas = np.random.default_rng(7)
beats = true_beats(hr_profile, duration_s=30.0, hrv_std=0.015, seed=6)
# ошибка определения RR-интервала алгоритмом поиска пиков (джиттер ~10-20 мс)
rr_true = np.diff(beats)
rr_meas = rr_true + rng_meas.normal(0, 0.02, size=len(rr_true))
hr_meas = 60.0 / np.clip(rr_meas, 0.2, None)          # "сырая" (шумная) оценка ЧСС по ударам
t_beats = beats[1:]
hr_true_at_beats = hr_profile(t_beats)

# Простая EMA взята с N=15 — периодом, обеспечивающим хорошее подавление
# шума в покое (см. подбор параметров ниже); KAMA настроена так, чтобы
# иметь СРАВНИМОЕ подавление шума в покое, но заведомо более быстрый режим
# (n_fast=2) на выраженном тренде.
ema_hr = simple_ema(hr_meas, n=15)
kama_hr = adaptive_ema(hr_meas, er_window=8, n_fast=2, n_slow=40)

fig, ax = plt.subplots(figsize=(9, 3.6))
ax.scatter(t_beats, hr_meas, color="#bbbbbb", s=14, label="Оценка ЧСС по удару (с шумом измерения)")
ax.plot(t_beats, hr_true_at_beats, color="k", ls="--", lw=1.3, label="Истинный профиль ЧСС")
ax.plot(t_beats, ema_hr, color="#ff7f0e", lw=1.6, label="Простая EMA (N=15)")
ax.plot(t_beats, kama_hr, color="#2ca02c", lw=1.8, label="Адаптивная EMA (KAMA)")
ax.axvline(15.0, color="k", ls=":", lw=1, alpha=0.5)
ax.set_title("Сглаживание ряда ЧСС при переходе покой → тахикардия (70 → 140 уд/мин)")
ax.set_xlabel("Время, с")
ax.set_ylabel("ЧСС, уд/мин")
ax.legend(loc="lower right", fontsize=8)
save(fig, "05_hr_trend_ema_vs_kama.png")

# Количественное сравнение: время выхода на 90% скачка и шум в состоянии покоя
def time_to_90pct(t_arr, y_arr, base, final, t_event):
    target = base + 0.9 * (final - base)
    after = t_arr >= t_event
    idx = np.argmax(y_arr[after] >= target)
    return t_arr[after][idx] - t_event if np.any(y_arr[after] >= target) else float("nan")

base_hr, final_hr = 70.0, 140.0
d_ema = time_to_90pct(t_beats, ema_hr, base_hr, final_hr, 15.0)
d_kama = time_to_90pct(t_beats, kama_hr, base_hr, final_hr, 15.0)
rest_mask = t_beats < 14.0
rmse_ema_rest = np.sqrt(np.mean((ema_hr[rest_mask] - base_hr) ** 2))
rmse_kama_rest = np.sqrt(np.mean((kama_hr[rest_mask] - base_hr) ** 2))
print(f"Время выхода на 90% скачка ЧСС: простая EMA = {d_ema:.2f} с, KAMA = {d_kama:.2f} с")
print(f"RMSE в покое (шум): простая EMA = {rmse_ema_rest:.2f} уд/мин, KAMA = {rmse_kama_rest:.2f} уд/мин")

# ---------------------------------------------------------------------------
# 6. Иллюстрация буфера, ресемплинга и нарезки на окна
# ---------------------------------------------------------------------------
src3 = SyntheticPpgSource(fs=500.0, heart_rate_bpm=75.0, seed=3)   # имитация fs=500 Гц (PhysioNet)
buf = RingBuffer()
seg = WindowSegmenter(win_s=8.0, step_s=2.0, fs_target=50.0)

all_windows = []
for _ in range(3):  # 3 порции по 8 с = 24 с сырых данных на fs=500 Гц
    c = src3.read_chunk(8.0)
    buf.push(c.ppg, c.t0, c.fs)
    all_windows.extend(seg.available_windows(buf))

print(f"Источник: fs={src3.sampling_rate()} Гц, накоплено {buf.duration_s():.1f} с, "
      f"сформировано окон: {len(all_windows)} (fs_target={seg.fs_target} Гц, "
      f"win={seg.win_s} с, step={seg.step_s} с)")

raw_all = buf.as_array()
t_raw = np.arange(len(raw_all)) / buf.sampling_rate()

fig, ax = plt.subplots(figsize=(9, 3.4))
ax.plot(t_raw, raw_all, color="#888888", lw=0.7, label=f"Буфер (fs={int(buf.sampling_rate())} Гц)")
colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(all_windows)))
for w, c in zip(all_windows, colors):
    ax.axvspan(w.t_start, w.t_start + seg.win_s, color=c, alpha=0.15)
    ax.axvline(w.t_start, color=c, lw=1.0)
ax.set_title(f"Сегментация буфера на окна {seg.win_s:.0f} с с шагом {seg.step_s:.0f} с "
             f"(ресемплинг {int(buf.sampling_rate())} → {int(seg.fs_target)} Гц)")
ax.set_xlabel("Время, с")
ax.set_ylabel("Амплитуда, у.е.")
ax.legend(loc="upper right", fontsize=8)
save(fig, "07_windows_segmentation.png")

print("Готово. Все графики сохранены в", OUT)
