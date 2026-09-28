import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / 'tenders.db'


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
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
        '''
    )
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS sent_tenders (
            user_id INTEGER NOT NULL,
            tender_id TEXT NOT NULL,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, tender_id)
        )
        '''
    )
    cur.execute(
        '''
        CREATE TABLE IF NOT EXISTS search_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            command TEXT NOT NULL,
            query TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    conn.close()


def save_tender(row: dict) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO tenders (tender_id, title, price, url, law, category)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(tender_id) DO UPDATE SET
            title = excluded.title,
            url = excluded.url,
            category = excluded.category
        ''',
        (
            row['id'],
            row.get('title') or '',
            row.get('price') or '',
            row.get('url') or '',
            row.get('law') or 'коммерция',
            row.get('category') or 'разное',
        ),
    )
    conn.commit()
    conn.close()


def mark_sent(user_id: int, tender_id: str) -> bool:
    """True — этому пользователю карточку ещё не показывали."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT OR IGNORE INTO sent_tenders (user_id, tender_id)
        VALUES (?, ?)
        ''',
        (user_id, tender_id),
    )
    inserted = cur.rowcount == 1
    conn.commit()
    conn.close()
    return inserted


def save_and_should_show(user_id: int, row: dict) -> bool:
    save_tender(row)
    return mark_sent(user_id, row['id'])


def log_search(user_id: int, command: str, query: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT INTO search_logs (user_id, command, query)
        VALUES (?, ?, ?)
        ''',
        (user_id, command, query),
    )
    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = 20) -> list[dict]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT command, query, created_at
        FROM search_logs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        ''',
        (user_id, limit),
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def list_tenders(limit: int = 20) -> list[tuple]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT tender_id, title, price
        FROM tenders
        ORDER BY id DESC
        LIMIT ?
        ''',
        (limit,),
    )
    rows = list(cur.fetchall())
    conn.close()
    return rows


def add_demo_tender() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        '''
        INSERT OR IGNORE INTO tenders
            (tender_id, title, price, url, law, category)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (
            'TEST-001',
            'Тестовая закупка: клининг офиса',
            '150000',
            'https://example.com',
            '44',
            'клининг',
        ),
    )
    conn.commit()
    conn.close()
