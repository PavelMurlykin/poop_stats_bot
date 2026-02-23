from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from db.connection import with_db


def _utc_now() -> datetime:
    """
    Выполняет операцию `_utc_now` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        datetime: Результат выполнения функции.
    """
    return datetime.utcnow().replace(microsecond=0)


def _parse_date(date_iso: str) -> date:
    """
    Выполняет операцию `_parse_date` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        date: Результат выполнения функции.
    """
    return date.fromisoformat(date_iso)


@with_db
def register_user(cursor, user_id: int) -> None:
    """
    Выполняет операцию `register_user` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    cursor.execute(
        'INSERT INTO users(user_id) VALUES (%s) '
        'ON CONFLICT(user_id) DO NOTHING',
        (user_id,),
    )


@with_db
def get_user_times(
    cursor,
    user_id: int,
) -> Optional[Tuple[str, str, str, str, str, str]]:
    """
    Выполняет операцию `get_user_times` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.

    Returns:
        Optional[Tuple[str, str, str, str, str, str]]: Результат выполнения
        функции.
    """
    cursor.execute(
        'SELECT breakfast_time, lunch_time, dinner_time, toilet_time, '
        'wakeup_time, bed_time '
        'FROM users WHERE user_id = %s',
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return (
        row['breakfast_time'],
        row['lunch_time'],
        row['dinner_time'],
        row['toilet_time'],
        row['wakeup_time'],
        row['bed_time'],
    )


@with_db
def update_user_time(cursor, user_id: int, slot: str, time_str: str) -> bool:
    """
    Выполняет операцию `update_user_time` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        slot: Ключ слота расписания пользователя.
        time_str: Время в формате `HH:MM`.

    Returns:
        bool: Результат выполнения функции.
    """
    col_map = {
        'breakfast': 'breakfast_time',
        'lunch': 'lunch_time',
        'dinner': 'dinner_time',
        'toilet': 'toilet_time',
        'wakeup': 'wakeup_time',
        'bed': 'bed_time',
    }
    column_name = col_map.get(slot)
    if not column_name:
        return False
    now = _utc_now()
    cursor.execute(
        (
            f'UPDATE users SET {column_name} = %s, updated_at = %s '
            'WHERE user_id = %s'
        ),
        (time_str, now, user_id),
    )
    return cursor.rowcount > 0


@with_db
def get_all_users(cursor) -> List[Tuple[int, str, str, str, str, str, str]]:
    """
    Выполняет операцию `get_all_users` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.

    Returns:
        List[Tuple[int, str, str, str, str, str, str]]: Результат выполнения
        функции.
    """
    cursor.execute(
        'SELECT user_id, breakfast_time, lunch_time, dinner_time, '
        'toilet_time, wakeup_time, bed_time '
        'FROM users',
    )
    return [
        (
            r['user_id'],
            r['breakfast_time'],
            r['lunch_time'],
            r['dinner_time'],
            r['toilet_time'],
            r['wakeup_time'],
            r['bed_time'],
        )
        for row in cursor.fetchall()
    ]


@with_db
def is_notification_sent(
    cursor,
    user_id: int,
    notification_type: str,
    date_iso: str,
) -> bool:
    """
    Выполняет операцию `is_notification_sent` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        notification_type: Параметр `notification_type` для текущего шага
                           обработки.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        bool: Результат выполнения функции.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT 1 FROM notifications_log '
        'WHERE user_id=%s AND type=%s AND date=%s',
        (user_id, notification_type, date_val),
    )
    return cursor.fetchone() is not None


