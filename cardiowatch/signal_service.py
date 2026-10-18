"""
Сервис «умных часов» внутри Docker-контейнера (Лабораторная работа № 3).

В ЛР № 2 этот сервис просто рассылал сырые отсчёты ФПГ. Теперь контейнер
играет роль самостоятельного устройства: сам генерирует сигнал, сам его
обрабатывает (буфер -> ресемплинг -> окна -> признаки ВСР -> нейросеть) и
в поток уходит уже готовый результат по каждому окну, а не сырые отсчёты.
Flutter-приложение (клиент) ничего не вычисляет — только рисует график и
пишет историю в БД.

Формат сообщения (JSON, одно окно — одно сообщение):
    {
      "t": <float>,          время начала окна от старта сеанса, с
      "hr": <float>,         ЧСС по этому окну, уд/мин
      "hr_smoothed": <float> ЧСС, сглаженная адаптивной EMA (KAMA, см. ЛР № 2)
      "sdnn": <float>, "rmssd": <float>, "pnn50": <float>   признаки ВСР, см. ЛР № 1
      "risk_prob": <float>,  вероятность класса "повышенный риск" (нейросеть)
      "risk_class": 0 | 1    0 - норма, 1 - повышенный риск (порог 0.5)
    }

Переменные окружения — как в ЛР № 2 (SOURCE_TYPE, HEART_RATE, FS,
RECORD_PATH, CHANNEL, HOST, PORT), плюс:
    WIN_SECONDS     длительность окна анализа, с (по умолчанию 8.0, как в ЛР № 1)
    STEP_SECONDS    шаг между окнами, с (по умолчанию 2.0)
    FS_TARGET       частота после ресемплинга, Гц (по умолчанию 50.0)
    MODEL_PATH      путь к обученной модели (по умолчанию model.pt, см. train_model.py)
"""

from __future__ import annotations
import asyncio
import json
import logging
import os

import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed   # импортируем явно: в websockets>=14 ленивая загрузка submodule'ей
                                                       # делает обращение "websockets.exceptions.ConnectionClosed" в except
                                                       # ненадёжным, если сам submodule не был импортирован отдельно

from .signal_source import SyntheticPpgSource, PhysioNetSource, SignalSource
from .buffer import RingBuffer, WindowSegmenter
from .features import window_features
from .preprocessing import adaptive_ema
from .model import RiskClassifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("signal_service")

_MODEL_CACHE: RiskClassifier | None = None   # модель грузим из файла один раз на процесс, а не на клиента


def get_model() -> RiskClassifier:
    """Загружает веса нейросети один раз и переиспользует для всех подключений."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        path = os.environ.get("MODEL_PATH", "model.pt")
        log.info("Загрузка модели риска: %s", path)
        _MODEL_CACHE = RiskClassifier.load(path)
    return _MODEL_CACHE


def build_source() -> SignalSource:
    """Без изменений по сравнению с ЛР № 2 — выбор варианта источника."""
    kind = os.environ.get("SOURCE_TYPE", "synthetic").lower()
    if kind == "physionet":
        record_path = os.environ["RECORD_PATH"]
        channel = os.environ.get("CHANNEL", "pleth_1")
        log.info("Источник: PhysioNetSource(record_path=%s, channel=%s)", record_path, channel)
        return PhysioNetSource(record_path=record_path, channel=channel)

    hr = float(os.environ.get("HEART_RATE", "70"))
    fs = float(os.environ.get("FS", "100"))
    log.info("Источник: SyntheticPpgSource(fs=%s, heart_rate_bpm=%s)", fs, hr)
    return SyntheticPpgSource(fs=fs, heart_rate_bpm=hr)


async def _stream_to_client(ws, chunk_s: float, realtime: bool,
                             win_s: float, step_s: float, fs_target: float) -> None:
    """
    Обслуживает одно подключение. У каждого клиента — собственный источник,
    буфер и сегментатор (как если бы у каждого клиента были свои часы), но
    общая на весь процесс модель (веса не меняются между клиентами).
    """
    source = build_source()
    buf = RingBuffer()
    seg = WindowSegmenter(win_s=win_s, step_s=step_s, fs_target=fs_target)
    model = get_model()
    hr_history: list[float] = []            # вся история ЧСС по окнам этого клиента — для KAMA (п. "Сглаженный тренд ЧСС")

    peer = ws.remote_address
    log.info("Клиент подключился: %s", peer)
    try:
        while True:
            chunk = source.read_chunk(chunk_s)         # очередная порция сырых отсчётов от "датчика"
            buf.push(chunk.ppg, chunk.t0, chunk.fs)     # накапливаем в буфере (ЛР № 2, п. 3.5)

            for window in seg.available_windows(buf):    # все окна, которые уже можно сформировать (ЛР № 2, п. 3.6)
                feat = window_features(window.samples, window.fs)   # ЧСС, SDNN, RMSSD, pNN50 (ЛР № 1 / features.py)
                if feat is None:                           # пиков нашлось слишком мало — окно пропускаем, не шлём мусор
                    continue

                hr_history.append(float(feat[0]))
                hr_smoothed = adaptive_ema(np.array(hr_history))[-1]   # KAMA по всей истории сеанса (ЛР № 2, п. 3.7.2)

                risk_prob = float(model.predict_proba(feat.reshape(1, -1))[0])  # инференс нейросети (ЛР № 3)
                risk_class = int(risk_prob >= 0.5)

                msg = json.dumps({
                    "t": window.t_start,
                    "hr": round(float(feat[0]), 1),
                    "hr_smoothed": round(float(hr_smoothed), 1),
                    "sdnn": round(float(feat[1]), 1),
                    "rmssd": round(float(feat[2]), 1),
                    "pnn50": round(float(feat[3]), 1),
                    "risk_prob": round(risk_prob, 3),
                    "risk_class": risk_class,
                })
                await ws.send(msg)                        # отправляем готовый результат клиенту (Flutter)

            if realtime:
                await asyncio.sleep(chunk_s)               # имитация реального темпа поступления данных с датчика
            else:
                await asyncio.sleep(0)                      # всё равно уступаем event loop — иначе один клиент с REALTIME=0 заблокирует всех остальных
    except ConnectionClosed:
        log.info("Клиент отключился: %s", peer)


async def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8765"))
    chunk_s = float(os.environ.get("CHUNK_SECONDS", "1.0"))
    realtime = os.environ.get("REALTIME", "1") not in ("0", "false", "False")
    win_s = float(os.environ.get("WIN_SECONDS", "8.0"))        # окно анализа — как в ЛР № 1/№ 2
    step_s = float(os.environ.get("STEP_SECONDS", "2.0"))      # шаг окна — как в ЛР № 1/№ 2
    fs_target = float(os.environ.get("FS_TARGET", "50.0"))     # частота после ресемплинга — как в ЛР № 1/№ 2

    get_model()   # грузим модель один раз при старте контейнера, а не при первом подключении (чтобы сразу увидеть ошибку, если model.pt отсутствует)

    async def handler(ws):
        await _stream_to_client(ws, chunk_s, realtime, win_s, step_s, fs_target)

    log.info("Устройство CardioWatch запущено: ws://%s:%s (окно=%.0fс, шаг=%.0fс, realtime=%s)",
              host, port, win_s, step_s, realtime)
    async with websockets.serve(handler, host, port):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
