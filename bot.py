import asyncio
import os
import zipfile
import sqlite3
import re
from docx import Document
from analyze import analyze_tender
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from parser import parse_bidzaar, download_bidzaar_files, search_bidzaar
from doc2txt import extract_text
from pypdf import PdfReader
from openpyxl import load_workbook
from pathlib import Path

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command



# читает секрет из .env
load_dotenv()
token = os.getenv('BOT_TOKEN')
bot = Bot(token=token)
dp = Dispatcher()

# папка docs рядом с этим файлом (на другом компьютере путь сам правильный)
DOCS_DIR = Path(__file__).resolve().parent / 'docs'
LAST_TENDER = {}
WATCH = {}
REFRESH_SECONDS = 15 * 60
CARD_PAUSE = 1.5

def read_tender_file(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == '.docx':
            word = Document(path)
            return '\n'.join(p.text for p in word.paragraphs if p.text.strip())
        if suffix == '.doc':
            return extract_text(str(path)) or ''
        if suffix == '.pdf':
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                chunk = page.extract_text() or ''
                if chunk.strip():
                    pages.append(chunk)
            return '\n'.join(pages)
        if suffix == '.xlsx':
            book = load_workbook(str(path), data_only=True)
            lines = []
            for sheet in book.worksheets:
                lines.append(f'лист: {sheet.title}')
                for row in sheet.iter_rows(values_only=True):
                    cells = [str(cell) for cell in row if cell is not None]
                    if cells:
                        lines.append('\t'.join(cells))
            return '\n'.join(lines)
        if suffix == '.zip':
            out_dir = path.parent / (path.stem + '_unzip')
            out_dir.mkdir(exist_ok=True)
            with zipfile.ZipFile(path) as archive:
                archive.extractall(out_dir)
            parts = []
            for inner in out_dir.rglob('*'):
                if not inner.is_file():
                    continue
                if inner.suffix.lower() == '.zip':
                    continue
                text = read_tender_file(inner)
                if text.strip():
                    parts.append(f'--- {inner.name} ---\n{text}')
            return '\n'.join(parts)
        return ''
    except Exception as error:
        return f'[не прочитал {path.name}: {error}]'

def folder_name(data: dict) -> str:
    title = data.get('title') or 'tender'
    short = re.sub(r'[^\wа-яА-ЯёЁ\s-]', '', title)
    short = '_'.join(short.split())[:40] or 'tender'
    category = data.get('category') or 'разное'
    return f"{category}__{short}__{data['id'][:8]}"


def card_keyboard(tender_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Скачать файлы', callback_data=f'dl:{tender_id}'),
        InlineKeyboardButton(text='Анализ', callback_data=f'an:{tender_id}'),
    ]])


