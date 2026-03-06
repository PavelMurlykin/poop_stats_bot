"""Набор валидаторов пользовательского ввода."""

from datetime import datetime

from config import DATE_FORMAT_DISPLAY, DATE_FORMAT_STORAGE, MAX_TEXT_LENGTH


def validate_text(value: str) -> str:
    """Проверяет и нормализует текстовое поле свободного ввода.

    Args:
        value: Сырой текст, полученный от пользователя.

    Returns:
        str: Обрезанный по краям и валидный текст.

    Raises:
        ValueError: Если текст пустой или длиннее разрешённого лимита.
    """
    normalized_text = (value or '').strip()
    if not normalized_text:
        raise ValueError('Пустой текст')
    if len(normalized_text) > MAX_TEXT_LENGTH:
        raise ValueError(
            f'Слишком длинный текст (>{MAX_TEXT_LENGTH} символов)'
        )
    return normalized_text


def validate_time_hhmm(value: str) -> bool:
    """Проверяет, что значение является временем в формате `ЧЧ:ММ`.

    Args:
        value: Строка с предполагаемым временем.

    Returns:
        bool: `True`, если время успешно распарсено, иначе `False`.
    """
    try:
        datetime.strptime(value, '%H:%M')
        return True
    except ValueError:
        return False


def validate_stool_quality(value: str) -> int:
    """Проверяет оценку по Бристольской шкале и возвращает число 0..7.

    Args:
        value: Строка, которую пользователь ввёл как оценку.

    Returns:
        int: Числовая оценка качества стула.

    Raises:
        ValueError: Если значение не является целым числом диапазона 0..7.
    """
    normalized_quality_text = (value or '').strip()
    if not normalized_quality_text.isdigit():
        raise ValueError('Введите число от 0 до 7.')
    quality_value = int(normalized_quality_text)
    if not 0 <= quality_value <= 7:
        raise ValueError('Введите число от 0 до 7.')
    return quality_value


def validate_date_display(value: str) -> str:
    """Преобразует пользовательскую дату `ДД.ММ.ГГГГ` в формат БД.

    Args:
        value: Дата в пользовательском формате отображения.

    Returns:
        str: Дата в формате хранения `ГГГГ-ММ-ДД`.

    Raises:
        ValueError: Если дата не соответствует ожидаемому формату.
    """
    normalized_value = (value or '').strip()
    try:
        return datetime.strptime(
            normalized_value,
            DATE_FORMAT_DISPLAY,
        ).strftime(DATE_FORMAT_STORAGE)
    except ValueError as error:
        raise ValueError(
            'Введите дату в формате ДД.ММ.ГГГГ.'
        ) from error
