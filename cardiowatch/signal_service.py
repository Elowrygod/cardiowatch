"""
Сетевой сервис источника сигнала (для упаковки в Docker-контейнер).

Идея: вместо того чтобы источник сигнала (SignalSource) жил внутри того
же процесса, что и обработка, он выделяется в отдельный сервис —
имитацию реальных смарт-часов, которые физически отделены от сервера
обработки и передают данные по сети. Сервис оборачивает уже готовые
классы SyntheticPpgSource / PhysioNetSource (см. signal_source.py) в
WebSocket-сервер: любой подключившийся клиент получает непрерывный
поток порций сигнала (chunk), как это делал бы Bluetooth-модуль часов,
только вместо Bluetooth — TCP/WebSocket.

Формат сообщения (JSON, одна порция на одно сообщение):
    {
      "t0": <float>,   время начала порции относительно старта источника, с
      "fs": <float>,   частота дискретизации, Гц
      "ppg": [<float>, ...]   отсчёты порции
    }

Переменные окружения (все необязательные, см. значения по умолчанию):
    SOURCE_TYPE     synthetic | physionet     (по умолчанию synthetic)
    HEART_RATE      ЧСС для синтетического источника, уд/мин (по умолчанию 70)
    FS              частота дискретизации синтетического источника, Гц (100)
    RECORD_PATH     путь к записи WFDB/CSV — обязателен при SOURCE_TYPE=physionet
    CHANNEL         канал записи PhysioNet (по умолчанию pleth_1)
    CHUNK_SECONDS   длительность одной порции, с (по умолчанию 1.0)
    REALTIME        "1" — отправлять с реальной задержкой между порциями
                     (имитация темпа настоящего датчика), "0" — как можно
                     быстрее, без пауз (по умолчанию "1")
    HOST / PORT     адрес и порт сервера (по умолчанию 0.0.0.0:8765)
"""

from __future__ import annotations
import asyncio     # асинхронный цикл обработки подключений (сервер обслуживает много клиентов одновременно)
import json        # сериализация порции сигнала в формат сообщения WebSocket
import logging     # журналирование событий сервиса (подключения, параметры источника)
import os          # чтение конфигурации из переменных окружения контейнера

import websockets  # сторонняя библиотека, реализующая протокол WebSocket (RFC 6455)

from .signal_source import SyntheticPpgSource, PhysioNetSource, SignalSource  # оба варианта источника из ЛР № 2, п. 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")  # формат строк журнала
log = logging.getLogger("signal_service")  # именованный логгер модуля


def build_source() -> SignalSource:
    """Создаёт источник согласно переменным окружения (см. описание модуля)."""
    kind = os.environ.get("SOURCE_TYPE", "synthetic").lower()   # тип источника; synthetic — значение по умолчанию
    if kind == "physionet":
        record_path = os.environ["RECORD_PATH"]  # обязателен для этого режима
        channel = os.environ.get("CHANNEL", "pleth_1")           # канал по умолчанию — "pleth_1" (ФПГ)
        log.info("Источник: PhysioNetSource(record_path=%s, channel=%s)", record_path, channel)
        return PhysioNetSource(record_path=record_path, channel=channel)  # источник на реальной записи

    hr = float(os.environ.get("HEART_RATE", "70"))               # ЧСС для математической модели, уд/мин
    fs = float(os.environ.get("FS", "100"))                      # частота дискретизации модели, Гц
    log.info("Источник: SyntheticPpgSource(fs=%s, heart_rate_bpm=%s)", fs, hr)
    return SyntheticPpgSource(fs=fs, heart_rate_bpm=hr)           # источник по умолчанию — математическая модель


async def _stream_to_client(ws, chunk_s: float, realtime: bool) -> None:
    """Обслуживает одно подключение: у каждого клиента — свой независимый
    источник (как если бы каждый клиент был отдельными часами)."""
    source = build_source()                   # отдельный экземпляр источника на каждое подключение
    peer = ws.remote_address                  # адрес подключившегося клиента (для журнала)
    log.info("Клиент подключился: %s", peer)
    try:
        while True:                           # пока клиент не отключился — бесконечно шлём новые порции
            chunk = source.read_chunk(chunk_s)             # получаем очередную порцию данных от источника
            msg = json.dumps({                             # собираем JSON-сообщение по формату из докстринга модуля
                "t0": chunk.t0,
                "fs": chunk.fs,
                "ppg": chunk.ppg.tolist(),                 # numpy-массив -> обычный список (JSON не умеет ndarray)
            })
            await ws.send(msg)                             # отправляем сообщение клиенту по WebSocket
            if realtime:                                   # если включён режим реального времени —
                await asyncio.sleep(chunk_s)               # ждём столько же, сколько "прошло" в самой порции
    except websockets.exceptions.ConnectionClosed:          # клиент закрыл соединение — это штатная ситуация
        log.info("Клиент отключился: %s", peer)


async def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")                # слушаем все сетевые интерфейсы контейнера по умолчанию
    port = int(os.environ.get("PORT", "8765"))               # порт WebSocket-сервера
    chunk_s = float(os.environ.get("CHUNK_SECONDS", "1.0"))  # длительность одной порции данных, с
    realtime = os.environ.get("REALTIME", "1") not in ("0", "false", "False")  # булев флаг из текстовой переменной окружения

    async def handler(ws):
        await _stream_to_client(ws, chunk_s, realtime)       # делегируем всю работу с конкретным клиентом отдельной функции

    log.info("Сервис источника сигнала запущен: ws://%s:%s (realtime=%s, chunk=%.1fs)",
              host, port, realtime, chunk_s)
    async with websockets.serve(handler, host, port):        # поднимаем сервер и регистрируем handler для новых подключений
        await asyncio.Future()  # работает, пока контейнер не остановят


if __name__ == "__main__":
    asyncio.run(main())                                       # точка входа при запуске `python -m cardiowatch.signal_service`
