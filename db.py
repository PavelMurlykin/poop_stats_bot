import sqlite3
from datetime import datetime

DB_PATH = 'db.sqlite3'


def with_db(func):
    """Декоратор, открывающий соединение и передающий курсор."""
    def wrapper(*args, **kwargs):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            result = func(cur, *args, **kwargs)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return wrapper


# ------------------- Инициализация таблиц -------------------
@with_db
def create_tables(cur):
    """Создание всех таблиц и справочников."""
    # Пользователи
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            breakfast_time TEXT DEFAULT '08:00',
            lunch_time TEXT DEFAULT '13:00',
            dinner_time TEXT DEFAULT '19:00',
            toilet_time TEXT DEFAULT '09:00'
        )
    ''')

    # Типы приёмов пищи (справочник)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meal_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    ''')
    # Заполняем типы, если таблица пуста
    cur.execute('SELECT COUNT(*) FROM meal_types')
    if cur.fetchone()[0] == 0:
        types = [('завтрак',), ('обед',), ('ужин',), ('перекус',)]
        cur.executemany('INSERT INTO meal_types (name) VALUES (?)', types)

    # Приёмы пищи
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            meal_type_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (meal_type_id) REFERENCES meal_types(id)
        )
    ''')

    # Лекарства
    cur.execute('''
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            dosage TEXT,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Стул
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            quality INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Лог уведомлений
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            date TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, type, date)
        )
    ''')

    # Бристольская шкала (справочник)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bristol_scale (
            id INTEGER PRIMARY KEY,
            description TEXT
        )
    ''')
    bristol_data = [
        (0, 'Отсутствие дефекации'),
        (1,
         'Отдельные твёрдые комки, как орехи, трудно проходят [серьезный запор]'
         ),
        (2, 'Колбасовидный, но комковатый [запор или склонность к запору]'),
        (3, 'Колбасовидный с трещинами на поверхности [норма]'),
        (4, 'Колбасовидный гладкий и мягкий [норма]'),
        (5, 'Мягкие маленькие шарики с чёткими краями [склонность к диарее]'),
        (6, 'Рыхлые кусочки с неровными краями, кашицеобразный [диарея]'),
        (7, 'Водянистый, без твёрдых кусочков [сильная диарея]')
    ]

    cur.executemany(
        'INSERT OR REPLACE INTO bristol_scale (id, description) VALUES (?, ?)',
        bristol_data
    )


# ------------------- Пользователи -------------------
@with_db
def register_user(cur, user_id):
    cur.execute(
        'INSERT OR IGNORE INTO users (user_id) VALUES (?)',
        (user_id,)
    )


@with_db
def get_user_times(cur, user_id):
    cur.execute('''
        SELECT
            breakfast_time,
            lunch_time,
            dinner_time,
            toilet_time
        FROM users
        WHERE user_id = ?
    ''', (user_id,))
    return cur.fetchone()


@with_db
def update_user_time(cur, user_id, meal_type, time_str):
    try:
        datetime.strptime(time_str, '%H:%M')
    except ValueError:
        return False
    cur.execute(f'''
        UPDATE users
        SET {meal_type}_time = ?
        WHERE user_id = ?
    ''', (time_str, user_id))
    return True


@with_db
def get_all_users(cur):
    cur.execute('''
        SELECT
            user_id,
            breakfast_time,
            lunch_time,
            dinner_time,
            toilet_time
        FROM users
    ''')
    return cur.fetchall()


# ------------------- Уведомления -------------------
@with_db
def is_notification_sent(cur, user_id, n_type, date_str):
    cur.execute('''
        SELECT id
        FROM notifications_log
        WHERE user_id = ? AND type = ? AND date = ?
    ''', (user_id, n_type, date_str))
    return cur.fetchone() is not None


@with_db
def mark_notification_sent(cur, user_id, n_type, date_str):
    cur.execute('''
        INSERT OR IGNORE INTO notifications_log
            (user_id, type, date)
        VALUES (?, ?, ?)
    ''', (user_id, n_type, date_str))


# ------------------- Приёмы пищи -------------------
@with_db
def get_meal_types(cur):
    """Возвращает список (id, name) всех типов приёмов пищи."""
    cur.execute('SELECT id, name FROM meal_types ORDER BY id')
    return cur.fetchall()


