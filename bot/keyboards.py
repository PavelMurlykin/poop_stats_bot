from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    """
    Выполняет операцию `main_menu` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        InlineKeyboardMarkup: Результат выполнения функции.
    """
    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(
        InlineKeyboardButton('⏰ Расписание', callback_data='show_timetable'),
        InlineKeyboardButton('📊 Бристольская шкала', callback_data='bristol'),
        InlineKeyboardButton('➕ Добавить событие',
                             callback_data='manual_menu'),
        InlineKeyboardButton('📋 Дневная статистика',
                             callback_data='show_today'),
        InlineKeyboardButton('📥 Полная статистика',
                             callback_data='export_all_stats'),
        InlineKeyboardButton('❓ Помощь', callback_data='help'),
    )
    return keyboard_markup


def back_to_main() -> InlineKeyboardMarkup:
    """
    Выполняет операцию `back_to_main` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        InlineKeyboardMarkup: Результат выполнения функции.
    """
    keyboard_markup = InlineKeyboardMarkup()
    keyboard_markup.add(InlineKeyboardButton(
        '◀ Назад', callback_data='back_to_main'))
    return keyboard_markup


def edit_timetable_menu() -> InlineKeyboardMarkup:
    """
    Выполняет операцию `edit_timetable_menu` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        InlineKeyboardMarkup: Результат выполнения функции.
    """
    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(
        InlineKeyboardButton('🍳 Завтрак', callback_data='set_time_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='set_time_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='set_time_dinner'),
        InlineKeyboardButton('🚽 Туалет', callback_data='set_time_toilet'),
        InlineKeyboardButton('🌅 Подъём', callback_data='set_time_wakeup'),
        InlineKeyboardButton('🌙 Отход ко сну', callback_data='set_time_bed'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main'),
    )
    return keyboard_markup


def manual_menu() -> InlineKeyboardMarkup:
    """
    Выполняет операцию `manual_menu` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        InlineKeyboardMarkup: Результат выполнения функции.
    """
    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(
        InlineKeyboardButton(
            '🍳 Завтрак', callback_data='manual_meal_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='manual_meal_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='manual_meal_dinner'),
        InlineKeyboardButton('🍪 Перекус', callback_data='manual_meal_snack'),
        InlineKeyboardButton('💧 Стакан воды', callback_data='manual_water'),
        InlineKeyboardButton('💊 Лекарство', callback_data='manual_medicine'),
        InlineKeyboardButton('🚽 Туалет', callback_data='manual_stool'),
        InlineKeyboardButton('😊 Самочувствие', callback_data='manual_feeling'),
        InlineKeyboardButton(
            '🛌 Качество сна', callback_data='manual_sleep_quality'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main'),
    )
    return keyboard_markup


def confirm_delete(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    """
    Выполняет операцию `confirm_delete` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        item_type: Тип записи, над которой выполняется действие.
        item_id: Идентификатор записи в базе данных.

    Returns:
        InlineKeyboardMarkup: Результат выполнения функции.
    """
    keyboard_markup = InlineKeyboardMarkup(row_width=2)
    keyboard_markup.add(
        InlineKeyboardButton(
            '✅ Да, удалить',
            callback_data=f'confirm_delete:{item_type}:{item_id}',
        ),
        InlineKeyboardButton('❌ Нет', callback_data='cancel_delete'),
    )
    return keyboard_markup
