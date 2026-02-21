import io
from datetime import datetime, date
import pandas as pd
from config import DATE_FORMAT_STORAGE, DATE_FORMAT_DISPLAY
from db.repositories import fetch_all_for_report


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
    if isinstance(date_value, datetime):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    if isinstance(date_value, date):
        return date_value.strftime(DATE_FORMAT_DISPLAY)
    dt = datetime.strptime(str(date_value), DATE_FORMAT_STORAGE)
    return dt.strftime(DATE_FORMAT_DISPLAY)


def generate_user_report_xlsx(user_id: int) -> io.BytesIO:
    data = fetch_all_for_report(user_id)
    meals = data['meals']
    medicines = data['medicines']
    stools = data['stools']
    feelings = data['feelings']

    dates = sorted(set(
        [m['date'] for m in meals] +
        [m['date'] for m in medicines] +
        [s['date'] for s in stools] +
        [f['date'] for f in feelings]
    ))

    by_date_meals, by_date_meds, by_date_stools, by_date_feelings = {}, {}, {}, {}
    for m in meals:
        by_date_meals.setdefault(m['date'], []).append(m)
    for m in medicines:
        by_date_meds.setdefault(m['date'], []).append(m)
    for s in stools:
        by_date_stools.setdefault(s['date'], []).append(s)
    for f in feelings:
        by_date_feelings.setdefault(f['date'], []).append(f)

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
            meds_list.append(f'{nm} {ds}'.strip())

        stool_list = []
        for s in by_date_stools.get(d, []):
            q = int(s['quality'])
            stool_list.append(f'{q} — {BRISTOL.get(q, "неизвестно")}')

        feeling_list = [f['description'] for f in by_date_feelings.get(d, [])]

        rows.append([
            _to_display(d),
            breakfast,
            lunch,
            dinner,
            len(snacks),
            '; '.join(snacks),
            len(meds_list),
            '; '.join(meds_list),
            len(stool_list),
            '; '.join(stool_list),
            '; '.join(feeling_list),
        ])

    df = pd.DataFrame(rows, columns=[
        'Дата', 'Завтрак', 'Обед', 'Ужин',
        'Количество перекусов', 'Перекусы',
        'Количество лекарств', 'Лекарства',
        'Количество походов в туалет', 'Качество стула',
        'Самочувствие'
    ])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Статистика')
    output.seek(0)
    return output
