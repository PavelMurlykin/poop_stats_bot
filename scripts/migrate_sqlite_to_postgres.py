import sqlite3
from datetime import datetime, date, timezone
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import SQLITE_PATH
from db.connection import get_connection
from db.schema import init_db


MEAL_TYPE_BY_ID = {
    1: 'breakfast',
    2: 'lunch',
    3: 'dinner',
    4: 'snack',
}


def _now_dt() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _sqlite_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(cur: sqlite3.Cursor, table_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return cur.fetchone() is not None


def _has_column(cur: sqlite3.Cursor, table_name: str, column_name: str) -> bool:
    cur.execute(f'PRAGMA table_info({table_name})')
    return any(row['name'] == column_name for row in cur.fetchall())


def _sync_sequence(pg_cur, table_name: str) -> None:
    pg_cur.execute(f'SELECT COALESCE(MAX(id), 0) AS max_id FROM {table_name}')
    max_id = int(pg_cur.fetchone()['max_id'])
    if max_id > 0:
        pg_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), %s, true)",
            (max_id,),
        )
    else:
        pg_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), 1, false)"
        )


def _parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    if not text:
        raise ValueError('Empty date value cannot be migrated')
    text = text.split('T')[0].split(' ')[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    for fmt in ('%d.%m.%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Invalid date format for migration: {text}')


def _parse_timestamp(value) -> datetime:
    if not value:
        return _now_dt()
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


def _parse_timestamptz(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def migrate(sqlite_path: str) -> None:
    src_path = Path(sqlite_path)
    if not src_path.exists():
        raise FileNotFoundError(f'SQLite database not found: {src_path}')

    init_db()

    src = _sqlite_connect(str(src_path))
    dst = get_connection()
    logs = []
    try:
        src_cur = src.cursor()
        dst_cur = dst.cursor()

        src_cur.execute(
            'SELECT user_id, breakfast_time, lunch_time, dinner_time, toilet_time FROM users'
        )
        users = src_cur.fetchall()
        for r in users:
            dst_cur.execute(
                '''
                INSERT INTO users(user_id, breakfast_time, lunch_time, dinner_time, toilet_time)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE
                SET breakfast_time = EXCLUDED.breakfast_time,
                    lunch_time = EXCLUDED.lunch_time,
                    dinner_time = EXCLUDED.dinner_time,
                    toilet_time = EXCLUDED.toilet_time
                ''',
                (
                    r['user_id'],
                    r['breakfast_time'],
                    r['lunch_time'],
                    r['dinner_time'],
                    r['toilet_time'],
                ),
            )

        meals = []
        if _table_exists(src_cur, 'meals'):
            if _has_column(src_cur, 'meals', 'meal_type'):
                src_cur.execute(
                    'SELECT id, user_id, date, meal_type, description, created_at, updated_at FROM meals'
                )
                meals = src_cur.fetchall()
            elif _has_column(src_cur, 'meals', 'meal_type_id'):
                src_cur.execute(
                    'SELECT id, user_id, date, meal_type_id, description, created_at, updated_at FROM meals'
                )
                rows = src_cur.fetchall()
                for row in rows:
                    meals.append(
                        {
                            'id': row['id'],
                            'user_id': row['user_id'],
                            'date': row['date'],
                            'meal_type': MEAL_TYPE_BY_ID.get(
                                int(row['meal_type_id']), 'snack'
                            ),
                            'description': row['description'],
                            'created_at': row['created_at'],
                            'updated_at': row['updated_at'],
                        }
                    )

        for r in meals:
            created_at = _parse_timestamp(r['created_at'])
            updated_at = _parse_timestamp(r['updated_at']) if r['updated_at'] else created_at
            dst_cur.execute(
                '''
                INSERT INTO meals(id, user_id, date, meal_type, description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    date = EXCLUDED.date,
                    meal_type = EXCLUDED.meal_type,
                    description = EXCLUDED.description,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                ''',
                (
                    r['id'],
                    r['user_id'],
                    _parse_date(r['date']),
                    r['meal_type'],
                    r['description'],
                    created_at,
                    updated_at,
                ),
            )

        src_cur.execute(
            'SELECT id, user_id, date, name, dosage, created_at, updated_at FROM medicines'
        )
        medicines = src_cur.fetchall()
        for r in medicines:
            created_at = _parse_timestamp(r['created_at'])
            updated_at = _parse_timestamp(r['updated_at']) if r['updated_at'] else created_at
            dst_cur.execute(
                '''
                INSERT INTO medicines(id, user_id, date, name, dosage, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    date = EXCLUDED.date,
                    name = EXCLUDED.name,
                    dosage = EXCLUDED.dosage,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                ''',
                (
                    r['id'],
                    r['user_id'],
                    _parse_date(r['date']),
                    r['name'],
                    r['dosage'],
                    created_at,
                    updated_at,
                ),
            )

        src_cur.execute(
            'SELECT id, user_id, date, quality, created_at, updated_at FROM stools'
        )
        stools = src_cur.fetchall()
        for r in stools:
            created_at = _parse_timestamp(r['created_at'])
            updated_at = _parse_timestamp(r['updated_at']) if r['updated_at'] else created_at
            dst_cur.execute(
                '''
                INSERT INTO stools(id, user_id, date, quality, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    date = EXCLUDED.date,
                    quality = EXCLUDED.quality,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                ''',
                (
                    r['id'],
                    r['user_id'],
                    _parse_date(r['date']),
                    r['quality'],
                    created_at,
                    updated_at,
                ),
            )

        src_cur.execute(
            'SELECT id, user_id, date, description, created_at, updated_at FROM feelings'
        )
        feelings = src_cur.fetchall()
        for r in feelings:
            created_at = _parse_timestamp(r['created_at'])
            updated_at = _parse_timestamp(r['updated_at']) if r['updated_at'] else created_at
            dst_cur.execute(
                '''
                INSERT INTO feelings(id, user_id, date, description, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    date = EXCLUDED.date,
                    description = EXCLUDED.description,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                ''',
                (
                    r['id'],
                    r['user_id'],
                    _parse_date(r['date']),
                    r['description'],
                    created_at,
                    updated_at,
                ),
            )

        if _table_exists(src_cur, 'notifications_log'):
            src_cur.execute(
                'SELECT id, user_id, type, date, sent_at FROM notifications_log'
            )
            logs = src_cur.fetchall()
            for r in logs:
                sent_at = _parse_timestamptz(r['sent_at'])
                dst_cur.execute(
                    '''
                    INSERT INTO notifications_log(id, user_id, type, date, sent_at)
                    VALUES (%s, %s, %s, %s, COALESCE(%s, NOW()))
                    ON CONFLICT(id) DO UPDATE
                    SET user_id = EXCLUDED.user_id,
                        type = EXCLUDED.type,
                        date = EXCLUDED.date,
                        sent_at = EXCLUDED.sent_at
                    ''',
                    (r['id'], r['user_id'], r['type'], _parse_date(r['date']), sent_at),
                )

        for table in ('meals', 'medicines', 'stools', 'feelings', 'notifications_log'):
            _sync_sequence(dst_cur, table)

        dst.commit()
        print(f'Users: {len(users)}')
        print(f'Meals: {len(meals)}')
        print(f'Medicines: {len(medicines)}')
        print(f'Stools: {len(stools)}')
        print(f'Feelings: {len(feelings)}')
        if logs:
            print(f'Notifications: {len(logs)}')
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == '__main__':
    migrate(SQLITE_PATH)
