# 🤖 Bidzaar Tender Bot

Telegram-бот для автоматизации тендерной работы на площадке **Bidzaar**.
Позволяет искать закупки, получать карточку тендера и скачивать всю
документацию прямо в чат — без ручного блуждания по сайту.

---

## 📌 Зачем этот бот

Ручной поиск и разбор тендеров съедает часы: открыть площадку, найти
нужную закупку, проверить, та ли это процедура, скачать 5–10 файлов,
разобраться в ТЗ. Бот делает это за секунды:

- 🔍 **Поиск закупок** по ключевым словам (ОКВЭД, товар, заказчик)
- 📄 **Карточка тендера** — название, ссылка, список файлов
- 📥 **Скачивание документации** — все вложения тендера в один клик
- ⚡ **Без рутины** — вы сразу видите суть закупки, а не тонете в интерфейсе

---

## 🚀 Возможности

| Функция | Описание |
|---|---|
| `search_bidzaar(query, limit)` | Поиск закупок по запросу, возвращает список с id, названием и ссылкой |
| `parse_bidzaar(url)` | Разбор карточки тендера: название, ссылка, прикреплённые файлы |
| `download_bidzaar_files(files, folder)` | Скачивание всех файлов тендера в локальную папку |
| `download_bidzaar_file(file_id, folder, filename)` | Скачивание одного файла по его id |

---

## 🧠 Как это работает

```
Telegram → Бот → Bidzaar API → Карточка тендера / Файлы → Telegram
```

1. Пользователь отправляет поисковый запрос или ссылку на тендер.
2. Бот обращается к публичному API Bidzaar (`/api/process/...`).
3. Извлекает `procedureId`, название, список файлов.
4. Скачивает документацию и отправляет её пользователю.
5. Пользователь принимает решение по тендеру, не открывая сайт.

---

## 🛠️ Технологии

- **Python 3.10+**
- **requests** — работа с HTTP API Bidzaar
- **re** — извлечение UUID закупки из ссылки
- **os**, **time** — файловая система и throttling запросов
- **Telegram Bot API** (aiogram / pyTelegramBotAPI / python-telegram-bot — на выбор)

---

## 📦 Установка

```bash
git clone https://github.com/your-username/bidzaar-tender-bot.git
cd bidzaar-tender-bot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt`:
```
requests>=2.31.0
aiogram>=3.0.0
```

---

## ⚙️ Настройка

Создайте файл `.env` в корне проекта:

```env
BOT_TOKEN=123456:ABC-DEF...
DOWNLOAD_DIR=downloads
```

- `BOT_TOKEN` — токен бота, полученный у [@BotFather](https://t.me/BotFather)
- `DOWNLOAD_DIR` — папка для скачивания документов тендеров

---

## ▶️ Запуск

```bash
python bot.py
```

После запуска найдите бота в Telegram и отправьте команду `/start`.

---

## 💬 Примеры использования

### Поиск тендеров

```
Пользователь: поставка щебня
Бот:
1. Поставка щебня фракции 5-20 — https://bidzaar.com/app/process/light/...
2. Щебень гранитный, 2000 т — https://bidzaar.com/app/process/light/...
3. ...
```

### Разбор тендера по ссылке

```
Пользователь: https://bidzaar.com/app/process/light/abc12345-...
Бот:
📄 Поставка щебня фракции 5-20
🔗 https://bidzaar.com/app/process/light/...
📎 Файлов: 4
Скачиваю документацию...
✅ Готово: ТЗ.pdf, Смета.xlsx, Договор.docx, Форма_КП.docx
```

---

## 🧩 Структура проекта

```
bidzaar-tender-bot/
├── bot.py            # логика Telegram-бота (хендлеры команд)
├── parser.py         # работа с Bidzaar API (этот файл)
├── downloads/        # скачанные документы тендеров
├── .env              # токен и настройки
├── requirements.txt
└── README.md
```

---

## 🔌 Основные функции `parser.py`

### `search_bidzaar(query, limit=5)`

Ищет закупки на Bidzaar по ключевому слову.

```python
from parser import search_bidzaar

results = search_bidzaar('щебень', limit=5)
for r in results:
    print(r['title'], r['url'])
```

Возвращает список словарей:
```python
[
    {'id': 'uuid', 'title': 'Поставка щебня', 'url': 'https://bidzaar.com/...'},
    ...
]
```

---

### `parse_bidzaar(url)`

Разбирает карточку тендера по ссылке или id.

```python
from parser import parse_bidzaar

info = parse_bidzaar('https://bidzaar.com/app/process/light/abc12345-...')
print(info['title'])
print(info['files'])
```

Возвращает:
```python
{
    'id': 'uuid',
    'title': 'Поставка щебня',
    'url': 'https://bidzaar.com/app/process/light/...',
    'files': [ {...}, {...} ]
}
```

Поддерживает два формата ссылок:
- прямая на процедуру (`/app/process/light/...`)
- агрегатор (`/api/process/aggregator/tenders/...`) — бот сам найдёт `procedureId`

---

### `download_bidzaar_files(files, folder)`

Скачивает все файлы тендера в папку.

```python
from parser import parse_bidzaar, download_bidzaar_files

info = parse_bidzaar(url)
paths = download_bidzaar_files(info['files'], 'downloads/tender_123')
print(paths)
```

Между загрузками — пауза `1 сек`, чтобы не получить бан от площадки.

---

## ⚠️ Важно

- Бот использует **публичные API Bidzaar**. Не злоупотребляйте частотой
  запросов — в коде уже стоит `time.sleep(1)` между скачиваниями.
- Некоторые файлы могут требовать авторизации. Если площадка начнёт
  отдавать `403` — потребуется добавить cookie/токен в `HEADERS`.
- Уважайте правила площадки и законодательство о персональных данных.

---

## 🗺️ Roadmap

- [ ] Уведомления о новых тендерах по сохранённым фильтрам
- [ ] Интеграция с ИИ для краткого резюме ТЗ (что реально требуется заказчику)
- [ ] Автоматический скоринг: «стоит ли участвовать»
- [ ] Экспорт тендеров в Excel
- [ ] Поддержка других площадок (zakupki.gov.ru, B2B-Center, ЭТП ГПБ)
- [ ] Мультипользовательский режим с личными фильтрами

---

## 🤝 Вклад

Pull request'ы приветствуются. Если нашли баг или хотите добавить
площадку — открывайте issue.

---

## 📄 Лицензия

MIT

---

## 💬 Контакты

Автор: Алексей
Telegram: @NN_KRATOS