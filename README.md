# CardioWatch — Лабораторная работа № 2

Программная реализация блока приёма и предварительной обработки данных
имитатора смарт-часов для обнаружения тахикардии.

Продолжение проекта из Лабораторной работы № 1 (проектирование средствами
CASE-инструментов). В этой лабораторной работе реализован рабочий код:
приём сигнала, буферизация, дискретизация и три алгоритма предварительной
обработки.

## Структура репозитория

```
cardiowatch/
  __init__.py
  signal_source.py    — источники данных: SignalSource, PhysioNetSource,
                         SyntheticPpgSource (математическая модель ФПГ)
  signal_service.py   — сетевой сервис-обёртка (WebSocket) для Docker:
                         рассылает сигнал подключившимся клиентам
  buffer.py            — RingBuffer, Resampler, WindowSegmenter
  preprocessing.py     — simple_ema, adaptive_ema (KAMA), bandpass_filter
demo.py                 — демонстрационный скрипт, строит все графики отчёта
test_client.py          — тестовый клиент для сервиса источника сигнала
plots/                  — сгенерированные графики (PNG)
Dockerfile
docker-compose.yml
requirements.txt
```

## Установка и запуск

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python demo.py
```

Графики появятся в папке `plots/`.

## Источники данных

По умолчанию используется `SyntheticPpgSource` — математическая модель
пульсовой волны из отчёта по Лабораторной работе № 1 (не требует интернета
и внешних файлов).

Для работы с реальными записями PhysioNet:

1. Скачайте записи датасета Pulse Transit Time PPG Dataset 1.1.0:
   ```bash
   wget -r -N -c -np https://physionet.org/files/pulse-transit-time-ppg/1.1.0/
   ```
2. Установите пакет `wfdb` (уже включён в requirements.txt).
3. Используйте `PhysioNetSource(record_path="путь/к/записи", channel="pleth_1")`.

## Источник сигнала как отдельный сетевой сервис (Docker)

Источник данных вынесен в отдельный контейнер, имитирующий физически
отделённые от сервера обработки смарт-часы: контейнер генерирует сигнал
и рассылает его по сети через WebSocket всем подключившимся клиентам —
формат сообщения и переменные окружения описаны в docstring файла
`cardiowatch/signal_service.py`.

### Запуск через Docker Compose (рекомендуется)

```bash
docker compose up --build
```

Сервис поднимется на `ws://localhost:8765`. Проверить его работу можно
тестовым клиентом (без Docker, из корня проекта, с установленными
зависимостями):

```bash
python test_client.py ws://localhost:8765 --n 5
```

Ожидаемый вывод — построчно порции сигнала с их статистикой:

```
chunk 00: t0=  0.00 c   fs=100 Гц   n= 100   среднее=0.420 ...
chunk 01: t0=  1.00 c   fs=100 Гц   n= 100   среднее=0.374 ...
...
```

### Запуск через обычный Docker (без Compose)

```bash
docker build -t cardiowatch-signal-source .
docker run --rm -p 8765:8765 \
    -e SOURCE_TYPE=synthetic -e HEART_RATE=90 -e FS=100 \
    cardiowatch-signal-source
```

### Использование реальной записи PhysioNet внутри контейнера

```bash
docker run --rm -p 8765:8765 \
    -v $(pwd)/data:/app/data:ro \
    -e SOURCE_TYPE=physionet -e RECORD_PATH=/app/data/s1_sit -e CHANNEL=pleth_1 \
    cardiowatch-signal-source
```

(предварительно скачайте запись, см. раздел «Источники данных» ниже).

## Реализованные алгоритмы предобработки

| Функция | Алгоритм | Где применять |
|---|---|---|
| `simple_ema` | Экспоненциальное скользящее среднее | Быстрое сглаживание, база для сравнения |
| `adaptive_ema` | Адаптивная EMA (Kaufman's Adaptive Moving Average) | Сглаживание ряда ЧСС: подавляет шум в покое, быстро реагирует на реальный тренд |
| `bandpass_filter` | Полосовой фильтр Баттерворта, 0,5–8 Гц | Очистка сырой формы волны перед поиском пиков |

Подробное обоснование выбора и графики — в отчёте по Лабораторной работе № 2.
