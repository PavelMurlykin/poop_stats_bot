import io
import sqlite3
import pandas as pd
from datetime import datetime

from db import (
    get_meals_for_day,
    get_medicines_for_day,
    get_stools_for_day,
    get_feelings_for_day,
    get_bristol_scale,
    DB_PATH
)


def generate_user_report(user_id):
    """
    Генерирует Excel-отчёт по всем дням пользователя.

    Столбцы:
        Дата, Завтрак, Обед, Ужин, Количество перекусов, Перекусы,
        Количество лекарств, Лекарства, Количество походов в туалет,
        Качество стула, Самочувствие
    """
    bristol = dict(get_bristol_scale())

    # Собираем все уникальные даты из всех таблиц
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    dates = set()

    cur.execute("SELECT DISTINCT date FROM meals WHERE user_id = ?", (user_id,))
    dates.update(row['date'] for row in cur.fetchall())

    cur.execute(
        "SELECT DISTINCT date FROM medicines WHERE user_id = ?", (user_id,))
    dates.update(row['date'] for row in cur.fetchall())

    cur.execute("SELECT DISTINCT date FROM stools WHERE user_id = ?", (user_id,))
    dates.update(row['date'] for row in cur.fetchall())

    cur.execute(
        "SELECT DISTINCT date FROM feelings WHERE user_id = ?", (user_id,))
    dates.update(row['date'] for row in cur.fetchall())

    conn.close()

    # Универсальная функция для преобразования строки даты в объект datetime
    def parse_date(date_str):
        for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Неизвестный формат даты: {date_str}")

    # Сортируем даты, используя парсер
    sorted_dates = sorted(dates, key=parse_date)

    rows = []

    for date_str in sorted_dates:
        # Преобразуем дату в единый формат ДД.ММ.ГГГГ для отображения
        dt_obj = parse_date(date_str)
        display_date = dt_obj.strftime('%d.%m.%Y')

        meals = get_meals_for_day(user_id, date_str)

        breakfast = ''
        lunch = ''
        dinner = ''
        snacks = []

        for m in meals:
            meal_type = m['meal_type']
            desc = m['description']
            if meal_type == 'завтрак':
                breakfast = desc
            elif meal_type == 'обед':
                lunch = desc
            elif meal_type == 'ужин':
                dinner = desc
            elif meal_type == 'перекус':
                snacks.append(desc)

        snacks_count = len(snacks)
        snacks_str = '; '.join(snacks) if snacks else ''

        medicines = get_medicines_for_day(user_id, date_str)
        medicines_count = len(medicines)
        medicines_list = []
        for med in medicines:
            name = med['name']
            dosage = med['dosage'] if med['dosage'] else ''
            medicines_list.append(f"{name} {dosage}".strip())
        medicines_str = '; '.join(medicines_list) if medicines_list else ''

        stools = get_stools_for_day(user_id, date_str)
        stools_count = len(stools)
        stools_list = []
        for s in stools:
            quality = s['quality']
            desc = bristol.get(quality, 'неизвестно')
            stools_list.append(f"{quality} — {desc}")
        stools_str = '; '.join(stools_list) if stools_list else ''

        feelings = get_feelings_for_day(user_id, date_str)
        feelings_list = [f['description'] for f in feelings]
        feelings_str = '; '.join(feelings_list) if feelings_list else ''

        rows.append([
            display_date,
            breakfast,
            lunch,
            dinner,
            snacks_count,
            snacks_str,
            medicines_count,
            medicines_str,
            stools_count,
            stools_str,
            feelings_str
        ])

    df = pd.DataFrame(rows, columns=[
        'Дата',
        'Завтрак',
        'Обед',
        'Ужин',
        'Количество перекусов',
        'Перекусы',
        'Количество лекарств',
        'Лекарства',
        'Количество походов в туалет',
        'Качество стула',
        'Самочувствие'
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Статистика')
    output.seek(0)

    return output
