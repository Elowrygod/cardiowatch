# CardioWatch — Лабораторная работа № 3

Развёртывание программной части  на аппаратной платформе:
контейнер Docker исполняет роль самостоятельного
устройства — сам генерирует сигнал ФПГ, сам его обрабатывает и сам
классифицирует риск нейросетью, а наружу отдаёт уже готовый результат
по сети. БД поднимается рядом вторым сервисом.

## Структура репозитория

```
cardiowatch/
  __init__.py
  signal_source.py    — источники данных: SignalSource, PhysioNetSource,
                         SyntheticPpgSource (математическая модель ФПГ)
  signal_service.py   — "устройство" целиком: генерация + буфер + окна +
                         признаки + нейросеть, WebSocket-поток результатов
  buffer.py            — RingBuffer, Resampler, WindowSegmenter
  preprocessing.py     — simple_ema, adaptive_ema (KAMA), bandpass_filter
  features.py           — детекция пиков, ЧСС/SDNN/RMSSD/pNN50 (ЛР № 3)
  model.py               — RiskNet (MLP 4-8-1, PyTorch) + RiskClassifier (ЛР № 3)
train_model.py            — обучение модели, запускается при сборке образа
demo.py                    — демонстрационный скрипт для отчёта по ЛР № 2
test_client.py              — тестовый клиент: печатает поток результатов устройства
db/init.sql                  — схема PostgreSQL (ER-диаграмма из ЛР № 1)
Dockerfile, docker-compose.yml
```

## Запуск Docker 

```bash
docker compose up --build
```

Поднимутся два сервиса:

- `device` — устройство на `ws://localhost:8765`, обучает модель прямо
  при сборке образа (воспроизводимо: все генераторы случайных чисел —
  с фиксированным `seed=42`) и сразу начинает стримить результат;
- `db` — PostgreSQL на `localhost:5432` (пользователь/пароль/БД —
  `cardiowatch`/`cardiowatch`/`cardiowatch`), схема создаётся автоматически
  из `db/init.sql` при первом запуске.

Проверить поток результатов устройства (без Flutter, из корня проекта,
с установленными зависимостями):

```bash
python test_client.py ws://localhost:8765 --n 8
```

Ожидаемый вывод — по одной строке на каждое окно анализа (8 с, шаг 2 с):

```
окно 00: t=   0.0 c   ЧСС= 76.1 (сглаж.= 76.1)   SDNN= 31.8   RMSSD= 54.3   pNN50= 50.0   риск=0.20 [норма]
окно 01: t=   2.0 c   ЧСС= 76.7 (сглаж.= 76.3)   SDNN= 30.7   RMSSD= 49.5   pNN50= 37.5   риск=0.22 [норма]
...
```

## Обучение модели отдельно, без докера

```bash
pip install -r requirements.txt
python3 train_model.py
```

Печатает метрики на отложенной выборке (accuracy, precision, recall, F1,
ROC-AUC) и сохраняет веса в `model.pt`.

## Подключение Flutter-приложения

- Живой поток результатов: WebSocket `ws://<host>:8765` — формат сообщения
  описан в docstring `cardiowatch/signal_service.py`.
- История сеансов: прямое подключение к `db` по протоколу PostgreSQL
  (пакет `postgres` для Dart), шифрование — на стороне приложения
  (пакет `cryptography`) перед записью в таблицу `raw_signals`/`users`.

