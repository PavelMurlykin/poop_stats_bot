from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db.connection import with_db


def _utc_now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def _parse_date(date_iso: str) -> date:
    return date.fromisoformat(date_iso)


@with_db
def register_user(cur, user_id: int) -> None:
    """Регистрация нового пользователя."""
    cur.execute(
        'INSERT INTO users(user_id) VALUES (%s) '
        'ON CONFLICT(user_id) DO NOTHING',
        (user_id,),
    )


@with_db
def get_user_times(cur, user_id: int) -> Optional[Tuple[str, str, str, str]]:
    """Получение раписания пользователя."""
    cur.execute(
        'SELECT breakfast_time, lunch_time, dinner_time, toilet_time '
        'FROM users WHERE user_id = %s',
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return (
        row['breakfast_time'],
        row['lunch_time'],
        row['dinner_time'],
        row['toilet_time'])


@with_db
def update_user_time(cur, user_id: int, slot: str, time_str: str) -> bool:
    """Изменение раписания пользователя."""
    col_map = {'breakfast': 'breakfast_time', 'lunch': 'lunch_time',
               'dinner': 'dinner_time', 'toilet': 'toilet_time'}
    col = col_map.get(slot)
    if not col:
        return False
    cur.execute(f'UPDATE users SET {col} = %s WHERE user_id = %s',
                (time_str, user_id))
    return cur.rowcount > 0


@with_db
def get_all_users(cur) -> List[Tuple[int, str, str, str, str]]:
    """Получение списка пользователей."""
    cur.execute(
        'SELECT user_id, breakfast_time, lunch_time, dinner_time, '
        'toilet_time FROM users'
    )
    return [(r['user_id'], r['breakfast_time'], r['lunch_time'],
             r['dinner_time'], r['toilet_time']) for r in cur.fetchall()]


@with_db
def is_notification_sent(
        cur,
        user_id: int,
        n_type: str,
        date_iso: str) -> bool:
    """Is notification sent."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'SELECT 1 FROM notifications_log '
        'WHERE user_id=%s AND type=%s AND date=%s',
        (user_id,
         n_type,
         date_val))
    return cur.fetchone() is not None


@with_db
def mark_notification_sent(
        cur,
        user_id: int,
        n_type: str,
        date_iso: str) -> None:
    """Mark notification sent."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'INSERT INTO notifications_log(user_id, type, date) '
        'VALUES (%s, %s, %s) '
        'ON CONFLICT(user_id, type, date) DO NOTHING',
        (user_id, n_type, date_val),
    )


@with_db
def upsert_meal(
        cur,
        user_id: int,
        date_iso: str,
        meal_type: str,
        description: str) -> None:
    """Upsert meal."""
    now = _utc_now()
    date_val = _parse_date(date_iso)
    if meal_type in ('breakfast', 'lunch', 'dinner'):
        cur.execute(
            'SELECT id FROM meals '
            'WHERE user_id=%s AND date=%s AND meal_type=%s',
            (user_id,
             date_val,
             meal_type))
        row = cur.fetchone()
        if row:
            cur.execute(
                'UPDATE meals SET description=%s, updated_at=%s '
                'WHERE id=%s AND user_id=%s',
                (description,
                 now,
                 row['id'],
                    user_id))
            return
    cur.execute(
        'INSERT INTO meals('
        'user_id, date, meal_type, description, created_at, updated_at'
        ') '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id, date_val, meal_type, description, now, now),
    )


