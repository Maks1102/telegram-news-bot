# 📰 Telegram News Bot

Асинхронный Telegram-бот, который раз в неделю собирает новости из RSS-фидов, отсеивает дубликаты через SQLite и присылает в чат сводку из 10 заголовков со ссылками.

**Стек:** Python 3.11+ · aiogram 3 · APScheduler 3 · aiohttp · feedparser · aiosqlite · pydantic-settings

## Возможности

- 💻 **Только русскоязычная IT-повестка**: Habr, vc.ru, 3DNews, CNews, «Код.ру», «Хакер», «Компьютерра»
- 🗓 Еженедельная рассылка по настраиваемому расписанию (день недели, время, таймзона)
- 🔁 Дедупликация двумя уровнями:
  - нормализация URL (срезаются `utm_*` и трекинг-параметры, `www.`, trailing slash) → SHA-256;
  - нормализация заголовка (регистр, пунктуация, пробелы) → SHA-256, отсекает одну и ту же новость из разных фидов
- 🗄 SQLite-хранилище отправленных статей + автоочистка старых записей (`RETENTION_DAYS`)
- ⚡ Конкурентная загрузка всех фидов через `asyncio.gather`; упавший фид не ломает остальные
- 📝 Команды: `/start`, `/help`, `/digest` (сводка по запросу), `/stats`
- 📄 Логирование в консоль и ротируемый файл `logs/bot.log`
- ⚙️ Вся конфигурация через `.env` с валидацией (pydantic-settings)

## Структура проекта

```
telegram-news-bot/
├── main.py                  # точка входа
├── app/
│   ├── config.py            # настройки из .env + валидация
│   ├── db.py                # SQLite: дедупликация, статистика, очистка
│   ├── rss.py               # асинхронная загрузка и разбор RSS
│   ├── digest.py            # сборка, форматирование и отправка сводки
│   ├── scheduler.py         # APScheduler: еженедельный cron-джоб
│   ├── handlers.py          # команды /start /help /digest /stats
│   └── logging_config.py    # консоль + RotatingFileHandler
├── requirements.txt
├── .env.example
└── .gitignore
```

## Установка

### Windows (PowerShell)

```powershell
cd F:\Projects\MyProjects\telegram-news-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

### Linux / macOS

```bash
cd telegram-news-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

## Настройка `.env`

1. **`BOT_TOKEN`** — создайте бота у [@BotFather](https://t.me/BotFather) командой `/newbot` и вставьте токен.
2. **`CHAT_ID`** — куда слать сводку:
   - для личного чата: запустите бота, отправьте `/start` — он покажет ID чата;
   - для группы: добавьте бота в группу и используйте `@getidsbot` (ID будет отрицательным, например `-1001234567890`);
   - для канала: добавьте бота администратором и укажите ID канала.
3. **`RSS_FEEDS`** — список русскоязычных IT-фидов через запятую: Habr, vc.ru, 3DNews, CNews, «Код.ру», «Хакер», «Компьютерра». Можно заменить на свои.
4. **`SCHEDULE_DAY` / `SCHEDULE_TIME` / `TIMEZONE`** — когда слать. По умолчанию стоит **21:00 `Europe/Moscow`** (для теста) — после проверки верните `09:00`.

Полный список переменных с описанием — в [`.env.example`](.env.example).

## Запуск

```bash
python main.py
```

Ожидаемые логи при старте:

```
2026-11-16 09:00:00 | INFO     | root | Запуск Telegram News Bot…
2026-11-16 09:00:00 | INFO     | root | Планировщик запущен: каждый mon в 09:00 (Europe/Moscow)
```

Проверить работу без ожидания понедельника: отправьте боту команду `/digest`.

## Как это работает

1. **APScheduler** (`AsyncIOScheduler` + `CronTrigger`) раз в неделю вызывает `weekly_digest_job`.
2. Все фиды скачиваются конкурентно (`aiohttp`), разбираются через `feedparser`.
3. Из статей считаются `url_hash` и `title_hash`; те, что уже есть в SQLite, отбрасываются. Внутри пачки тоже дедуплицируется.
4. Берутся свежие 10 (по дате публикации), форматируются в HTML с экранированием и отправляются в `CHAT_ID` (с разбивкой на части, если текст длиннее лимита Telegram в 4096 символов).
5. Отправленные статьи сохраняются в `articles` — они больше не попадут в следующие сводки.

## Деплой (Linux, systemd)

`/etc/systemd/system/telegram-news-bot.service`:

```ini
[Unit]
Description=Telegram News Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/telegram-news-bot
ExecStart=/opt/telegram-news-bot/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now telegram-news-bot
journalctl -u telegram-news-bot -f
```

## Дедупликация: детали

| Уровень | Ключ | Что отсекает |
|---|---|---|
| URL | SHA-256 нормализованного URL | Повторы одной статьи из одного фида; трекинг-параметры не мешают распознать дубль |
| Заголовок | SHA-256 нормализованного заголовка | Одну новость из разных фидов (URL разные, заголовок — почти тот же) |
| Пачка | те же хэши внутри текущего сбора | Дубли между фидами за один запуск, пока они не попали в БД |

## Частые проблемы

- **`ValidationError: bot_token ...`** — не создан/не заполнен `.env` или токен скопирован с лишними пробелами.
- **Бот молчит в `/digest`, но работает в личке** — для группы `CHAT_ID` должен быть отрицательным; проверьте командой `/start` внутри группы.
- **`feedparser` ругается на фид** — бот залогирует предупреждение `Фид ... пропущен` и продолжит с остальными.
- **Хотите другую частоту** — `CronTrigger` в `app/scheduler.py` легко меняется на ежедневную/часовую, либо правьте `SCHEDULE_*`.
- **Хочу проверить прямо сейчас, не дожидаясь 21:00** — отправьте боту `/digest`: он соберёт и пришлёт сводку немедленно (и заодно очистит источники от тех новостей, что попадут в БД).