def save_tender(row: dict, mark_sent: bool = False) -> bool:
    conn = sqlite3.connect('tenders.db')
    cur = conn.cursor()
    cur.execute('SELECT sent FROM tenders WHERE tender_id = ?', (row['id'],))
    found = cur.fetchone()
    if found is None:
        cur.execute(
            '''INSERT INTO tenders
               (tender_id, title, price, url, law, category, sent)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (row['id'], row.get('title') or '', '', row.get('url') or '',
             'коммерция', row.get('category') or 'клининг', 1 if mark_sent else 0),
        )
        conn.commit()
        conn.close()
        return True
    already = bool(found[0])
    if mark_sent and not already:
        cur.execute('UPDATE tenders SET sent = 1 WHERE tender_id = ?', (row['id'],))
        conn.commit()
    conn.close()
    return not already


def remember_folder(user_id: int, tender_id: str, folder: str) -> None:
    LAST_TENDER[user_id] = folder
    LAST_TENDER[f'{user_id}:{tender_id}'] = folder


def folder_for(user_id: int, tender_id=None):
    if tender_id:
        return LAST_TENDER.get(f'{user_id}:{tender_id}') or LAST_TENDER.get(user_id)
    return LAST_TENDER.get(user_id)


async def send_card(chat_id: int, row: dict) -> None:
    await bot.send_message(
        chat_id,
        f'{row["title"]}\n{row["url"]}',
        reply_markup=card_keyboard(row['id']),
    )


async def send_new_cards(chat_id: int, user_id: int, rows: list) -> int:
    shown = 0
    for row in rows:
        if not save_tender(row, mark_sent=True):
            continue
        await send_card(chat_id, row)
        shown += 1
        await asyncio.sleep(CARD_PAUSE)
    return shown


def fetch_and_save_files(url: str, user_id: int):
    data = parse_bidzaar(url)
    folder = folder_name(data)
    folder_path = DOCS_DIR / folder
    saved = []
    if data['files']:
        saved = download_bidzaar_files(data['files'], str(folder_path))
    remember_folder(user_id, data['id'], folder)
    return data, saved, folder_path

async def run_analyze(message_or_cb, folder_path: Path) -> None:
    send = message_or_cb.answer
    if not folder_path.is_dir():
        await send(f'Папки нет: {folder_path.name}')
        return

    pieces = []
    skipped = []
    for path in folder_path.iterdir():
        if not path.is_file() or path.name == 'analiz.txt':
            continue
        text = read_tender_file(path)
        if text.strip() and not text.startswith('[не прочитал'):
            pieces.append(f'--- {path.name} ---\n{text}')
        else:
            skipped.append(path.name)

    if not pieces:
        await send(
            'В папке нет текста для анализа. '
            f'Пропущены: {", ".join(skipped) or "ничего"}'
        )
        return

    await send('Читаю документы, жду Яндекс…')
    report = analyze_tender('\n'.join(pieces))
    analiz_path = folder_path / 'analiz.txt'
    analiz_path.write_text(report or 'Пустой анализ', encoding='utf-8')
    await message_or_cb.answer_document(
        FSInputFile(analiz_path),
        caption='Анализ закупки',
    )

def stop_watch(user_id: int) -> None:
    job = WATCH.pop(user_id, None)
    if job and job.get('task'):
        job['task'].cancel()


async def watch_loop(user_id: int, chat_id: int, query: str) -> None:
    try:
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            try:
                rows = search_bidzaar(query)
            except ConnectionError:
                await bot.send_message(chat_id, 'Обновление: Bidzaar не ответил.')
                continue
            shown = await send_new_cards(chat_id, user_id, rows)
            if shown:
                await bot.send_message(chat_id, f'Обновление по «{query}»: новых {shown}.')
    except asyncio.CancelledError:
        return


def start_watch(user_id: int, chat_id: int, query: str) -> None:
    stop_watch(user_id)
    WATCH[user_id] = {
        'query': query,
        'task': asyncio.create_task(watch_loop(user_id, chat_id, query)),
    }

# /start — проверка, что бот жив
@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer('Бот мониторинга закупок запущен')


# /demo — тестовая закупка в базу и показ всех строк
@dp.message(Command('demo'))
async def demo(message: types.Message):
    conn = sqlite3.connect('tenders.db')
    cur = conn.cursor()
    cur.execute(
        '''INSERT OR IGNORE INTO tenders
           (tender_id, title, price, url, law, category)
           VALUES (?, ?, ?, ?, ?, ?)''',
        ('TEST-001', 'Тестовая закупка: клининг офиса', '150000',
         'https://example.com', '44', 'клининг')
    )
    conn.commit()
    cur.execute('SELECT tender_id, title, price FROM tenders')
    rows = cur.fetchall()
    conn.close()

    lines = []
    for row in rows:
        lines.append(f'{row[0]} | {row[1]} | {row[2]}')
    await message.answer('\n'.join(lines))


# /parse ссылка — карточка Bidzaar, запись в базу, список документов
@dp.message(Command('parse'))
async def cmd_parse(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer('Кинь ссылку: /parse https://bidzaar.com/...')
        return
    url = parts[1]
    try:
        data = parse_bidzaar(url)
    except (ValueError, ConnectionError) as error:
        await message.answer(str(error))
        return
    conn = sqlite3.connect('tenders.db')
    cur = conn.cursor()
    cur.execute(
        '''INSERT OR IGNORE INTO tenders
           (tender_id, title, price, url, law, category)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (data['id'], data['title'], '', data['url'], 'коммерция', 'клининг')
    )
    conn.commit()
    conn.close()
    lines = [data['title'], data['url'], '', 'Документы:']
    if data['files']:
        for i, f in enumerate(data['files'], start=1):
            name = f.get('name') or 'без имени'
            ext = f.get('extension') or ''
            if ext:
                lines.append(f'{i}. {name}.{ext}')
            else:
                lines.append(f'{i}. {name}')
    else:
        lines.append('в карточке файлов нет')
    
    title = data['title']
    short = re.sub(r'[^\wа-яА-ЯёЁ\s-]', '', title)
    short = '_'.join(short.split())[:40] or 'tender'
    folder = f"{data.get('category', 'разное')}__{short}__{data['id'][:8]}"
    LAST_TENDER[message.from_user.id] = folder
    if data['files']:
        try:
            saved = download_bidzaar_files(
                data['files'],
                os.path.join('docs', folder),
            )
            lines.append('')
            lines.append(f'Скачал {len(saved)} файл(ов) в docs/{folder}')
        except ConnectionError as error:
            lines.append('')
            lines.append(f'Не скачал: {error}')
    text = '\n'.join(lines)
    await message.answer(text)


@dp.message(Command('fresh'))
async def fresh_cmd(message: types.Message):
    query = message.text.replace('/fresh', '', 1).strip()
    if not query:
        await message.answer('Напиши слово после команды.\nПример: /fresh клининг')
        return
    await message.answer(f'Ищу на Bidzaar: {query}')
    try:
        rows = search_bidzaar(query)
    except ConnectionError:
        await message.answer('Bidzaar не ответил. Попробуй ещё раз.')
        return
    if not rows:
        await message.answer('Ничего не нашёл по этому запросу.')
        return
    shown = await send_new_cards(message.chat.id, message.from_user.id, rows)
    if shown == 0:
        await message.answer('Эти закупки уже были в базе, новых карточек нет.')
    start_watch(message.from_user.id, message.chat.id, query)
    await message.answer(
        f'Смотрю «{query}» каждые 15 минут. Новое слово — новый /fresh. Стоп — /stop'
    )

@dp.message(Command('stop'))
async def cmd_stop(message: types.Message):
    stop_watch(message.from_user.id)
    await message.answer('Обновление остановлено.')
    
@dp.message(Command('analyze'))
async def cmd_analyze(message: types.Message):
    folder = LAST_TENDER.get(message.from_user.id)
    if not folder:
        await message.answer('Сначала /parse со ссылкой, потом /analyze')
        return
    folder_path = DOCS_DIR / folder
    if not folder_path.is_dir():
        await message.answer(f'Папки нет: {folder_path}')
        return

    pieces = []
    skipped = []
    for path in folder_path.iterdir():
        if not path.is_file() or path.name == 'analiz.txt':
            continue
        text = read_tender_file(path)
        if text.strip():
            pieces.append(f'--- {path.name} ---\n{text}')
        else:
            skipped.append(path.name)

    if not pieces:
        await message.answer(
            'В папке нет текста из .docx. '
            f'Пропущены: {", ".join(skipped) or "ничего"}'
        )
        return

    body = '\n'.join(pieces)
    await message.answer('Читаю документы, жду Яндекс…')
    report = analyze_tender(body)
    analiz_path = folder_path / 'analiz.txt'
    analiz_path.write_text(report or 'Пустой анализ', encoding='utf-8')
    await message.answer_document(
        FSInputFile(analiz_path),
        caption='Анализ закупки'
    )

@dp.callback_query(F.data.startswith('dl:'))
async def cb_download(callback: types.CallbackQuery):
    tender_id = callback.data.split(':', 1)[1]
    url = f'https://bidzaar.com/app/process/light/{tender_id}'
    try:
        await callback.answer('Качаю файлы…')
    except Exception:
        pass
    try:
        data, saved, folder_path = fetch_and_save_files(
            url,
            callback.from_user.id,
        )
    except (ValueError, ConnectionError) as error:
        await callback.message.answer(str(error))
        return
    if not data['files']:
        await callback.message.answer('В карточке файлов нет')
        return
    await callback.message.answer(
        f'Скачал {len(saved)} файл(ов) в {folder_path}'
    )


@dp.callback_query(F.data.startswith('an:'))
async def cb_analyze(callback: types.CallbackQuery):
    tender_id = callback.data.split(':', 1)[1]
    url = f'https://bidzaar.com/app/process/light/{tender_id}'
    try:
        await callback.answer('Готовлю анализ…')
    except Exception:
        pass
    folder = folder_for(callback.from_user.id, tender_id)
    folder_path = DOCS_DIR / folder if folder else None
    if folder_path is None or not folder_path.is_dir():
        try:
            _data, _saved, folder_path = fetch_and_save_files(
                url,
                callback.from_user.id,
            )
        except (ValueError, ConnectionError) as error:
            await callback.message.answer(str(error))
            return
    await run_analyze(callback.message, folder_path)


# человек кинул файл в чат → кладём в docs/<его telegram id>/
@dp.message(F.document)
async def save_doc(message: types.Message):
    doc = message.document
    if not doc.file_name:
        await message.answer('У файла нет имени, не сохраняю')
        return
    user_id = message.from_user.id
    tender_folder = LAST_TENDER.get(user_id, 'без_закупки')
    user_dir = DOCS_DIR / str(user_id) / tender_folder
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / doc.file_name
    await bot.download(doc, destination=dest)

    text = read_tender_file(dest)
    reply = [f'Принял: {doc.file_name}', f'Папка: {user_dir}']
    if not text.strip():
        reply.append('Текст не вытащил (пустой файл или формат пока не читаем)')
        await message.answer('\n'.join(reply))
        return

    await message.answer('Читаю документ, жду Яндекс…')
    report = analyze_tender(text)
    analiz_path = user_dir / 'analiz.txt'
    analiz_path.write_text(report or 'Пустой анализ', encoding='utf-8')
    await message.answer_document(
        FSInputFile(analiz_path),
        caption='Анализ закупки'
    )
    await message.answer('\n'.join(reply))

# создать таблицу tenders, если её ещё нет
def init_db():
    conn = sqlite3.connect('tenders.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tender_id TEXT UNIQUE,
            title TEXT,
            price TEXT,
            url TEXT,
            law TEXT,
            category TEXT,
            sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


# сначала база, потом бот слушает Telegram
async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
        