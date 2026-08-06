# Telegram-бот: polling, вебхук, мини-апп

Минимальный, но полноценный бот в `tgbot/`. Сделан так, чтобы с ним можно было
работать из изолированного окружения без публичного IP — и при этом без
переписывания разворачивался в прод на вебхуке.

## Из чего состоит

| Файл | Зачем |
|---|---|
| `tgbot/handlers.py` | Вся логика: `dispatch(update) -> [(метод Bot API, payload)]`. Чистая функция — без сети и состояния |
| `tgbot/runner.py` | Исполняет действия из `dispatch`, гасит ошибки отдельных вызовов |
| `tgbot/api.py` | Тонкий асинхронный клиент Bot API |
| `tgbot/polling.py` | Long polling + журнал апдейтов в `.runtime/updates.jsonl` |
| `tgbot/server.py` | FastAPI: вебхук, бэкенд мини-аппа, раздача его статики |
| `tgbot/security.py` | Секрет вебхука и проверка подписи `initData` |
| `tgbot/miniapp/index.html` | Мини-апп одним файлом |
| `scripts/tg_admin.py` | Разовые настройки и ручные проверки |

Ключевое решение: **polling и вебхук используют один и тот же `dispatch()`**.
Смена режима не меняет поведение бота и не требует переписывать тесты.

## Запуск

```bash
cp .env.example .env          # заполнить TELEGRAM_BOT_TOKEN
python -m scripts.tg_admin info     # проверить токен и текущий вебхук
python -m scripts.tg_admin setup    # меню команд + кнопка мини-аппа
python -m tgbot polling             # режим по умолчанию
```

`polling` при старте сам снимает вебхук: `getUpdates` и вебхук взаимоисключающи,
иначе Telegram отвечает `409 Conflict`.

## Команды

`/start` — приветствие, inline-кнопки и закреплённая кнопка мини-аппа ·
`/ping` — `pong` · `/whoami` — `chat_id` и `user_id` · `/echo <текст>` ·
`/app` — открыть мини-апп · `/help`.
Любой другой текст бот повторяет, нажатия inline-кнопок обрабатывает через
`callback_query`.

## Мини-апп

Одна статическая страница: читает `Telegram.WebApp`, подхватывает тему клиента,
показывает пользователя из `initDataUnsafe` и умеет две вещи.

**Вернуть данные в чат** — `WebApp.sendData(...)`. Прилетает боту как
`message.web_app_data`, доверять можно: пейлоад проходит через серверы Telegram.
Работает только если мини-апп открыт **кнопкой обычной клавиатуры** (`/start`
такую закрепляет) — из inline-кнопки и из кнопки меню `sendData` недоступен.

**Проверить подпись на сервере** — POST `initData` на `/api/miniapp/verify`.
Нужен, когда мини-апп ходит в бэкенд: там `initData` — просто строка из
браузера, и без проверки HMAC ей верить нельзя. Бэкенд задаётся параметром
`?api=https://<host>` в URL мини-аппа.

Требования Telegram: URL обязательно `https`, самоподписанные сертификаты не
принимаются. Подойдёт любая статика — GitHub Pages, S3, тот же `serve`.

## Вебхук

```bash
# TELEGRAM_WEBHOOK_BASE_URL=https://bot.example.com
# TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 24)
python -m tgbot serve &
python -m scripts.tg_admin setup
python -m scripts.tg_admin webhook-set
python -m scripts.tg_admin webhook-delete   # вернуться на polling
```

Что важно:

- Telegram ходит только на порты **443, 80, 88, 8443** и только по HTTPS с
  валидным сертификатом. TLS обычно терминирует реверс-прокси перед `serve`.
- **Секрет обязателен.** Telegram возвращает его в заголовке
  `X-Telegram-Bot-Api-Secret-Token`; без сверки любой, кто узнал URL, шлёт боту
  поддельные апдейты. `check_webhook_secret` сравнивает в постоянном времени.
- Эндпоинт всегда отвечает `200`: на любой не-2xx Telegram ретраит апдейт.

Проверить вебхук локально, не выставляя сервис наружу:

```bash
curl -X POST localhost:8081/telegram/webhook \
  -H 'Content-Type: application/json' \
  -H "X-Telegram-Bot-Api-Secret-Token: $TELEGRAM_WEBHOOK_SECRET" \
  -d '{"update_id":1,"message":{"message_id":1,"chat":{"id":<CHAT_ID>,"type":"private"},"from":{"id":<CHAT_ID>,"first_name":"T"},"text":"/ping"}}'
```

Бот пришлёт `pong` в реальный чат — то есть проверяется весь путь, кроме
последней мили «Telegram → наш HTTP».

## Как выбрать режим

| | polling | вебхук |
|---|---|---|
| Публичный HTTPS | не нужен | обязателен |
| Задержка | до секунды | мгновенно |
| Масштабирование | один процесс на бота | сколько угодно реплик |
| Где уместен | разработка, изолированные окружения, CI | прод |

В окружении без входящего трафика (контейнер за прокси, dev-машина без белого
IP) вебхук физически не поднять: туннели вроде `cloudflared` требуют исходящих
портов вроде 7844, которые обычно закрыты. Поэтому режим по умолчанию —
polling, а вебхук включается на деплое одной командой.

## Тесты

```bash
pytest tests/test_tgbot_handlers.py tests/test_tgbot_security.py tests/test_tgbot_webhook.py
```

Сети не требуют: `dispatch` чистый, а в тестах вебхука вместо Bot API
подставлен рекордер вызовов.
