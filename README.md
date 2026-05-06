# YouStatic Bot

Telegram-бот для отслеживания статистики YouTube-каналов.

Бот позволяет добавлять YouTube-каналы по ссылке, `@handle`, `UC...` ID или названию, автоматически определяет `channel_id`, сохраняет каналы в SQLite и показывает текущую статистику, динамику роста и аналитические показатели.

## Возможности

- Добавление YouTube-канала по:
  - `https://www.youtube.com/@handle`
  - `https://www.youtube.com/channel/UC...`
  - `@handle`
  - названию канала
  - ссылке на видео
- Автоматическое определение `UC...` channel ID через YouTube Data API v3.
- Хранение каналов пользователей в SQLite.
- Отображение списка каналов с названиями, а не техническими `UC...` ID.
- Удаление одного канала или очистка всех каналов пользователя.
- Получение текущей статистики:
  - подписчики;
  - общие просмотры;
  - количество видео.
- Сохранение исторических снапшотов статистики.
- Расчёт роста за 1, 7 и 30 дней:
  - абсолютный прирост;
  - средний дневной рост;
  - процентный рост;
  - ускорение или замедление роста относительно предыдущего периода.
- Автоматический сбор снапшотов по расписанию через APScheduler.
- Поддержка прокси для подключения к Telegram API.
- Асинхронная архитектура на `aiogram`.

## Стек

- Python
- aiogram 3
- SQLite
- aiosqlite
- aiohttp
- pandas
- APScheduler
- python-dotenv
- YouTube Data API v3

## Структура проекта

```text
.
├── bot.py                  # основной файл Telegram-бота
├── db.py                   # работа с SQLite
├── youtube_api.py          # работа с YouTube Data API
├── analytics.py            # расчёт метрик роста через pandas
├── snapshot_scheduler.py   # автоматический сбор снапшотов
├── bot.db                  # локальная SQLite-БД, не коммитить
├── .env                    # переменные окружения, не коммитить
├── .gitignore
└── README.md
```

## Требования

Рекомендуется использовать Python 3.11 или 3.12.

Также нужны:

- Telegram Bot Token от BotFather;
- YouTube API key для YouTube Data API v3;
- установленный Git;
- виртуальное окружение Python.

## Установка

### 1. Клонировать репозиторий

```bash
git clone <URL_ТВОЕГО_РЕПОЗИТОРИЯ>
cd <ИМЯ_ПАПКИ_ПРОЕКТА>
```

### 2. Создать виртуальное окружение

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Установить зависимости

```bash
pip install -U pip
pip install aiogram python-dotenv aiosqlite aiohttp aiohttp-socks apscheduler pandas
```

