from datetime import datetime
from config import MAX_TEXT_LENGTH


def validate_text(value: str) -> str:
    v = (value or '').strip()
    if not v:
        raise ValueError('Пустой текст')
    if len(v) > MAX_TEXT_LENGTH:
        raise ValueError(
            f'Слишком длинный текст (>{MAX_TEXT_LENGTH} символов)')
    return v


def validate_time_hhmm(value: str) -> bool:
    try:
        datetime.strptime(value, '%H:%M')
        return True
    except ValueError:
        return False


def validate_stool_quality(value: str) -> int:
    s = (value or '').strip()
    if not s.isdigit():
        raise ValueError('Введите число от 0 до 7.')
    q = int(s)
    if not (0 <= q <= 7):
        raise ValueError('Введите число от 0 до 7.')
    return q
