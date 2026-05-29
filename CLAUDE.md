# CLAUDE.md — Telegram Userbot Mirror

## Контекст проекта

Кастомный заказ для клиента (@MrWerther, Rehy Solutions).  
Юзербот на Telethon копирует все сообщения из одного топика одной группы в топик другой группы — от своего имени (без форварда, автор скрыт). Клиент редактирует сообщения руками в Telegram.

---

## Стек

- **Python 3.13**
- **Telethon v1** — MTProto, юзербот (чтение истории + отправка)  
  > ⚠️ Репозиторий Telethon v1 переведён в read-only 21 февраля 2026. Работает, но обновлений не будет. Альтернатива — Pyrogram.
- **PyYAML** — конфиг
- **asyncio** — асинхронное ядро
- **Деплой:** VPS, systemd или docker-compose

---

## Обязательные credentials

| Что | Где взять | Переменная |
|---|---|---|
| `api_id` | my.telegram.org → App configuration | `TG_API_ID` |
| `api_hash` | my.telegram.org → App configuration | `TG_API_HASH` |
| Номер телефона юзербота | Выделенный аккаунт клиента | `TG_PHONE` |

> ⚠️ Юзербот — это **обычный аккаунт**, не бот. Сессия хранится в файле `session/userbot.session`.  
> Первый запуск требует интерактивной авторизации (ввод кода из Telegram).  
> Рекомендуется **отдельный номер телефона**, не личный аккаунт клиента.

---

## Структура проекта

```
tg-mirror-bot/
├── CLAUDE.md
├── README.md
├── .env                    # api_id, api_hash, phone (не в git)
├── .env.example
├── config.yaml             # зеркала: source → dest
├── requirements.txt
├── main.py                 # точка входа
├── core.py                 # сессия, подключение, диспетчер
├── session/
│   └── userbot.session     # Telethon сессия (не в git)
└── modules/
    ├── __init__.py
    └── mirror.py           # логика копирования топиков
```

---

## Конфигурация (config.yaml)

```yaml
mirrors:
  - name: "Пример зеркала"
    source_chat: -100123456789      # chat_id группы-источника
    source_topic: 42                # message_thread_id топика-источника
    dest_chat: -100987654321        # chat_id группы-назначения
    dest_topic: 17                  # message_thread_id топика-назначения
    dump_history: true              # копировать историю при старте
```

> Добавить новое зеркало = новый элемент списка. Перезапустить процесс.

---

## Архитектура

### core.py
- Инициализация `TelegramClient` с сессией
- Загрузка модулей из `modules/`
- Запуск event loop

### modules/mirror.py
Два режима:

**1. Дамп истории** (`dump_history: true`)  
При старте итерирует `iter_messages(source_chat, reply_to=source_topic)` от старых к новым и отправляет в dest.

**2. Онлайн-зеркало**  
`@client.on(events.NewMessage(chats=source_chat))` — фильтрует по `message.reply_to.reply_to_top_id == source_topic`, копирует в dest.

### Отправка сообщений
Используется `client.send_message` / `client.send_file` с `reply_to=dest_topic` — **не forward**, сообщение идёт от имени юзербота.

---

## Поддерживаемые типы контента

| Тип | Метод Telethon |
|---|---|
| Текст | `send_message` |
| Фото | `send_file(file=message.media)` |
| Видео | `send_file(file=message.media)` |
| Аудио / голосовое | `send_file(file=message.media)` |
| Видеосообщение (кружок) | `send_file(file=message.media)` |
| Документ / файл | `send_file(file=message.media)` |
| Медиагруппа (альбом) | `send_file(files=[...])` |

### Передача медиа без скачивания

Telethon позволяет передавать `message.media` напрямую в `send_file` — файл переиспользуется на серверах Telegram, ничего не скачивается на VPS:

```python
await client.send_file(
    dest_chat,
    file=message.media,   # передаём хэндл, не скачиваем
    caption=message.text,
    reply_to=dest_topic
)
```

**Важно — file reference expiry:**
Файловые ссылки Telegram имеют срок жизни.
- **Онлайн-зеркало (новые сообщения)** → `message.media` напрямую, всегда свежий ✅
- **Исторический дамп (старые сообщения)** → для недавней истории работает, для старых возможна ошибка `FileReferenceExpiredError` → fallback: `download_media` + `send_file`

---

## Flood control

```python
import asyncio
# Между сообщениями при дампе истории:
await asyncio.sleep(0.3)
# При ошибке FloodWaitError:
await asyncio.sleep(e.seconds + 1)
```

Всегда оборачивать отправку в `try/except FloodWaitError`.

---

## Как клиент редактирует сообщения

Юзербот отправляет сообщения **от своего аккаунта**.  
Клиент заходит в этот аккаунт → находит сообщение в группе B → редактирует как обычно через интерфейс Telegram.  
Никаких команд, никакого маппинга — не нужно.

> ✅ Это намеренное упрощение архитектуры. Не усложнять без запроса клиента.

---

## Права юзербота в группах

| Сценарий | Что нужно |
|---|---|
| Группа A (источник) | Быть участником, видеть топик |
| Группа B (назначение, другая группа) | **Быть администратором** с правом отправки сообщений |
| Топик A → Топик B внутри **одной группы** | Быть участником/админом одной группы — `chat_id` одинаковый, просто разные `reply_to` |

> Зеркалирование внутри одной группы (разные топики) работает штатно — это та же операция, что и между двумя группами.

---

## .env.example

```env
TG_API_ID=12345678
TG_API_HASH=abcdef1234567890abcdef1234567890
TG_PHONE=+79001234567
```

---

## Запуск

```bash
# Первый запуск (интерактивная авторизация)
python main.py

# После авторизации — фоновый запуск
# systemd или:
nohup python main.py &
```

---

## .gitignore (обязательно)

```
.env
session/
*.session
*.session-journal
```

---

## Переиспользование (следующие проекты)

`core.py` — универсальный, не трогать.  
Новая фича для нового клиента → новый файл в `modules/`.  
Новая пара топиков → новая запись в `config.yaml`.

---

## Известные ограничения Telegram

- Бот **не может** читать историю группы через Bot API → поэтому юзербот
- `forward_messages` показывает оригинального автора → поэтому `send_message`/`send_file`
- Топик в MTProto = `reply_to_top_id` сообщения-заголовка топика
- При дампе большой истории: Telegram может временно ограничить аккаунт, sleep обязателен