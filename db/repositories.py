"""Репозиторный слой для чтения и записи данных пользователя."""

from datetime import date, datetime, timezone
from typing import Any, TypeAlias

import psycopg

from db.connection import with_db

RowData: TypeAlias = dict[str, Any]
RowsData: TypeAlias = list[RowData]
UserTimes: TypeAlias = tuple[str, str, str, str, str, str]
UserScheduleRow: TypeAlias = tuple[int, str, str, str, str, str, str]

TIME_SLOT_COLUMNS: dict[str, str] = {
    'breakfast': 'breakfast_time',
    'lunch': 'lunch_time',
    'dinner': 'dinner_time',
    'toilet': 'toilet_time',
    'wakeup': 'wakeup_time',
    'bed': 'bed_time',
}


def _utc_now() -> datetime:
    """Возвращает текущее UTC-время без микросекунд для записей в БД.

    Returns:
        datetime: Текущее время UTC с обнулёнными микросекундами.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def _parse_date(date_iso: str) -> date:
    """Преобразует строку формата `YYYY-MM-DD` в объект `date`.

    Args:
        date_iso: Дата в формате хранения.

    Returns:
        date: Преобразованная дата.
    """
    return date.fromisoformat(date_iso)


def _fetch_dict(cursor: psycopg.Cursor) -> RowData | None:
    """Возвращает одну строку курсора в формате словаря.

    Args:
        cursor: Курсор PostgreSQL с `dict_row`.

    Returns:
        RowData | None: Словарь с полями строки или `None`.
    """
    row = cursor.fetchone()
    return dict(row) if row else None


def _list_rows_for_day(
    cursor: psycopg.Cursor,
    query: str,
    user_id: int,
    date_iso: str,
) -> RowsData:
    """Выполняет выборку строк за указанную дату пользователя.

    Args:
        cursor: Курсор PostgreSQL.
        query: SQL-запрос с параметрами `(user_id, date)`.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.

    Returns:
        RowsData: Список строк в виде словарей.
    """
    cursor.execute(query, (user_id, _parse_date(date_iso)))
    return [dict(row) for row in cursor.fetchall()]


def _delete_by_id(
    cursor: psycopg.Cursor,
    table_name: str,
    user_id: int,
    entity_id: int,
) -> bool:
    """Удаляет запись пользователя по идентификатору.

    Args:
        cursor: Курсор PostgreSQL.
        table_name: Имя таблицы.
        user_id: Идентификатор пользователя.
        entity_id: Идентификатор записи.

    Returns:
        bool: `True`, если запись удалена; иначе `False`.
    """
    cursor.execute(
        f'DELETE FROM {table_name} WHERE id=%s AND user_id=%s',
        (entity_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def register_user(cursor: psycopg.Cursor, user_id: int) -> None:
    """Создаёт пользователя при первом обращении к боту.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.
    """
    cursor.execute(
        'INSERT INTO users(user_id) VALUES (%s) '
        'ON CONFLICT(user_id) DO NOTHING',
        (user_id,),
    )


@with_db
def get_user_times(
    cursor: psycopg.Cursor,
    user_id: int,
) -> UserTimes | None:
    """Возвращает пользовательские времена напоминаний.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.

    Returns:
        UserTimes | None: Кортеж времени уведомлений или `None`, если
        пользователь не найден.
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
def update_user_time(
    cursor: psycopg.Cursor,
    user_id: int,
    slot: str,
    time_str: str,
) -> bool:
    """Обновляет одно поле расписания пользователя.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.
        slot: Ключ временного слота (`breakfast`, `lunch`, ...).
        time_str: Новое время в формате `HH:MM`.

    Returns:
        bool: `True`, если строка пользователя обновлена.
    """
    column_name = TIME_SLOT_COLUMNS.get(slot)
    if not column_name:
        return False

    cursor.execute(
        f'UPDATE users SET {column_name}=%s, updated_at=%s '
        'WHERE user_id=%s',
        (time_str, _utc_now(), user_id),
    )
    return cursor.rowcount > 0