@with_db
def mark_notification_sent(
    cursor,
    user_id: int,
    notification_type: str,
    date_iso: str,
) -> None:
    """
    Выполняет операцию `mark_notification_sent` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        notification_type: Параметр `notification_type` для текущего шага
                           обработки.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO notifications_log(user_id, type, date) '
        'VALUES (%s, %s, %s) '
        'ON CONFLICT(user_id, type, date) DO NOTHING',
        (user_id, notification_type, date_val),
    )


@with_db
def ensure_sleep_for_day(
    cursor,
    user_id: int,
    date_iso: str,
) -> Optional[Dict[str, Any]]:
    """
    Выполняет операцию `ensure_sleep_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Optional[Dict[str, Any]]: Результат выполнения функции.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO sleeps('
        'user_id, date, wakeup_time, bed_time, created_at, updated_at'
        ') '
        'SELECT user_id, %s, wakeup_time, bed_time, %s, %s '
        'FROM users WHERE user_id=%s '
        'ON CONFLICT(user_id, date) DO NOTHING',
        (date_val, now, now, user_id),
    )
    cursor.execute(
        'SELECT id, wakeup_time, bed_time, quality_description '
        'FROM sleeps WHERE user_id=%s AND date=%s',
        (user_id, date_val),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


@with_db
def get_sleep_for_day(
    cursor,
    user_id: int,
    date_iso: str,
) -> Optional[Dict[str, Any]]:
    """
    Выполняет операцию `get_sleep_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Optional[Dict[str, Any]]: Результат выполнения функции.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT id, wakeup_time, bed_time, quality_description '
        'FROM sleeps WHERE user_id=%s AND date=%s',
        (user_id, date_val),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


@with_db
def upsert_sleep_times(
    cursor,
    user_id: int,
    date_iso: str,
    wakeup_time: Optional[str] = None,
    bed_time: Optional[str] = None,
) -> bool:
    """
    Выполняет операцию `upsert_sleep_times` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        wakeup_time: Параметр `wakeup_time` для текущего шага обработки.
        bed_time: Параметр `bed_time` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO sleeps('
        'user_id, date, wakeup_time, bed_time, created_at, updated_at'
        ') '
        'SELECT user_id, %s, wakeup_time, bed_time, %s, %s '
        'FROM users WHERE user_id=%s '
        'ON CONFLICT(user_id, date) DO NOTHING',
        (date_val, now, now, user_id),
    )

    if wakeup_time is not None and bed_time is not None:
        cursor.execute(
            'UPDATE sleeps SET wakeup_time=%s, bed_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (wakeup_time, bed_time, now, user_id, date_val),
        )
        return cursor.rowcount > 0

    if wakeup_time is not None:
        cursor.execute(
            'UPDATE sleeps SET wakeup_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (wakeup_time, now, user_id, date_val),
        )
        return cursor.rowcount > 0

    if bed_time is not None:
        cursor.execute(
            'UPDATE sleeps SET bed_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (bed_time, now, user_id, date_val),
        )
        return cursor.rowcount > 0

    return False


@with_db
def upsert_sleep_quality(
    cursor,
    user_id: int,
    date_iso: str,
    quality_description: str,
) -> bool:
    """
    Выполняет операцию `upsert_sleep_quality` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        quality_description: Параметр `quality_description` для текущего шага
                             обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO sleeps('
        'user_id, date, wakeup_time, bed_time, quality_description, '
        'created_at, updated_at'
        ') '
        'SELECT user_id, %s, wakeup_time, bed_time, %s, %s, %s '
        'FROM users WHERE user_id=%s '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'quality_description = EXCLUDED.quality_description, '
        'updated_at = EXCLUDED.updated_at',
        (date_val, quality_description, now, now, user_id),
    )
    return cursor.rowcount > 0