@with_db
def list_meals_for_day(cur, user_id: int, date_iso: str):
    """List meals for day."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'SELECT id, meal_type, description FROM meals '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cur.fetchall()


@with_db
def update_meal(cur, user_id: int, meal_id: int, description: str) -> bool:
    """Update meal."""
    now = _utc_now()
    cur.execute(
        'UPDATE meals SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description,
         now,
         meal_id,
         user_id))
    return cur.rowcount > 0


@with_db
def delete_meal(cur, user_id: int, meal_id: int) -> bool:
    """Delete meal."""
    cur.execute('DELETE FROM meals WHERE id=%s AND user_id=%s',
                (meal_id, user_id))
    return cur.rowcount > 0


@with_db
def add_medicine(
        cur,
        user_id: int,
        date_iso: str,
        name: str,
        dosage: Optional[str]) -> None:
    """Add medicine."""
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cur.execute(
        'INSERT INTO medicines('
        'user_id, date, name, dosage, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id,
         date_val,
         name,
         dosage,
         now,
         now))


@with_db
def list_medicines_for_day(cur, user_id: int, date_iso: str):
    """List medicines for day."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'SELECT id, name, dosage FROM medicines '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cur.fetchall()


@with_db
def update_medicine(
        cur,
        user_id: int,
        med_id: int,
        name: str,
        dosage: Optional[str]) -> bool:
    """Update medicine."""
    now = _utc_now()
    cur.execute(
        'UPDATE medicines SET name=%s, dosage=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (name,
         dosage,
         now,
         med_id,
         user_id))
    return cur.rowcount > 0


@with_db
def delete_medicine(cur, user_id: int, med_id: int) -> bool:
    """Delete medicine."""
    cur.execute('DELETE FROM medicines WHERE id=%s AND user_id=%s',
                (med_id, user_id))
    return cur.rowcount > 0


@with_db
def add_stool(cur, user_id: int, date_iso: str, quality: int) -> None:
    """Add stool."""
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cur.execute(
        'INSERT INTO stools('
        'user_id, date, quality, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id,
         date_val,
         quality,
         now,
         now))


@with_db
def list_stools_for_day(cur, user_id: int, date_iso: str):
    """List stools for day."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'SELECT id, quality FROM stools '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cur.fetchall()


@with_db
def update_stool(cur, user_id: int, stool_id: int, quality: int) -> bool:
    """Update stool."""
    now = _utc_now()
    cur.execute(
        'UPDATE stools SET quality=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (quality,
         now,
         stool_id,
         user_id))
    return cur.rowcount > 0


@with_db
def delete_stool(cur, user_id: int, stool_id: int) -> bool:
    """Delete stool."""
    cur.execute('DELETE FROM stools WHERE id=%s AND user_id=%s',
                (stool_id, user_id))
    return cur.rowcount > 0


@with_db
def add_feeling(cur, user_id: int, date_iso: str, description: str) -> None:
    """Add feeling."""
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cur.execute(
        'INSERT INTO feelings('
        'user_id, date, description, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id,
         date_val,
         description,
         now,
         now))


@with_db
def list_feelings_for_day(cur, user_id: int, date_iso: str):
    """List feelings for day."""
    date_val = _parse_date(date_iso)
    cur.execute(
        'SELECT id, description FROM feelings '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cur.fetchall()


@with_db
def update_feeling(
        cur,
        user_id: int,
        feeling_id: int,
        description: str) -> bool:
    """Update feeling."""
    now = _utc_now()
    cur.execute(
        'UPDATE feelings SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description,
         now,
         feeling_id,
         user_id))
    return cur.rowcount > 0


@with_db
def delete_feeling(cur, user_id: int, feeling_id: int) -> bool:
    """Delete feeling."""
    cur.execute('DELETE FROM feelings WHERE id=%s AND user_id=%s',
                (feeling_id, user_id))
    return cur.rowcount > 0


@with_db
def fetch_all_for_report(cur, user_id: int) -> Dict[str, Any]:
    """Fetch all for report."""
    cur.execute(
        'SELECT date, meal_type, description FROM meals '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    meals = [dict(r) for r in cur.fetchall()]
    cur.execute(
        'SELECT date, name, dosage FROM medicines '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    medicines = [dict(r) for r in cur.fetchall()]
    cur.execute(
        'SELECT date, quality FROM stools '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    stools = [dict(r) for r in cur.fetchall()]
    cur.execute(
        'SELECT date, description FROM feelings '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    feelings = [dict(r) for r in cur.fetchall()]
    return {
        'meals': meals,
        'medicines': medicines,
        'stools': stools,
        'feelings': feelings}
