# Docker-образ сетевого сервиса источника сигнала CardioWatch.
# Собирает изолированный контейнер, имитирующий смарт-часы: генерирует
# (или воспроизводит из записи PhysioNet) сигнал ФПГ и рассылает его по
# сети через WebSocket всем подключившимся клиентам.

FROM python:3.11-slim

WORKDIR /app

# Сначала только зависимости — отдельный слой кэша Docker,
# ускоряет повторную сборку при изменении только кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cardiowatch ./cardiowatch

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