Или, если в проекте есть `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Переменные окружения

Создай файл `.env` в корне проекта:

```env
BOT_TOKEN=your_telegram_bot_token
YOUTUBE_API_KEY=your_youtube_api_key
SNAPSHOT_INTERVAL_HOURS=6
TELEGRAM_PROXY=
```

### Описание переменных

| Переменная | Назначение |
|---|---|
| `BOT_TOKEN` | токен Telegram-бота от BotFather |
| `YOUTUBE_API_KEY` | ключ YouTube Data API v3 |
| `SNAPSHOT_INTERVAL_HOURS` | интервал автоматического сбора статистики в часах |
| `TELEGRAM_PROXY` | прокси для Telegram API, можно оставить пустым |

## Прокси

По умолчанию прокси отключён:

```env
TELEGRAM_PROXY=
```

Пример SOCKS5-прокси:

```env
TELEGRAM_PROXY=socks5://127.0.0.1:10808
```

Пример HTTP-прокси:

```env
TELEGRAM_PROXY=http://127.0.0.1:10809
```

Если появляется ошибка вида:

```text
Couldn't connect to proxy 127.0.0.1:10001
```

значит на указанном порту прокси не запущен или указан неправильный порт. В таком случае нужно либо отключить `TELEGRAM_PROXY`, либо указать реальный локальный порт прокси-клиента.

## Запуск

Windows PowerShell:

```powershell
python .\bot.py
```

Linux / macOS:

```bash
python bot.py
```

После запуска в консоли должно появиться примерно такое сообщение:

```text
INFO:aiogram.dispatcher:Start polling
INFO:aiogram.dispatcher:Run polling for bot ...
```

## Команды и кнопки бота

### Основные команды

| Команда | Описание |
|---|---|
| `/start` | запуск бота и главное меню |
| `/help` | справка |
| `/stats` | текущая статистика по каналам |
| `/growth` | аналитика роста по каналам |

### Кнопки

| Кнопка | Описание |
|---|---|
| `➕ Добавить канал` | добавить YouTube-канал |
| `📊 Мои каналы` | показать список добавленных каналов |
| `📈 Статистика` | показать текущую статистику |
| `📉 Рост` | показать динамику роста |
| `➖ Удалить канал` | удалить канал из списка |
| `ℹ️ Помощь` | показать справку |
| `🧹 Очистить мои каналы` | удалить все каналы пользователя |

## Добавление канала

Бот принимает разные форматы:

```text
https://www.youtube.com/@GoogleDevelopers
@GoogleDevelopers
https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw
Google Developers
https://youtu.be/<video_id>
```

После ввода бот:

1. определяет `channel_id`;
2. получает название канала;
3. сохраняет канал в SQLite;
4. показывает канал в разделе `📊 Мои каналы` уже по названию.

## Текущая статистика

Раздел `📈 Статистика` показывает:

- название канала;
- YouTube channel ID;
- количество подписчиков;
- общее количество просмотров;
- количество видео.

Пример вывода:

```text
📺 Google Developers
🆔 UC_x5XG1OV2P6uZZ5FSM9Ttw
👥 Подписчики: 2 000 000
👁 Просмотры: 250 000 000
🎞 Видео: 6 500
```

## Метрики роста

Раздел `📉 Рост` считает динамику по историческим снапшотам.

Поддерживаются периоды:

- 1 день;
- 7 дней;
- 30 дней.

Для каждого периода считаются:

- прирост подписчиков;
- прирост просмотров;
- прирост количества видео;
- средний дневной рост;
- процентный рост.

Также бот сравнивает последние 7 дней с предыдущими 7 днями и определяет:

- ускорение роста;
- замедление роста;
- отсутствие изменений.

## Снапшоты статистики

Снапшот — это сохранённое состояние канала в определённый момент времени:

```text
channel_id
subscribers
views
videos
timestamp
```

Снапшоты нужны для расчёта роста. Без истории невозможно узнать, насколько канал вырос за 7 или 30 дней.

## Автоматический сбор статистики

Автоматический сбор работает через APScheduler.

При запуске бот:

1. инициализирует SQLite;
2. запускает планировщик;
3. собирает первый снапшот;
4. продолжает сбор по расписанию.

Интервал задаётся в `.env`:

```env
SNAPSHOT_INTERVAL_HOURS=6
```

Например:

| Значение | Поведение |
|---|---|
| `1` | каждый час |
| `6` | каждые 6 часов |
| `24` | раз в сутки |

## База данных

Проект использует SQLite.

Основные таблицы:

### `users`

Хранит Telegram-пользователей.

| Поле | Описание |
|---|---|
| `id` | Telegram user ID |
| `created_at` | дата добавления |

### `channels`

Хранит YouTube-каналы.

| Поле | Описание |
|---|---|
| `id` | внутренний ID |
| `channel_key` | YouTube `UC...` ID |
| `title` | название канала |
| `created_at` | дата добавления |

### `user_channels`

Связующая таблица между пользователями и каналами.

| Поле | Описание |
|---|---|
| `user_id` | Telegram user ID |
| `channel_id` | внутренний ID канала |
| `created_at` | дата добавления |

### `snapshots`

Хранит исторические данные статистики.

| Поле | Описание |
|---|---|
| `id` | ID снапшота |
| `channel_id` | внутренний ID канала |
| `subscribers` | количество подписчиков |
| `views` | общее количество просмотров |
| `videos` | количество видео |
| `ts` | дата и время снапшота |

## `.gitignore`

Рекомендуемый `.gitignore`:

```gitignore
.env
bot.db
.venv/
__pycache__/
*.pyc
*.log
.idea/
.vscode/
```

Особенно важно не коммитить:

- `.env`;
- `bot.db`;
- `.venv`.

## Безопасность

Не публикуй в GitHub:

- Telegram bot token;
- YouTube API key;
- локальную базу данных;
- прокси-логины и пароли.

Для YouTube API key рекомендуется включить ограничения:

- разрешить использование только YouTube Data API v3;
- при деплое на сервер ограничить ключ по IP-адресу сервера.

## Частые проблемы

### PowerShell не запускает `bot.py`

Ошибка:

```text
bot.py : Имя "bot.py" не распознано...
```

Решение:

```powershell
python .\bot.py
```

или:

```powershell
.\.venv\Scripts\python.exe .\bot.py
```

### `BOT_TOKEN not found`

Проверь, что файл `.env` находится в корне проекта и содержит:

```env
BOT_TOKEN=your_telegram_bot_token
```

Также проверь, что в коде вызывается:

```python
load_dotenv()
```

### `YOUTUBE_API_KEY not found`

Проверь `.env`:

```env
YOUTUBE_API_KEY=your_youtube_api_key
```

Также убедись, что YouTube Data API v3 включён в Google Cloud Console.

### `TelegramNetworkError: Request timeout error`

Обычно это проблема сети, Telegram API, VPN, прокси или firewall.

Проверка в PowerShell:

```powershell
Test-NetConnection api.telegram.org -Port 443
```

Если соединение нестабильное, можно использовать `TELEGRAM_PROXY`.

### `Couldn't connect to proxy`

