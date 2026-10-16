"""
Тестовый клиент сервиса источника сигнала.

Подключается к запущенному сервису (локально или в Docker-контейнере)
и печатает статистику по каждой полученной порции — быстрый способ
убедиться, что контейнер действительно рассылает сигнал по сети,
без запуска всего остального конвейера (буфера, предобработки).

Запуск:
    python test_client.py                    # ws://localhost:8765
    python test_client.py ws://localhost:8765 --n 10
"""
import argparse       # разбор аргументов командной строки (адрес сервиса, число порций)
import asyncio        # клиент тоже асинхронный — та же модель, что и у сервиса
import json           # разбор JSON-сообщений от сервиса
import statistics     # для среднего значения порции (statistics.fmean)

import websockets     # WebSocket-клиент


async def run(uri: str, n_chunks: int) -> None:
    print(f"Подключение к {uri} ...")
    async with websockets.connect(uri) as ws:        # открываем соединение с сервисом
        for i in range(n_chunks):                    # принимаем ровно n_chunks порций и завершаемся
            msg = await ws.recv()                    # ждём очередное сообщение от сервера
            data = json.loads(msg)                   # разбираем JSON {"t0":..., "fs":..., "ppg":[...]}
            ppg = data["ppg"]                         # сами отсчёты порции
            print(f"chunk {i:02d}: t0={data['t0']:6.2f} c   fs={data['fs']:.0f} Гц   "
                  f"n={len(ppg):4d}   среднее={statistics.fmean(ppg):.3f}   "
                  f"мин={min(ppg):.3f}   макс={max(ppg):.3f}")   # краткая статистика порции — проверка, что данные осмысленные
    print("Готово.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", nargs="?", default="ws://localhost:8765")      # адрес сервиса, по умолчанию локальный
    ap.add_argument("--n", type=int, default=5, help="сколько порций принять")
    args = ap.parse_args()
    asyncio.run(run(args.uri, args.n))     # запускаем асинхронную функцию run() из обычного синхронного кода