@with_db
def get_all_users(cursor: psycopg.Cursor) -> list[UserScheduleRow]:
    """Возвращает расписание всех пользователей для планировщика.

    Args:
        cursor: Курсор PostgreSQL.

    Returns:
        list[UserScheduleRow]: Список кортежей с настройками расписания.
    """
    cursor.execute(
        'SELECT user_id, breakfast_time, lunch_time, dinner_time, '
        'toilet_time, wakeup_time, bed_time '
        'FROM users',
    )
    return [
        (
            row['user_id'],
            row['breakfast_time'],
            row['lunch_time'],
            row['dinner_time'],
            row['toilet_time'],
            row['wakeup_time'],
            row['bed_time'],
        )
        for row in cursor.fetchall()
    ]


@with_db
def is_notification_sent(
    cursor: psycopg.Cursor,
    user_id: int,
    notification_type: str,
    date_iso: str,
) -> bool:
    """Проверяет, было ли отправлено уведомление за указанную дату.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.
        notification_type: Тип уведомления.
        date_iso: Дата в формате хранения.

    Returns:
        bool: `True`, если уведомление уже отправлено.
    """
    cursor.execute(
        'SELECT 1 FROM notifications_log '
        'WHERE user_id=%s AND type=%s AND date=%s',
        (user_id, notification_type, _parse_date(date_iso)),
    )
    return cursor.fetchone() is not None


@with_db
def mark_notification_sent(
    cursor: psycopg.Cursor,
    user_id: int,
    notification_type: str,
    date_iso: str,
) -> None:
    """Помечает уведомление как отправленное в журнале.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.
        notification_type: Тип уведомления.
        date_iso: Дата в формате хранения.
    """
    cursor.execute(
        'INSERT INTO notifications_log(user_id, type, date) '
        'VALUES (%s, %s, %s) '
        'ON CONFLICT(user_id, type, date) DO NOTHING',
        (user_id, notification_type, _parse_date(date_iso)),
    )


