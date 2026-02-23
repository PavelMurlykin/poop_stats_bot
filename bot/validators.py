from datetime import datetime

from config import MAX_TEXT_LENGTH


def validate_text(value: str) -> str:
    """
    Выполняет операцию `validate_text` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        value: Входное значение для проверки или обработки.

    Returns:
        str: Результат выполнения функции.
    """
    normalized_text = (value or '').strip()
    if not normalized_text:
        raise ValueError('Пустой текст')
    if len(normalized_text) > MAX_TEXT_LENGTH:
        raise ValueError(
            f'Слишком длинный текст (>{MAX_TEXT_LENGTH} символов)')
    return normalized_text


def validate_time_hhmm(value: str) -> bool:
    """
    Выполняет операцию `validate_time_hhmm` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        value: Входное значение для проверки или обработки.

    Returns:
        bool: Результат выполнения функции.
    """
    try:
        datetime.strptime(value, '%H:%M')
        return True
    except ValueError:
        return False


def validate_stool_quality(value: str) -> int:
    """
    Выполняет операцию `validate_stool_quality` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        value: Входное значение для проверки или обработки.

    Returns:
        int: Результат выполнения функции.
    """
    normalized_quality_text = (value or '').strip()
    if not normalized_quality_text.isdigit():
        raise ValueError('Введите число от 0 до 7.')
    quality_value = int(normalized_quality_text)
    if not (0 <= quality_value <= 7):
        raise ValueError('Введите число от 0 до 7.')
    return quality_value
