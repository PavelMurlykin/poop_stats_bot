import sqlite3
from datetime import datetime

DB_PATH = 'db.sqlite3'


def create_tables():
    """Создание таблиц, если их нет, и заполнение справочника Bristol."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users
        (
            user_id INTEGER PRIMARY KEY,
            breakfast_time TEXT DEFAULT '08:00',
            lunch_time TEXT DEFAULT '13:00',
            dinner_time TEXT DEFAULT '19:00',
            toilet_time TEXT DEFAULT '09:00'
        )
    ''')

    # Таблица приёмов пищи
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meals
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            breakfast TEXT,
            lunch TEXT,
            dinner TEXT,
            UNIQUE(user_id, date)
        )
    ''')

    # Таблица оценок стула
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stools
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            quality INTEGER,
            UNIQUE(user_id, date)
        )
    ''')

    # Таблица лога уведомлений (чтобы не дублировать)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS notifications_log
        (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            date TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, type, date)
        )
    ''')

    # Справочник Бристольской шкалы
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bristol_scale
        (
            id INTEGER PRIMARY KEY,
            description TEXT
        )
    ''')

    # Заполняем справочник, если он пуст
    cur.execute("SELECT COUNT(*) FROM bristol_scale")
    if cur.fetchone()[0] == 0:
        bristol_data = [
            (0, "Отсутствие дефекации"),
            (1, "Отдельные твёрдые комки, как орехи (трудно проходят)"),
            (2, "Колбасовидный, но комковатый"),
            (3, "Колбасовидный с трещинами на поверхности"),
            (4, "Колбасовидный гладкий и мягкий"),
            (5, "Мягкие маленькие шарики с чёткими краями"),
            (6, "Рыхлые кусочки с неровными краями, кашицеобразный"),
            (7, "Водянистый, без твёрдых кусочков (полностью жидкий)")
        ]
        cur.executemany(
            "INSERT INTO bristol_scale (id, description) VALUES (?, ?)", bristol_data)

    conn.commit()
    conn.close()


def register_user(user_id):
    """Добавляет пользователя с настройками по умолчанию, если его нет."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()


def get_user_times(user_id):
    """Возвращает (breakfast_time, lunch_time, dinner_time, toilet_time)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT breakfast_time, lunch_time, dinner_time, toilet_time
        FROM users
        WHERE user_id=?
    ''', (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def update_user_time(user_id, meal_type, time_str):
    """Обновляет время для указанного типа (breakfast/lunch/dinner/toilet)."""
    try:
        datetime.strptime(time_str, '%H:%M')
    except ValueError:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        f'UPDATE users SET {meal_type}_time = ? WHERE user_id = ?', (time_str, user_id))
    conn.commit()
    conn.close()
    return True


def get_all_users():
    """
    Возвращает список кортежей
    (user_id, breakfast_time, lunch_time, dinner_time, toilet_time).
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id, breakfast_time, lunch_time, dinner_time, toilet_time
        FROM users
    ''')
    rows = cur.fetchall()
    conn.close()
    return rows


def is_notification_sent(user_id, n_type, date_str):
    """Проверяет, отправлялось ли уведомление сегодня."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        SELECT id
        FROM notifications_log
        WHERE user_id=? AND type=? AND date=?
    ''', (user_id, n_type, date_str))
    row = cur.fetchone()
    conn.close()
    return row is not None


def mark_notification_sent(user_id, n_type, date_str):
    """Записывает факт отправки уведомления."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR IGNORE INTO notifications_log (user_id, type, date) VALUES (?, ?, ?)',
                (user_id, n_type, date_str))
    conn.commit()
    conn.close()


def save_meal(user_id, meal_type, text, date_str):
    """Сохраняет или обновляет запись о приёме пищи."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id FROM meals WHERE user_id=? AND date=?',
                (user_id, date_str))
    row = cur.fetchone()
    if row:
        cur.execute(
            f'UPDATE meals SET {meal_type}=? WHERE user_id=? AND date=?', (text, user_id, date_str))
    else:
        cur.execute(
            f'INSERT INTO meals (user_id, date, {meal_type}) VALUES (?, ?, ?)', (user_id, date_str, text))
    conn.commit()
    conn.close()


def save_stool(user_id, quality, date_str):
    """Сохраняет оценку стула (перезаписывает, если за эту дату уже была)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO stools (user_id, date, quality) VALUES (?, ?, ?)',
                (user_id, date_str, quality))
    conn.commit()
    conn.close()


def get_bristol_scale():
    """Возвращает все записи из справочника Bristol (id, description)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, description FROM bristol_scale ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows
