-- Схема базы данных CardioWatch — ровно та же, что спроектирована как
-- ER-диаграмма в отчёте по ЛР № 1 (раздел 3.7, рисунок 3.18) и
-- описана в таблице 3.6 того же отчёта. Выполняется автоматически
-- при первом запуске контейнера db (переменная окружения Postgres
-- POSTGRES_* создаёт саму базу, этот файл — только таблицы внутри неё).
--
-- Шифрование: raw_signals.data_enc и users.full_name_enc хранятся как
-- bytea — зашифрованные данные пишет сама Flutter-часть (AES-256-GCM,
-- пакет cryptography для Dart), база не видит открытого текста и не
-- занимается шифрованием сама (не используется pg_crypto) — ключ не
-- должен попадать на сервер БД.

CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    full_name_enc BYTEA,                  -- ФИО, зашифровано на стороне приложения
    birth_year    INT,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users(user_id),
    started_at   TIMESTAMP NOT NULL DEFAULT now(),
    duration_s   INT NOT NULL,
    fs_hz        INT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_signals (
    session_id INT PRIMARY KEY REFERENCES sessions(session_id),
    data_enc   BYTEA NOT NULL,            -- зашифрованные отсчёты ФПГ (AES-256-GCM)
    nonce      BYTEA NOT NULL,            -- одноразовое число шифра, 12 байт
    tag        BYTEA NOT NULL             -- тег аутентичности GCM, 16 байт
);

CREATE TABLE IF NOT EXISTS features (
    session_id INT PRIMARY KEY REFERENCES sessions(session_id),
    hr         REAL,
    sdnn       REAL,
    rmssd      REAL,
    pnn50      REAL
);

CREATE TABLE IF NOT EXISTS predictions (
    session_id    INT PRIMARY KEY REFERENCES sessions(session_id),
    risk_class    SMALLINT,               -- 0 - норма, 1 - повышенный риск
    probability   REAL,
    model_version VARCHAR(32)             -- например, "risknet-mlp-4-8-1-v1"
);
