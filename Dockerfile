# Docker-образ устройства CardioWatch (Лабораторная работа № 3).
# Контейнер — самостоятельное "устройство": генерирует (или воспроизводит
# из записи PhysioNet) сигнал ФПГ, прогоняет его через буфер, фильтр,
# извлечение признаков ВСР и нейросетевой классификатор риска, и рассылает
# по сети через WebSocket уже готовый результат всем подключившимся клиентам
# (Flutter-приложению).

FROM python:3.11-slim

WORKDIR /app

# Сначала только зависимости — отдельный слой кэша Docker,
# ускоряет повторную сборку при изменении только кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cardiowatch ./cardiowatch
COPY train_model.py .

# Обучение воспроизводимо (все генераторы случайных чисел — с фиксированным
# seed=42, см. train_model.py), поэтому модель обучается прямо при сборке
# образа, а не поставляется отдельным бинарным файлом в репозитории.
RUN python3 train_model.py

EXPOSE 8765

# Значения по умолчанию — синтетический источник, ЧСС 70, 100 Гц,
# порции по 1 с в реальном темпе. Переопределяются через docker run -e
# или docker-compose.yml (см. пример подключения записи PhysioNet там же).
ENV SOURCE_TYPE=synthetic \
    HEART_RATE=70 \
    FS=100 \
    CHUNK_SECONDS=1.0 \
    REALTIME=1 \
    HOST=0.0.0.0 \
    PORT=8765

CMD ["python", "-m", "cardiowatch.signal_service"]
