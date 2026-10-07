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
import argparse
import asyncio
import json
import statistics

import websockets


async def run(uri: str, n_chunks: int) -> None:
    print(f"Подключение к {uri} ...")
    async with websockets.connect(uri) as ws:
        for i in range(n_chunks):
            msg = await ws.recv()
            data = json.loads(msg)
            ppg = data["ppg"]
            print(f"chunk {i:02d}: t0={data['t0']:6.2f} c   fs={data['fs']:.0f} Гц   "
                  f"n={len(ppg):4d}   среднее={statistics.fmean(ppg):.3f}   "
                  f"мин={min(ppg):.3f}   макс={max(ppg):.3f}")
    print("Готово.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", nargs="?", default="ws://localhost:8765")
    ap.add_argument("--n", type=int, default=5, help="сколько порций принять")
    args = ap.parse_args()
    asyncio.run(run(args.uri, args.n))