Ошибка означает, что бот пытается подключиться к локальному прокси, но он не запущен или указан неправильный порт.

Проверь порт:

```powershell
Test-NetConnection 127.0.0.1 -Port 10808
```

Или отключи прокси:

```env
TELEGRAM_PROXY=
```

### `ValueError: no active connection`

Обычно возникает, если в `db.py` код использует `db.execute(...)` вне блока:

```python
async with aiosqlite.connect(DB_PATH) as db:
```

Нужно проверить отступы в `init_db()`.

### Недостаточно данных для роста

Рост за 7 или 30 дней появится только после накопления истории.

Например, для роста за 7 дней нужен хотя бы один снапшот примерно неделю назад и текущий снапшот.

## Деплой на Ubuntu

Telegram-бот в режиме polling не требует открытых портов.

Минимальный запуск на сервере:

```bash
git clone <URL_РЕПОЗИТОРИЯ>
cd <ИМЯ_ПРОЕКТА>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### Пример systemd service

Создай файл:

```bash
sudo nano /etc/systemd/system/youstatic-bot.service
```

Пример содержимого:

```ini
[Unit]
Description=YouStatic Telegram Bot
After=network.target

[Service]
WorkingDirectory=/opt/youstatic-bot
ExecStart=/opt/youstatic-bot/.venv/bin/python /opt/youstatic-bot/bot.py
Restart=always
RestartSec=5
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable youstatic-bot
sudo systemctl start youstatic-bot
```

Проверка логов:

```bash
sudo journalctl -u youstatic-bot -f
```

## Git workflow

Создать новую ветку:

```bash
git switch -c feature/youtube-growth-analytics
```

Добавить изменения:

```bash
git add .
git commit -m "Add YouTube growth analytics"
```

Запушить ветку:

```bash
git push -u origin feature/youtube-growth-analytics
```

Обновить локальный репозиторий:

```bash
git pull
```

## Ограничения

- Поиск канала по названию может быть неточным, потому что YouTube может вернуть похожий канал.
- Для точного добавления лучше использовать ссылку на канал или `@handle`.
- Обычный YouTube Data API даёт публичные данные.
- Метрики вроде CTR, удержания аудитории, источников трафика и watch time требуют YouTube Analytics API и доступа владельца канала через OAuth.
- SQLite подходит для MVP и небольшого проекта. Для продакшена лучше рассмотреть PostgreSQL.

## Roadmap

Возможные улучшения:

- графики роста подписчиков и просмотров;
- экспорт отчётов в CSV;
- недельные и месячные отчёты;
- уведомления о резком росте или падении;
- сравнение нескольких каналов;
- рейтинг каналов по приросту;
- прогноз роста;
- веб-дашборд для менеджеров;
- переход с SQLite на PostgreSQL;
- Docker-деплой.

## Лицензия

Проект можно распространять под лицензией MIT.

Перед публикацией добавь файл `LICENSE`, если планируешь сделать репозиторий открытым.