@with_db
def upsert_meal(
    cursor,
    user_id: int,
    date_iso: str,
    meal_type: str,
    description: str,
) -> None:
    """
    Выполняет операцию `upsert_meal` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        meal_type: Параметр `meal_type` для текущего шага обработки.
        description: Параметр `description` для текущего шага обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    if meal_type in ('breakfast', 'lunch', 'dinner'):
        cursor.execute(
            'SELECT id FROM meals '
            'WHERE user_id=%s AND date=%s AND meal_type=%s',
            (user_id, date_val, meal_type),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute(
                'UPDATE meals SET description=%s, updated_at=%s '
                'WHERE id=%s AND user_id=%s',
                (description, now, row['id'], user_id),
            )
            return
    cursor.execute(
        'INSERT INTO meals('
        'user_id, date, meal_type, description, created_at, updated_at'
        ') '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id, date_val, meal_type, description, now, now),
    )


@with_db
def list_meals_for_day(cursor, user_id: int, date_iso: str):
    """
    Выполняет операцию `list_meals_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT id, meal_type, description FROM meals '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cursor.fetchall()


@with_db
def update_meal(cursor, user_id: int, meal_id: int, description: str) -> bool:
    """
    Выполняет операцию `update_meal` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        meal_id: Параметр `meal_id` для текущего шага обработки.
        description: Параметр `description` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    cursor.execute(
        'UPDATE meals SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description, now, meal_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_meal(cursor, user_id: int, meal_id: int) -> bool:
    """
    Выполняет операцию `delete_meal` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        meal_id: Параметр `meal_id` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    cursor.execute('DELETE FROM meals WHERE id=%s AND user_id=%s',
                   (meal_id, user_id))
    return cursor.rowcount > 0


@with_db
def add_medicine(
    cursor,
    user_id: int,
    date_iso: str,
    name: str,
    dosage: Optional[str],
) -> None:
    """
    Выполняет операцию `add_medicine` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        name: Параметр `name` для текущего шага обработки.
        dosage: Параметр `dosage` для текущего шага обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO medicines('
        'user_id, date, name, dosage, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id, date_val, name, dosage, now, now),
    )


@with_db
def list_medicines_for_day(cursor, user_id: int, date_iso: str):
    """
    Выполняет операцию `list_medicines_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT id, name, dosage FROM medicines '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cursor.fetchall()


@with_db
def update_medicine(
    cursor,
    user_id: int,
    med_id: int,
    name: str,
    dosage: Optional[str],
) -> bool:
    """
    Выполняет операцию `update_medicine` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        med_id: Параметр `med_id` для текущего шага обработки.
        name: Параметр `name` для текущего шага обработки.
        dosage: Параметр `dosage` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    cursor.execute(
        'UPDATE medicines SET name=%s, dosage=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (name, dosage, now, med_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_medicine(cursor, user_id: int, med_id: int) -> bool:
    """
    Выполняет операцию `delete_medicine` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        med_id: Параметр `med_id` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    cursor.execute('DELETE FROM medicines WHERE id=%s AND user_id=%s',
                   (med_id, user_id))
    return cursor.rowcount > 0


@with_db
def add_stool(cursor, user_id: int, date_iso: str, quality: int) -> None:
    """
    Выполняет операцию `add_stool` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        quality: Параметр `quality` для текущего шага обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO stools('
        'user_id, date, quality, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id, date_val, quality, now, now),
    )


@with_db
def list_stools_for_day(cursor, user_id: int, date_iso: str):
    """
    Выполняет операцию `list_stools_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT id, quality FROM stools '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cursor.fetchall()


@with_db
def update_stool(cursor, user_id: int, stool_id: int, quality: int) -> bool:
    """
    Выполняет операцию `update_stool` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        stool_id: Параметр `stool_id` для текущего шага обработки.
        quality: Параметр `quality` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    cursor.execute(
        'UPDATE stools SET quality=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (quality, now, stool_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_stool(cursor, user_id: int, stool_id: int) -> bool:
    """
    Выполняет операцию `delete_stool` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        stool_id: Параметр `stool_id` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    cursor.execute('DELETE FROM stools WHERE id=%s AND user_id=%s',
                   (stool_id, user_id))
    return cursor.rowcount > 0


@with_db
def add_feeling(cursor, user_id: int, date_iso: str, description: str) -> None:
    """
    Выполняет операцию `add_feeling` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        description: Параметр `description` для текущего шага обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO feelings('
        'user_id, date, description, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id, date_val, description, now, now),
    )


@with_db
def increment_water(
    cursor,
    user_id: int,
    date_iso: str,
    glasses_count: int = 1,
) -> int:
    """
    Выполняет операцию `increment_water` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        glasses_count: Параметр `glasses_count` для текущего шага обработки.

    Returns:
        int: Результат выполнения функции.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO water('
        'user_id, date, glasses_count, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s) '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'glasses_count = water.glasses_count + EXCLUDED.glasses_count, '
        'updated_at = EXCLUDED.updated_at '
        'RETURNING glasses_count',
        (user_id, date_val, glasses_count, now, now),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else glasses_count


@with_db
def get_water_for_day(cursor, user_id: int, date_iso: str) -> int:
    """
    Выполняет операцию `get_water_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        int: Результат выполнения функции.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT glasses_count FROM water '
        'WHERE user_id=%s AND date=%s',
        (user_id, date_val),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else 0


