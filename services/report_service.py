import io
from datetime import date, datetime

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from config import DATE_FORMAT_DISPLAY, DATE_FORMAT_STORAGE
from db.repositories import fetch_all_for_report

DATE_COLUMN_INDEXES = {1}
NUMBER_COLUMN_INDEXES = {5, 7, 9, 15}
CENTERED_COLUMN_INDEXES = DATE_COLUMN_INDEXES | NUMBER_COLUMN_INDEXES

DATE_COLUMN_WIDTH = 12
COUNT_COLUMN_WIDTH = 12
SHORT_TEXT_COLUMN_WIDTH = 18
LONG_TEXT_COLUMN_WIDTH = 24
XL_TEXT_COLUMN_WIDTH = 28

COLUMN_WIDTHS = {
    1: DATE_COLUMN_WIDTH,
    2: SHORT_TEXT_COLUMN_WIDTH,
    3: SHORT_TEXT_COLUMN_WIDTH,
    4: SHORT_TEXT_COLUMN_WIDTH,
    5: COUNT_COLUMN_WIDTH,
    6: LONG_TEXT_COLUMN_WIDTH,
    7: COUNT_COLUMN_WIDTH,
    8: LONG_TEXT_COLUMN_WIDTH,
    9: COUNT_COLUMN_WIDTH,
    10: XL_TEXT_COLUMN_WIDTH,
    11: LONG_TEXT_COLUMN_WIDTH,
    12: SHORT_TEXT_COLUMN_WIDTH,
    13: SHORT_TEXT_COLUMN_WIDTH,
    14: LONG_TEXT_COLUMN_WIDTH,
    15: COUNT_COLUMN_WIDTH,
}

BRISTOL = {
    0: 'Отсутствие дефекации',
    1: 'Отдельные твёрдые комки, как орехи, трудно проходят [серьезный запор]',
    2: 'Колбасовидный, но комковатый [запор или склонность к запору]',
    3: 'Колбасовидный с трещинами на поверхности [норма]',
    4: 'Колбасовидный гладкий и мягкий [норма]',
    5: 'Мягкие маленькие шарики с чёткими краями [склонность к диарее]',
    6: 'Рыхлые кусочки с неровными краями, кашицеобразный [диарея]',
    7: 'Водянистый, без твёрдых кусочков [сильная диарея]',
}


def _to_display(date_value) -> str:
    """
    Выполняет операцию `_to_display` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        date_value: Параметр `date_value` для текущего шага обработки.

    Returns:
        str: Результат выполнения функции.
    """
    if isinstance(date_value, datetime):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    if isinstance(date_value, date):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    parsed_datetime = datetime.strptime(str(date_value), DATE_FORMAT_STORAGE)
    return parsed_datetime.strftime(DATE_FORMAT_DISPLAY)


