"""Фабрики inline-клавиатур для интерфейса Telegram-бота."""

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


def _build_markup(
    buttons: list[tuple[str, str]],
    row_width: int = 2,
) -> InlineKeyboardMarkup:
    """Создаёт `InlineKeyboardMarkup` из списка пар `текст/callback`.

    Args:
        buttons: Последовательность кнопок в формате `(label, callback_data)`.
        row_width: Количество кнопок в одной строке.

    Returns:
        InlineKeyboardMarkup: Готовая клавиатура для Telegram-сообщения.
    """
    keyboard_markup = InlineKeyboardMarkup(row_width=row_width)
    keyboard_markup.add(
        *[
            InlineKeyboardButton(text=label, callback_data=callback_data)
            for label, callback_data in buttons
        ]
    )
    return keyboard_markup


def main_menu() -> InlineKeyboardMarkup:
    """Возвращает главное меню с ключевыми сценариями бота."""
    return _build_markup(
        [
            ('⏰ Расписание', 'show_timetable'),
            ('📊 Бристольская шкала', 'bristol'),
            ('➕ Добавить событие', 'manual_menu'),
            ('📋 Дневная статистика', 'show_today'),
            ('🗓 Статистика за дату', 'show_stats_by_date'),
            ('📥 Полная статистика', 'export_all_stats'),
            ('❓ Помощь', 'help'),
        ]
    )


def back_to_main() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой возврата в главное меню."""
    return _build_markup([('◀ Назад', 'back_to_main')], row_width=1)


def edit_timetable_menu() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру редактирования времени напоминаний."""
    return _build_markup(
        [
            ('🍳 Завтрак', 'set_time_breakfast'),
            ('🍲 Обед', 'set_time_lunch'),
            ('🍽️ Ужин', 'set_time_dinner'),
            ('🚽 Туалет', 'set_time_toilet'),
            ('🌅 Подъём', 'set_time_wakeup'),
            ('🌙 Отход ко сну', 'set_time_bed'),
            ('◀ Назад', 'back_to_main'),
        ]
    )


def manual_menu() -> InlineKeyboardMarkup:
    """Возвращает меню быстрого добавления пользовательских записей."""
    return _build_markup(
        [
            ('🍳 Завтрак', 'manual_meal_breakfast'),
            ('🍲 Обед', 'manual_meal_lunch'),
            ('🍽️ Ужин', 'manual_meal_dinner'),
            ('🍪 Перекус', 'manual_meal_snack'),
            ('💧 Стакан воды', 'manual_water'),
            ('💊 Лекарство', 'manual_medicine'),
            ('🚽 Туалет', 'manual_stool'),
            ('😊 Самочувствие', 'manual_feeling'),
            ('🛌 Качество сна', 'manual_sleep_quality'),
            ('◀ Назад', 'back_to_main'),
        ]
    )


def confirm_delete(
    item_type: str,
    item_id: int,
    date_iso: str | None = None,
) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру подтверждения удаления записи.

    Args:
        item_type: Тип удаляемой сущности (`meal`, `med`, `stool`, `feeling`).
        item_id: Идентификатор удаляемой записи.
        date_iso: Дата экрана статистики в формате хранения `YYYY-MM-DD`.

    Returns:
        InlineKeyboardMarkup: Клавиатура с подтверждением удаления.
    """
    callback_data = f'confirm_delete:{item_type}:{item_id}'
    if date_iso:
        callback_data += f':{date_iso}'
    return _build_markup(
        [
            ('✅ Да, удалить', callback_data),
            ('❌ Нет', 'cancel_delete'),
        ]
    )