@with_db
def set_water_for_day(
    cursor,
    user_id: int,
    date_iso: str,
    glasses_count: int,
) -> int:
    """
    Выполняет операцию `set_water_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.
        glasses_count: Параметр `glasses_count` для текущего шага обработки.

    Returns:
        int: Результат выполнения функции.
    """
    now = _utc_now()
    date_val = _parse_date(date_iso)
    cursor.execute(
        'INSERT INTO water('
        'user_id, date, glasses_count, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s) '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'glasses_count = EXCLUDED.glasses_count, '
        'updated_at = EXCLUDED.updated_at '
        'RETURNING glasses_count',
        (user_id, date_val, glasses_count, now, now),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else glasses_count


@with_db
def list_feelings_for_day(cursor, user_id: int, date_iso: str):
    """
    Выполняет операцию `list_feelings_for_day` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        date_iso: Дата в формате `YYYY-MM-DD`.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    date_val = _parse_date(date_iso)
    cursor.execute(
        'SELECT id, description FROM feelings '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        (user_id, date_val),
    )
    return cursor.fetchall()


@with_db
def update_feeling(
    cursor,
    user_id: int,
    feeling_id: int,
    description: str,
) -> bool:
    """
    Выполняет операцию `update_feeling` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        feeling_id: Параметр `feeling_id` для текущего шага обработки.
        description: Параметр `description` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    now = _utc_now()
    cursor.execute(
        'UPDATE feelings SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description, now, feeling_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_feeling(cursor, user_id: int, feeling_id: int) -> bool:
    """
    Выполняет операцию `delete_feeling` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.
        feeling_id: Параметр `feeling_id` для текущего шага обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    cursor.execute('DELETE FROM feelings WHERE id=%s AND user_id=%s',
                   (feeling_id, user_id))
    return cursor.rowcount > 0


@with_db
def fetch_all_for_report(cursor, user_id: int) -> Dict[str, Any]:
    """
    Выполняет операцию `fetch_all_for_report` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        cursor: Курсор PostgreSQL для выполнения SQL-запросов.
        user_id: Идентификатор пользователя в Telegram.

    Returns:
        Dict[str, Any]: Результат выполнения функции.
    """
    cursor.execute(
        'SELECT date, meal_type, description FROM meals '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    meals = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        'SELECT date, name, dosage FROM medicines '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    medicines = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        'SELECT date, quality FROM stools '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    stools = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        'SELECT date, description FROM feelings '
        'WHERE user_id=%s ORDER BY date, created_at',
        (user_id,),
    )
    feelings = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        'SELECT date, glasses_count FROM water '
        'WHERE user_id=%s ORDER BY date',
        (user_id,),
    )
    water = [dict(row) for row in cursor.fetchall()]
    cursor.execute(
        'SELECT date, wakeup_time, bed_time, quality_description FROM sleeps '
        'WHERE user_id=%s ORDER BY date',
        (user_id,),
    )
    sleeps = [dict(row) for row in cursor.fetchall()]
    return {
        'meals': meals,
        'medicines': medicines,
        'stools': stools,
        'feelings': feelings,
        'water': water,
        'sleeps': sleeps,
    }