def _apply_worksheet_style(
    worksheet,
    total_rows: int,
    total_columns: int,
) -> None:
    """
    Выполняет операцию `_apply_worksheet_style` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        worksheet: Параметр `worksheet` для текущего шага обработки.
        total_rows: Параметр `total_rows` для текущего шага обработки.
        total_columns: Параметр `total_columns` для текущего шага обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    thin = Side(style='thin', color='000000')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    header_font = Font(bold=True)
    header_alignment = Alignment(
        horizontal='center', vertical='center', wrap_text=True)
    text_alignment = Alignment(
        horizontal='left', vertical='top', wrap_text=True)
    centered_alignment = Alignment(horizontal='center', vertical='center')

    for col_idx, width in COLUMN_WIDTHS.items():
        worksheet.column_dimensions[get_column_letter(col_idx)].width = width

    worksheet.row_dimensions[1].height = 36

    for row in worksheet.iter_rows(
        min_row=1,
        max_row=total_rows,
        min_col=1,
        max_col=total_columns,
    ):
        for cell in row:
            cell.border = border
            if cell.row == 1:
                cell.font = header_font
                cell.alignment = header_alignment
            elif cell.column in CENTERED_COLUMN_INDEXES:
                cell.alignment = centered_alignment
            else:
                cell.alignment = text_alignment


def generate_user_report_xlsx(user_id: int) -> io.BytesIO:
    """
    Выполняет операцию `generate_user_report_xlsx` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        user_id: Идентификатор пользователя в Telegram.

    Returns:
        io.BytesIO: Результат выполнения функции.
    """
    data = fetch_all_for_report(user_id)
    meals = data['meals']
    medicines = data['medicines']
    stools = data['stools']
    feelings = data['feelings']
    water = data['water']
    sleeps = data['sleeps']

    dates = sorted(
        set(
            [meal['date'] for meal in meals]
            + [medicine['date'] for medicine in medicines]
            + [stool['date'] for stool in stools]
            + [feeling['date'] for feeling in feelings]
            + [water_row['date'] for water_row in water]
            + [sleep_row['date'] for sleep_row in sleeps]
        )
    )

    by_date_meals = {}
    by_date_meds = {}
    by_date_stools = {}
    by_date_feelings = {}
    by_date_water = {}
    by_date_sleep = {}

    for meal in meals:
        by_date_meals.setdefault(meal['date'], []).append(meal)
    for medicine in medicines:
        by_date_meds.setdefault(medicine['date'], []).append(medicine)
    for stool in stools:
        by_date_stools.setdefault(stool['date'], []).append(stool)
    for feeling in feelings:
        by_date_feelings.setdefault(feeling['date'], []).append(feeling)
    for water_row in water:
        by_date_water[water_row['date']] = int(water_row['glasses_count'])
    for sleep in sleeps:
        by_date_sleep[sleep['date']] = sleep

    rows = []
    for day in dates:
        breakfast = lunch = dinner = ''
        snacks = []
        for meal in by_date_meals.get(day, []):
            if meal['meal_type'] == 'breakfast':
                breakfast = meal['description']
            elif meal['meal_type'] == 'lunch':
                lunch = meal['description']
            elif meal['meal_type'] == 'dinner':
                dinner = meal['description']
            elif meal['meal_type'] == 'snack':
                snacks.append(meal['description'])

        meds_list = []
        for medicine in by_date_meds.get(day, []):
            name = medicine['name']
            dosage = (medicine.get('dosage') or '').strip()
            meds_list.append(f'{name} ({dosage})' if dosage else name)

        stool_list = []
        for stool in by_date_stools.get(day, []):
            quality = int(stool['quality'])
            stool_list.append(
                f'{quality} — {BRISTOL.get(quality, "неизвестно")}')

        feeling_list = [
            feeling['description']
            for feeling in by_date_feelings.get(day, [])
        ]

        sleep_row = by_date_sleep.get(day, {})
        sleep_wakeup = sleep_row.get('wakeup_time', '')
        sleep_bed = sleep_row.get('bed_time', '')
        sleep_quality = sleep_row.get('quality_description') or ''

        rows.append(
            [
                _to_display(day),
                breakfast,
                lunch,
                dinner,
                len(snacks),
                '; '.join(snacks),
                len(meds_list),
                '\n'.join(meds_list),
                len(stool_list),
                '\n'.join(stool_list),
                '\n'.join(feeling_list),
                sleep_wakeup,
                sleep_bed,
                sleep_quality,
                by_date_water.get(day, 0),
            ]
        )

    report_dataframe = pd.DataFrame(
        rows,
        columns=[
            'Дата',
            'Завтрак',
            'Обед',
            'Ужин',
            'Количество перекусов',
            'Перекусы',
            'Количество приемов лекарств',
            'Лекарства',
            'Количество походов в туалет',
            'Качество стула',
            'Самочувствие',
            'Сон: подъем',
            'Сон: отход ко сну',
            'Сон: качество',
            'Стаканов воды',
        ],
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        report_dataframe.to_excel(writer, index=False, sheet_name='Статистика')
        worksheet = writer.sheets['Статистика']
        _apply_worksheet_style(
            worksheet,
            total_rows=len(report_dataframe.index) + 1,
            total_columns=len(report_dataframe.columns),
        )
    output.seek(0)
    return output
