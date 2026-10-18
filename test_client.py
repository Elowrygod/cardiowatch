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
import argparse       # разбор аргументов командной строки (адрес сервиса, число сообщений)
import asyncio        # клиент тоже асинхронный — та же модель, что и у сервиса
import json           # разбор JSON-сообщений от сервиса

import websockets     # WebSocket-клиент


async def run(uri: str, n_messages: int) -> None:
    """
    С Лабораторной работы № 3 сервис шлёт не сырые отсчёты ФПГ, а уже
    готовый результат по каждому окну анализа (см. docstring модуля
    cardiowatch/signal_service.py): ЧСС, признаки ВСР и решение нейросети.
    """
    print(f"Подключение к {uri} ...")
    async with websockets.connect(uri) as ws:        # открываем соединение с устройством
        for i in range(n_messages):                  # принимаем ровно n_messages окон и завершаемся
            msg = await ws.recv()                    # ждём очередной результат от сервера
            data = json.loads(msg)                   # разбираем JSON (см. формат в docstring signal_service.py)
            risk = "РИСК" if data["risk_class"] else "норма"
            print(f"окно {i:02d}: t={data['t']:6.1f} c   ЧСС={data['hr']:5.1f} "
                  f"(сглаж.={data['hr_smoothed']:5.1f})   SDNN={data['sdnn']:5.1f}   "
                  f"RMSSD={data['rmssd']:5.1f}   pNN50={data['pnn50']:5.1f}   "
                  f"риск={data['risk_prob']:.2f} [{risk}]")   # вся строка — проверка, что пайплайн целиком работает
    print("Готово.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", nargs="?", default="ws://localhost:8765")      # адрес сервиса, по умолчанию локальный
    ap.add_argument("--n", type=int, default=5, help="сколько окон принять")
    args = ap.parse_args()
    asyncio.run(run(args.uri, args.n))     # запускаем асинхронную функцию run() из обычного синхронного кода