@with_db
def save_meal(cur, user_id, meal_type_id, description, date_str):
    """
    Сохраняет запись о приёме пищи.
    Для завтрака/обеда/ужина обновляет существующую запись, иначе создаёт новую.
    Для перекусов всегда вставляет новую запись.
    """
    # Получаем имя типа
    cur.execute('SELECT name FROM meal_types WHERE id = ?', (meal_type_id,))
    row = cur.fetchone()
    if not row:
        return False
    meal_name = row['name']

    now = datetime.now().isoformat(timespec='seconds')

    if meal_name in ('завтрак', 'обед', 'ужин'):
        # Проверяем, есть ли уже запись
        cur.execute('''
            SELECT id FROM meals
            WHERE user_id = ? AND date = ? AND meal_type_id = ?
        ''', (user_id, date_str, meal_type_id))
        existing = cur.fetchone()

        if existing:
            # Обновляем существующую
            cur.execute('''
                UPDATE meals
                SET description = ?, updated_at = ?
                WHERE id = ?
            ''', (description, now, existing['id']))
        else:
            # Вставляем новую
            cur.execute('''
                INSERT INTO meals (
                        user_id
                        , date
                        , meal_type_id
                        , description
                        , created_at
                        , updated_at
                    )
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, date_str, meal_type_id, description, now, now))
    else:  # перекус — всегда новая запись
        cur.execute('''
            INSERT INTO meals (
                    user_id
                    , date
                    , meal_type_id
                    , description
                    , created_at
                    , updated_at
                )
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, date_str, meal_type_id, description, now, now))

    return True


@with_db
def get_meals_for_day(cur, user_id, date_str):
    """Возвращает все записи о еде за указанный день."""
    cur.execute('''
        SELECT
            m.id,
            m.date,
            mt.name AS meal_type,
            m.description,
            m.created_at,
            m.updated_at
        FROM meals m
        JOIN meal_types mt ON m.meal_type_id = mt.id
        WHERE m.user_id = ? AND m.date = ?
        ORDER BY mt.id, m.created_at
    ''', (user_id, date_str))
    return cur.fetchall()


@with_db
def update_meal_description(cur, meal_id, new_description):
    """Обновляет описание конкретного приёма пищи."""
    now = datetime.now().isoformat(timespec='seconds')
    cur.execute('''
        UPDATE meals
        SET description = ?, updated_at = ?
        WHERE id = ?
    ''', (new_description, now, meal_id))


@with_db
def delete_meal(cur, meal_id):
    """Удаляет запись о приёме пищи (полезно для перекусов)."""
    cur.execute('DELETE FROM meals WHERE id = ?', (meal_id,))


# ------------------- Лекарства -------------------
@with_db
def save_medicine(cur, user_id, name, dosage, date_str):
    now = datetime.now().isoformat(timespec='seconds')
    cur.execute('''
        INSERT INTO medicines (
                user_id
                , name
                , dosage
                , date
                , created_at
                , updated_at
            )
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, name, dosage, date_str, now, now))


@with_db
def get_medicines_for_day(cur, user_id, date_str):
    cur.execute('''
        SELECT
            id,
            name,
            dosage,
            created_at,
            updated_at
        FROM medicines
        WHERE user_id = ? AND date = ?
        ORDER BY created_at
    ''', (user_id, date_str))
    return cur.fetchall()


@with_db
def update_medicine(cur, med_id, name, dosage):
    now = datetime.now().isoformat(timespec='seconds')
    cur.execute('''
        UPDATE medicines
        SET name = ?, dosage = ?, updated_at = ?
        WHERE id = ?
    ''', (name, dosage, now, med_id))


@with_db
def delete_medicine(cur, med_id):
    cur.execute('DELETE FROM medicines WHERE id = ?', (med_id,))


# ------------------- Стул -------------------
@with_db
def save_stool(cur, user_id, quality, date_str):
    now = datetime.now().isoformat(timespec='seconds')
    cur.execute('''
        INSERT INTO stools (
                user_id
                , date
                , quality
                , created_at
                , updated_at
            )
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, date_str, quality, now, now))


@with_db
def get_stools_for_day(cur, user_id, date_str):
    cur.execute('''
        SELECT
            id,
            quality,
            created_at,
            updated_at
        FROM stools
        WHERE user_id = ? AND date = ?
        ORDER BY created_at
    ''', (user_id, date_str))
    return cur.fetchall()


@with_db
def update_stool(cur, stool_id, quality):
    now = datetime.now().isoformat(timespec='seconds')
    cur.execute('''
        UPDATE stools
        SET quality = ?, updated_at = ?
        WHERE id = ?
    ''', (quality, now, stool_id))


@with_db
def delete_stool(cur, stool_id):
    cur.execute('DELETE FROM stools WHERE id = ?', (stool_id,))


# ------------------- Бристольская шкала -------------------
@with_db
def get_bristol_scale(cur):
    cur.execute('SELECT id, description FROM bristol_scale ORDER BY id')
    return cur.fetchall()
