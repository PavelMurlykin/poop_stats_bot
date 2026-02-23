import io
from datetime import date, datetime

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from config import DATE_FORMAT_DISPLAY, DATE_FORMAT_STORAGE
from db.repositories import fetch_all_for_report

DATE_COLUMN_INDEXES = {1}
NUMBER_COLUMN_INDEXES = {5, 7, 9, 12}
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
    12: COUNT_COLUMN_WIDTH,
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
    """To display."""
    if isinstance(date_value, datetime):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    if isinstance(date_value, date):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    dt = datetime.strptime(str(date_value), DATE_FORMAT_STORAGE)
    return dt.strftime(DATE_FORMAT_DISPLAY)


def _apply_worksheet_style(worksheet,
                           total_rows: int,
                           total_columns: int
                           ) -> None:
    """Apply table style for readability in exported report."""
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

    for row in worksheet.iter_rows(min_row=1,
                                   max_row=total_rows,
                                   min_col=1,
                                   max_col=total_columns
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
    """Generate user report xlsx."""
    data = fetch_all_for_report(user_id)
    meals = data['meals']
    medicines = data['medicines']
    stools = data['stools']
    feelings = data['feelings']
    water = data['water']

    dates = sorted(set(
        [m['date'] for m in meals] +
        [m['date'] for m in medicines] +
        [s['date'] for s in stools] +
        [f['date'] for f in feelings] +
        [w['date'] for w in water]
    ))

    by_date_meals = {}
    by_date_meds = {}
    by_date_stools = {}
    by_date_feelings = {}
    by_date_water = {}
    for m in meals:
        by_date_meals.setdefault(m['date'], []).append(m)
    for m in medicines:
        by_date_meds.setdefault(m['date'], []).append(m)
    for s in stools:
        by_date_stools.setdefault(s['date'], []).append(s)
    for f in feelings:
        by_date_feelings.setdefault(f['date'], []).append(f)
    for w in water:
        by_date_water[w['date']] = int(w['glasses_count'])

    rows = []
    for d in dates:
        breakfast = lunch = dinner = ''
        snacks = []
        for m in by_date_meals.get(d, []):
            if m['meal_type'] == 'breakfast':
                breakfast = m['description']
            elif m['meal_type'] == 'lunch':
                lunch = m['description']
            elif m['meal_type'] == 'dinner':
                dinner = m['description']
            elif m['meal_type'] == 'snack':
                snacks.append(m['description'])

        meds_list = []
        for med in by_date_meds.get(d, []):
            nm = med['name']
            ds = (med.get('dosage') or '').strip()
            meds_list.append(f'{nm} ({ds})'.strip())

        stool_list = []
        for s in by_date_stools.get(d, []):
            q = int(s['quality'])
            stool_list.append(f'{q} — {BRISTOL.get(q, 'неизвестно')}')

        feeling_list = [f['description'] for f in by_date_feelings.get(d, [])]

        rows.append([
            _to_display(d),
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
            by_date_water.get(d, 0),
        ])

    df = pd.DataFrame(rows, columns=[
        'Дата', 'Завтрак', 'Обед', 'Ужин',
        'Количество перекусов', 'Перекусы',
        'Количество приемов лекарств', 'Лекарства',
        'Количество походов в туалет', 'Качество стула',
        'Самочувствие', 'Стаканов воды'
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Статистика')
        worksheet = writer.sheets['Статистика']
        _apply_worksheet_style(
            worksheet,
            total_rows=len(df.index) + 1,
            total_columns=len(df.columns),
        )
    output.seek(0)
    return output
