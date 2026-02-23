from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    """Главное меню."""
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
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
    return m


def back_to_main() -> InlineKeyboardMarkup:
    """Меню - Вернуться в главное меню."""
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton('◀ Назад', callback_data='back_to_main'))
    return m


def edit_timetable_menu() -> InlineKeyboardMarkup:
    """Меню - Изменить расписание."""
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton('🍳 Завтрак', callback_data='set_time_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='set_time_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='set_time_dinner'),
        InlineKeyboardButton('🚽 Туалет', callback_data='set_time_toilet'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main'),
    )
    return m


def manual_menu() -> InlineKeyboardMarkup:
    """Меню - Ручное добавление событий."""
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton(
            '🍳 Завтрак', callback_data='manual_meal_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='manual_meal_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='manual_meal_dinner'),
        InlineKeyboardButton('🍪 Перекус', callback_data='manual_meal_snack'),
        InlineKeyboardButton('💧 Стакан воды', callback_data='manual_water'),
        InlineKeyboardButton('💊 Лекарство', callback_data='manual_medicine'),
        InlineKeyboardButton('🚽 Туалет', callback_data='manual_stool'),
        InlineKeyboardButton('😊 Самочувствие', callback_data='manual_feeling'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main'),
    )
    return m


def confirm_delete(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    """Меню - Подтвердить удаление."""
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton(
            '✅ Да, удалить',
            callback_data=f'confirm_delete:{item_type}:{item_id}'),
        InlineKeyboardButton(
            '❌ Нет',
            callback_data='cancel_delete'),
    )
    return m
