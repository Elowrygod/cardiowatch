# Создание и инициализация репозитория (п. 4 задания)

Проверить, что Git установлен:

```bash
git --version
```

Если не установлен — для Windows скачать с https://git-scm.com/download/win,
для Linux — `sudo apt install git`.

## Инициализация локального репозитория

```bash
cd cardiowatch-project
git init
git add .
git commit -m "Initial commit: сигнальный источник, буфер, предобработка"
```

## Публикация на GitHub

1. Создать пустой репозиторий на https://github.com/new (без README, без .gitignore —
   они уже есть локально).
2. Привязать удалённый репозиторий и отправить код:

```bash
git remote -v
git remote add origin https://github.com/<ваш-логин>/cardiowatch.git
git branch -M main
git push -u origin main
```

## Дальнейшая работа с репозиторием

```bash
git clone https://github.com/<ваш-логин>/cardiowatch.git   # клонирование на другом ПК
git pull                                                     # получить изменения
git checkout -b feature/kama-tuning                          # новая ветка
git checkout main                                             # переключение на ветку
git add .
git commit -m "Добавлена адаптивная EMA (KAMA)"
git push
```

## Рекомендуемый порядок коммитов для этой лабораторной работы

1. `Initial commit` — структура проекта, README, .gitignore
2. `Add signal sources: PhysioNet + synthetic PPG model`
3. `Add ring buffer and window segmenter`
4. `Add preprocessing: simple EMA, adaptive EMA (KAMA), bandpass filter`
5. `Add demo script and report figures`