def _ensure_sleep_row(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> None:
    """Создаёт запись сна за день, если она отсутствует.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO sleeps('
        'user_id, date, wakeup_time, bed_time, created_at, updated_at'
        ') '
        'SELECT user_id, %s, wakeup_time, bed_time, %s, %s '
        'FROM users WHERE user_id=%s '
        'ON CONFLICT(user_id, date) DO NOTHING',
        (_parse_date(date_iso), now, now, user_id),
    )


@with_db
def ensure_sleep_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowData | None:
    """Гарантирует существование записи сна и возвращает её.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.

    Returns:
        RowData | None: Словарь с данными сна за день или `None`.
    """
    date_value = _parse_date(date_iso)
    _ensure_sleep_row(cursor, user_id, date_iso)
    cursor.execute(
        'SELECT id, wakeup_time, bed_time, quality_description '
        'FROM sleeps WHERE user_id=%s AND date=%s',
        (user_id, date_value),
    )
    return _fetch_dict(cursor)


@with_db
def get_sleep_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowData | None:
    """Возвращает запись сна пользователя за конкретный день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.

    Returns:
        RowData | None: Словарь с данными сна или `None`.
    """
    cursor.execute(
        'SELECT id, wakeup_time, bed_time, quality_description '
        'FROM sleeps WHERE user_id=%s AND date=%s',
        (user_id, _parse_date(date_iso)),
    )
    return _fetch_dict(cursor)


@with_db
def upsert_sleep_times(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    wakeup_time: str | None = None,
    bed_time: str | None = None,
) -> bool:
    """Обновляет время подъёма и/или отхода ко сну за конкретный день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.
        wakeup_time: Новое время подъёма или `None`.
        bed_time: Новое время отхода ко сну или `None`.

    Returns:
        bool: `True`, если данные были обновлены.
    """
    _ensure_sleep_row(cursor, user_id, date_iso)
    date_value = _parse_date(date_iso)
    now = _utc_now()

    if wakeup_time is not None and bed_time is not None:
        cursor.execute(
            'UPDATE sleeps SET wakeup_time=%s, bed_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (wakeup_time, bed_time, now, user_id, date_value),
        )
        return cursor.rowcount > 0

    if wakeup_time is not None:
        cursor.execute(
            'UPDATE sleeps SET wakeup_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (wakeup_time, now, user_id, date_value),
        )
        return cursor.rowcount > 0

    if bed_time is not None:
        cursor.execute(
            'UPDATE sleeps SET bed_time=%s, updated_at=%s '
            'WHERE user_id=%s AND date=%s',
            (bed_time, now, user_id, date_value),
        )
        return cursor.rowcount > 0

    return False


@with_db
def upsert_sleep_quality(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    quality_description: str,
) -> bool:
    """Создаёт или обновляет описание качества сна за день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата в формате хранения.
        quality_description: Текстовое описание качества сна.

    Returns:
        bool: `True`, если запись создана или обновлена.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO sleeps('
        'user_id, date, wakeup_time, bed_time, quality_description, '
        'created_at, updated_at'
        ') '
        'SELECT user_id, %s, wakeup_time, bed_time, %s, %s, %s '
        'FROM users WHERE user_id=%s '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'quality_description=EXCLUDED.quality_description, '
        'updated_at=EXCLUDED.updated_at',
        (_parse_date(date_iso), quality_description, now, now, user_id),
    )
    return cursor.rowcount > 0


@with_db
def upsert_meal(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    meal_type: str,
    description: str,
) -> None:
    """Создаёт или обновляет приём пищи.

    Для основных приёмов (`breakfast`, `lunch`, `dinner`) запись за день
    обновляется, для `snack` всегда добавляется новая строка.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата приёма пищи в формате хранения.
        meal_type: Тип приёма пищи.
        description: Описание приёма пищи.
    """
    date_value = _parse_date(date_iso)
    now = _utc_now()

    if meal_type in ('breakfast', 'lunch', 'dinner'):
        cursor.execute(
            'SELECT id FROM meals '
            'WHERE user_id=%s AND date=%s AND meal_type=%s',
            (user_id, date_value, meal_type),
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
        ') VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id, date_value, meal_type, description, now, now),
    )


@with_db
def list_meals_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowsData:
    """Возвращает список приёмов пищи за день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата выборки в формате хранения.

    Returns:
        RowsData: Список записей о приёмах пищи.
    """
    return _list_rows_for_day(
        cursor,
        'SELECT id, meal_type, description FROM meals '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        user_id,
        date_iso,
    )


@with_db
def update_meal(
    cursor: psycopg.Cursor,
    user_id: int,
    meal_id: int,
    description: str,
) -> bool:
    """Обновляет описание приёма пищи по идентификатору.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        meal_id: Идентификатор записи приёма пищи.
        description: Новое текстовое описание.

    Returns:
        bool: `True`, если запись обновлена.
    """
    cursor.execute(
        'UPDATE meals SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description, _utc_now(), meal_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_meal(
    cursor: psycopg.Cursor,
    user_id: int,
    meal_id: int,
) -> bool:
    """Удаляет запись о приёме пищи.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        meal_id: Идентификатор записи.

    Returns:
        bool: `True`, если запись была удалена.
    """
    return _delete_by_id(cursor, 'meals', user_id, meal_id)


@with_db
def add_medicine(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    name: str,
    dosage: str | None,
) -> None:
    """Добавляет запись о приёме лекарства.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата приёма в формате хранения.
        name: Название лекарства.
        dosage: Дозировка, если указана пользователем.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO medicines('
        'user_id, date, name, dosage, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s, %s)',
        (user_id, _parse_date(date_iso), name, dosage, now, now),
    )


@with_db
def list_medicines_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowsData:
    """Возвращает список лекарств за день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата выборки в формате хранения.

    Returns:
        RowsData: Список записей о лекарствах.
    """
    return _list_rows_for_day(
        cursor,
        'SELECT id, name, dosage FROM medicines '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        user_id,
        date_iso,
    )


@with_db
def update_medicine(
    cursor: psycopg.Cursor,
    user_id: int,
    med_id: int,
    name: str,
    dosage: str | None,
) -> bool:
    """Обновляет название и дозировку лекарства.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        med_id: Идентификатор записи лекарства.
        name: Новое название.
        dosage: Новая дозировка.

    Returns:
        bool: `True`, если запись обновлена.
    """
    cursor.execute(
        'UPDATE medicines SET name=%s, dosage=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (name, dosage, _utc_now(), med_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_medicine(
    cursor: psycopg.Cursor,
    user_id: int,
    med_id: int,
) -> bool:
    """Удаляет запись о приёме лекарства.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        med_id: Идентификатор записи.

    Returns:
        bool: `True`, если запись была удалена.
    """
    return _delete_by_id(cursor, 'medicines', user_id, med_id)


@with_db
def add_stool(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    quality: int,
) -> None:
    """Добавляет оценку стула по Бристольской шкале.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата записи в формате хранения.
        quality: Оценка от 0 до 7.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO stools('
        'user_id, date, quality, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id, _parse_date(date_iso), quality, now, now),
    )


@with_db
def list_stools_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowsData:
    """Возвращает записи туалета за выбранный день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата выборки в формате хранения.

    Returns:
        RowsData: Список записей туалета.
    """
    return _list_rows_for_day(
        cursor,
        'SELECT id, quality FROM stools '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        user_id,
        date_iso,
    )


@with_db
def update_stool(
    cursor: psycopg.Cursor,
    user_id: int,
    stool_id: int,
    quality: int,
) -> bool:
    """Обновляет оценку стула по идентификатору записи.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        stool_id: Идентификатор записи.
        quality: Новая оценка от 0 до 7.

    Returns:
        bool: `True`, если запись обновлена.
    """
    cursor.execute(
        'UPDATE stools SET quality=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (quality, _utc_now(), stool_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_stool(
    cursor: psycopg.Cursor,
    user_id: int,
    stool_id: int,
) -> bool:
    """Удаляет запись туалета по идентификатору.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        stool_id: Идентификатор записи.

    Returns:
        bool: `True`, если запись была удалена.
    """
    return _delete_by_id(cursor, 'stools', user_id, stool_id)


@with_db
def add_feeling(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    description: str,
) -> None:
    """Добавляет запись о самочувствии пользователя.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата записи в формате хранения.
        description: Текст самочувствия.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO feelings('
        'user_id, date, description, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s)',
        (user_id, _parse_date(date_iso), description, now, now),
    )


@with_db
def increment_water(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    glasses_count: int = 1,
) -> int:
    """Увеличивает счётчик воды за день на заданное количество.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата записи в формате хранения.
        glasses_count: Количество добавляемых стаканов.

    Returns:
        int: Текущее количество стаканов воды за день.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO water('
        'user_id, date, glasses_count, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s) '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'glasses_count=water.glasses_count + EXCLUDED.glasses_count, '
        'updated_at=EXCLUDED.updated_at '
        'RETURNING glasses_count',
        (user_id, _parse_date(date_iso), glasses_count, now, now),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else glasses_count


@with_db
def get_water_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> int:
    """Возвращает количество выпитой воды за выбранный день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата выборки в формате хранения.

    Returns:
        int: Количество стаканов воды за день.
    """
    cursor.execute(
        'SELECT glasses_count FROM water WHERE user_id=%s AND date=%s',
        (user_id, _parse_date(date_iso)),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else 0


@with_db
def set_water_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
    glasses_count: int,
) -> int:
    """Устанавливает точное количество воды за день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата изменения в формате хранения.
        glasses_count: Итоговое количество стаканов.

    Returns:
        int: Сохранённое количество стаканов воды.
    """
    now = _utc_now()
    cursor.execute(
        'INSERT INTO water('
        'user_id, date, glasses_count, created_at, updated_at'
        ') VALUES (%s, %s, %s, %s, %s) '
        'ON CONFLICT(user_id, date) DO UPDATE SET '
        'glasses_count=EXCLUDED.glasses_count, '
        'updated_at=EXCLUDED.updated_at '
        'RETURNING glasses_count',
        (user_id, _parse_date(date_iso), glasses_count, now, now),
    )
    row = cursor.fetchone()
    return int(row['glasses_count']) if row else glasses_count


@with_db
def list_feelings_for_day(
    cursor: psycopg.Cursor,
    user_id: int,
    date_iso: str,
) -> RowsData:
    """Возвращает записи самочувствия за выбранный день.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        date_iso: Дата выборки в формате хранения.

    Returns:
        RowsData: Список записей самочувствия.
    """
    return _list_rows_for_day(
        cursor,
        'SELECT id, description FROM feelings '
        'WHERE user_id=%s AND date=%s ORDER BY created_at',
        user_id,
        date_iso,
    )


@with_db
def update_feeling(
    cursor: psycopg.Cursor,
    user_id: int,
    feeling_id: int,
    description: str,
) -> bool:
    """Обновляет описание самочувствия по идентификатору записи.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        feeling_id: Идентификатор записи.
        description: Новое описание самочувствия.

    Returns:
        bool: `True`, если запись обновлена.
    """
    cursor.execute(
        'UPDATE feelings SET description=%s, updated_at=%s '
        'WHERE id=%s AND user_id=%s',
        (description, _utc_now(), feeling_id, user_id),
    )
    return cursor.rowcount > 0


@with_db
def delete_feeling(
    cursor: psycopg.Cursor,
    user_id: int,
    feeling_id: int,
) -> bool:
    """Удаляет запись самочувствия.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя.
        feeling_id: Идентификатор записи.

    Returns:
        bool: `True`, если запись была удалена.
    """
    return _delete_by_id(cursor, 'feelings', user_id, feeling_id)


@with_db
def fetch_all_for_report(
    cursor: psycopg.Cursor,
    user_id: int,
) -> RowData:
    """Возвращает все данные пользователя для формирования Excel-отчёта.

    Args:
        cursor: Курсор PostgreSQL.
        user_id: Идентификатор пользователя Telegram.

    Returns:
        RowData: Словарь с ключами `meals`, `medicines`, `stools`,
        `feelings`, `water`, `sleeps`.
    """
    datasets: dict[str, tuple[str, tuple[Any, ...]]] = {
        'meals': (
            'SELECT date, meal_type, description FROM meals '
            'WHERE user_id=%s ORDER BY date, created_at',
            (user_id,),
        ),
        'medicines': (
            'SELECT date, name, dosage FROM medicines '
            'WHERE user_id=%s ORDER BY date, created_at',
            (user_id,),
        ),
        'stools': (
            'SELECT date, quality FROM stools '
            'WHERE user_id=%s ORDER BY date, created_at',
            (user_id,),
        ),
        'feelings': (
            'SELECT date, description FROM feelings '
            'WHERE user_id=%s ORDER BY date, created_at',
            (user_id,),
        ),
        'water': (
            'SELECT date, glasses_count FROM water '
            'WHERE user_id=%s ORDER BY date',
            (user_id,),
        ),
        'sleeps': (
            'SELECT date, wakeup_time, bed_time, quality_description '
            'FROM sleeps WHERE user_id=%s ORDER BY date',
            (user_id,),
        ),
    }

    report_data: RowData = {}
    for dataset_name, (query, params) in datasets.items():
        cursor.execute(query, params)
        report_data[dataset_name] = [dict(row) for row in cursor.fetchall()]
    return report_data
