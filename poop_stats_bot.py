import os
import pytz
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from export import generate_user_report

import telebot
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from db import (
    create_tables,
    register_user,
    get_user_times,
    update_user_time,
    get_all_users,
    is_notification_sent,
    mark_notification_sent,
    get_meal_types,
    save_meal,
    get_meals_for_day,
    update_meal_description,
    delete_meal,
    save_medicine,
    get_medicines_for_day,
    update_medicine,
    delete_medicine,
    save_stool,
    get_stools_for_day,
    update_stool,
    delete_stool,
    save_feeling,
    get_feelings_for_day,
    update_feeling,
    delete_feeling,
    get_bristol_scale
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TIMEOUT = 30
DATE_FORMAT = '%d.%m.%Y'
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Глобальные состояния
pending_lock = threading.Lock()
pending = {}          # ответы на вопросы
awaiting_time = {}    # ввод времени для расписания

# Дополнительные состояния для ручного ввода
manual_input = {}     # {user_id: {'action': ..., 'step': ...}}

# Кэш типов приёмов пищи
MEAL_TYPES = None


def load_meal_types():
    """Загружает справочник типов еды и сохраняет в глобальную переменную."""
    global MEAL_TYPES
    if MEAL_TYPES is None:
        MEAL_TYPES = dict(get_meal_types())
    return MEAL_TYPES


# ------------------- Функция для фоновой отправки отчёта -------------------
def generate_and_send_report(user_id):
    """Генерирует отчёт в фоне и отправляет пользователю."""
    try:
        excel_file = generate_user_report(user_id)
        bot.send_document(
            user_id,
            excel_file,
            visible_file_name=f'Статистика_{datetime.now(MOSCOW_TZ).strftime("%Y%m%d_%H%M%S")}.xlsx',
            caption='📊 Ваша полная статистика'
        )
    except Exception as e:
        bot.send_message(user_id, f'❌ Ошибка при формировании отчёта: {e}')


# ------------------- Клавиатуры -------------------
def main_menu():
    """Главное меню."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('⏰ Расписание', callback_data='show_timetable'),
        InlineKeyboardButton('📊 Бристольская шкала', callback_data='bristol'),
        InlineKeyboardButton('➕ Добавить событие',
                             callback_data='manual_menu'),
        InlineKeyboardButton('📋 Дневная статистика',
                             callback_data='show_today'),
        InlineKeyboardButton('📥 Полная статистика',
                             callback_data='export_all_stats'),
        InlineKeyboardButton('❓ Помощь', callback_data='help')
    )
    return markup


def edit_timetable_menu():
    """Изменение расписания."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('🍳 Завтрак', callback_data='set_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='set_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='set_dinner'),
        InlineKeyboardButton('🚽 Туалет', callback_data='set_toilet'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main')
    )
    return markup


def manual_menu_keyboard():
    """Меню ручного ввода события."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton('🍳 Завтрак', callback_data='manual_breakfast'),
        InlineKeyboardButton('🍲 Обед', callback_data='manual_lunch'),
        InlineKeyboardButton('🍽️ Ужин', callback_data='manual_dinner'),
        InlineKeyboardButton('🍪 Перекус', callback_data='manual_snack'),
        InlineKeyboardButton('💊 Лекарство', callback_data='manual_medicine'),
        InlineKeyboardButton('🚽 Стул', callback_data='manual_stool'),
        InlineKeyboardButton(
            '😊 Самочувствие', callback_data='manual_feeling'),
        InlineKeyboardButton('◀ Назад', callback_data='back_to_main')
    )
    return markup


def back_button():
    """Кнопка возврата в главное меню."""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton('◀ Назад', callback_data='back_to_main'))
    return markup


def edit_delete_keyboard(item_type, item_id):
    """Клавиатура для редактирования/удаления записи."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            '✏️ Редактировать',
            callback_data=f'edit_{item_type}_{item_id}'
        ),
        InlineKeyboardButton(
            '❌ Удалить',
            callback_data=f'delete_{item_type}_{item_id}'
        ),
        InlineKeyboardButton('◀ Назад', callback_data='show_today')
    )
    return markup


# ------------------- Отправка вопросов (уведомления) -------------------
def send_breakfast_question(user_id):
    bot.send_message(
        user_id,
        '🍳 Что вы ели на завтрак?',
        reply_markup=back_button()
    )
    with pending_lock:
        pending[user_id] = {
            'type': 'breakfast',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def send_lunch_question(user_id):
    bot.send_message(
        user_id,
        '🍲 Что вы ели на обед?',
        reply_markup=back_button()
    )
    with pending_lock:
        pending[user_id] = {
            'type': 'lunch',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def send_dinner_question(user_id):
    bot.send_message(
        user_id,
        '🍽️ Что вы ели на ужин?',
        reply_markup=back_button()
    )
    with pending_lock:
        pending[user_id] = {
            'type': 'dinner',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def send_toilet_question(user_id):
    scale = get_bristol_scale()
    text = '🚽 Оцените качество стула по Бристольской шкале:\n\n'
    for id_, desc in scale:
        text += f'{id_} — {desc}\n'
    text += '\nВведите цифру от 0 до 7:'

    bot.send_message(
        user_id,
        text,
        parse_mode='HTML',
        reply_markup=back_button()
    )

    with pending_lock:
        pending[user_id] = {
            'type': 'toilet',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


# ------------------- Планировщик уведомлений -------------------
def scheduler():
    """Фоновый поток: проверка времени и отправка вопросов."""
    while True:
        now = datetime.now(MOSCOW_TZ)
        current_time = now.strftime('%H:%M')
        current_date = now.strftime(DATE_FORMAT)

        for user in get_all_users():
            user_id = user[0]
            bt, lt, dt, tt = user[1], user[2], user[3], user[4]

            if (bt == current_time and
                    not is_notification_sent(user_id, 'breakfast', current_date)):
                send_breakfast_question(user_id)
                mark_notification_sent(user_id, 'breakfast', current_date)

            if (lt == current_time and
                    not is_notification_sent(user_id, 'lunch', current_date)):
                send_lunch_question(user_id)
                mark_notification_sent(user_id, 'lunch', current_date)

            if (dt == current_time and
                    not is_notification_sent(user_id, 'dinner', current_date)):
                send_dinner_question(user_id)
                mark_notification_sent(user_id, 'dinner', current_date)

            if (tt == current_time and
                    not is_notification_sent(user_id, 'toilet', current_date)):
                send_toilet_question(user_id)
                mark_notification_sent(user_id, 'toilet', current_date)

        time.sleep(TIMEOUT)


# ------------------- Обработчики команд -------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    register_user(user_id)
    load_meal_types()
    bot.send_message(
        user_id,
        '👋 Привет! Я помогу отслеживать связь между питанием и стулом.\n'
        'Я буду присылать вопросы в установленное время.\n'
        'Используй кнопки ниже для настройки и ручного ввода.',
        reply_markup=main_menu()
    )


@bot.message_handler(commands=['menu'])
def cmd_menu(message):
    bot.send_message(
        message.from_user.id,
        'Главное меню:',
        reply_markup=main_menu()
    )


@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    with pending_lock:
        cleared = False
        if user_id in pending:
            del pending[user_id]
            cleared = True
        if user_id in awaiting_time:
            del awaiting_time[user_id]
            cleared = True
        if user_id in manual_input:
            del manual_input[user_id]
            cleared = True
    if cleared:
        bot.reply_to(
            message,
            '✅ Ожидание отменено.',
            reply_markup=main_menu()
        )
    else:
        bot.reply_to(
            message,
            '❌ Нет активного ожидания.',
            reply_markup=main_menu()
        )


@bot.message_handler(commands=['help'])
def cmd_help(message):
    text = (
        '📋 <b>Доступные команды:</b>\n'
        '/menu — главное меню\n'
        '/cancel — отменить текущее ожидание\n'
        'Все функции доступны через кнопки.'
    )
    bot.send_message(
        message.from_user.id,
        text,
        parse_mode='HTML',
        reply_markup=back_button()
    )


# ------------------- Обработчики колбэков -------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    # Возврат в главное меню
    if data == 'back_to_main':
        bot.edit_message_text(
            'Главное меню:',
            user_id,
            call.message.message_id,
            reply_markup=main_menu()
        )
        return

    # Показать настройки времени
    if data == 'show_timetable':
        times = get_user_times(user_id)
        if times:
            breakfast_time, lunch_time, dinner_time, toilet_time = times
            text = (
                f'⏰ <b>Твоё расписание:</b>\n'
                f'Завтрак: {breakfast_time}\n'
                f'Обед:    {lunch_time}\n'
                f'Ужин:    {dinner_time}\n'
                f'Туалет:  {toilet_time}\n'
                f'\nЕсли хочешь изменить время,\n'
                f'нажми соответствующую кнопку:'
            )
        else:
            text = '❌ Ты не зарегистрирован. Напиши /start'
        bot.edit_message_text(
            text,
            user_id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=edit_timetable_menu()
        )
        return

    # Бристольская шкала
    if data == 'bristol':
        scale = get_bristol_scale()
        text = '📊 <b>Бристольская шкала:</b>\n'
        for id_, desc in scale:
            text += f'{id_} — {desc}\n'
        bot.edit_message_text(
            text,
            user_id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    # Помощь
    if data == 'help':
        text = (
            '📋 <b>Доступные действия:</b>\n'
            '• Настройка времени приёмов пищи и похода в туалет\n'
            '• Просмотр и редактирование записей'
        )
        bot.edit_message_text(
            text,
            user_id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=back_button()
        )
        return

    # Меню ручного ввода
    if data == 'manual_menu':
        bot.edit_message_text(
            '➕ Добавить событие: выберите тип записи',
            user_id,
            call.message.message_id,
            reply_markup=manual_menu_keyboard()
        )
        return

    # Показать записи за сегодня
    if data == 'show_today':
        show_today_entries(user_id, call.message.message_id)
        return

    # Обработка кнопок ручного ввода
    if data.startswith('manual_'):
        action = data.replace('manual_', '')
        handle_manual_start(user_id, call.message.message_id, action)
        return

    # Обработка редактирования/удаления
    if data.startswith('edit_'):
        parts = data.split('_', 2)
        if len(parts) == 3:
            _, item_type, item_id = parts
            start_editing(user_id, call.message.message_id, item_type, item_id)
        return

    if data.startswith('delete_'):
        parts = data.split('_', 2)
        if len(parts) == 3:
            _, item_type, item_id = parts
            confirm_delete(user_id, call.message.message_id,
                           item_type, item_id)
        return

    if data.startswith('confirm_delete_'):
        parts = data.split('_', 2)
        if len(parts) == 3:
            _, item_type, item_id = parts
            perform_delete(call, user_id, call.message.message_id,
                           item_type, item_id)
        return

    if data == 'cancel_delete':
        bot.edit_message_text(
            'Удаление отменено.',
            user_id,
            call.message.message_id,
            reply_markup=back_button()
        )
        return

    # Установка времени из главного меню
    if data in ('set_breakfast', 'set_lunch', 'set_dinner', 'set_toilet'):
        meal_type = data.replace('set_', '')
        meal_names = {
            'breakfast': ('завтрака', '08:00'),
            'lunch': ('обеда', '13:00'),
            'dinner': ('ужина', '19:00'),
            'toilet': ('туалета', '09:00')
        }
        name, example = meal_names[meal_type]
        bot.send_message(
            user_id,
            f'Введите время <b>{name}</b> в формате ЧЧ:ММ (например, {example}):',
            parse_mode='HTML'
        )
        with pending_lock:
            awaiting_time[user_id] = meal_type
        bot.edit_message_reply_markup(
            user_id,
            call.message.message_id,
            reply_markup=None
        )
        return

    # Экспорт всей статистики
    if data == 'export_all_stats':
        bot.answer_callback_query(call.id, text="Начинаю подготовку отчёта...")
        bot.send_message(
            user_id, "🔄 Формирую отчёт, это может занять некоторое время. Я сообщу, когда он будет готов.")
        thread = threading.Thread(
            target=generate_and_send_report, args=(user_id,))
        thread.daemon = True
        thread.start()
        return


# ------------------- Функции для ручного ввода и просмотра -------------------
def show_today_entries(user_id, message_id):
    """Показывает все записи за сегодня и даёт кнопки для редактирования."""
    today = datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
    meals = get_meals_for_day(user_id, today)
    medicines = get_medicines_for_day(user_id, today)
    stools = get_stools_for_day(user_id, today)
    feelings = get_feelings_for_day(user_id, today)
    bristol_scale = dict(get_bristol_scale())

    text = f'📋 <b>Записи за {today}</b>\n\n'

    if not meals and not medicines and not stools and not feelings:
        text += 'За сегодня записей нет.'
    else:
        if meals:
            text += '<b>🍽️ Приёмы пищи:</b>\n'
            for m in meals:
                text += (
                    f'• <b>{m["meal_type"]}</b>: {m["description"]}'
                    f' (ред.: /edit_meal_{m["id"]})\n'
                )
        if medicines:
            text += '\n<b>💊 Лекарства:</b>\n'
            for med in medicines:
                text += (
                    f'• {med["name"]} {med["dosage"]}'
                    f' (ред.: /edit_med_{med["id"]})\n'
                )
        if stools:
            text += '\n<b>🚽 Стул:</b>\n'
            for s in stools:
                description = bristol_scale.get(s['quality'], 'неизвестно')
                text += (
                    f'• {s["quality"]} — {description}'
                    f' (ред.: /edit_stool_{s["id"]})\n'
                )
        if feelings:
            text += '\n<b>😊 Самочувствие:</b>\n'
            for f in feelings:
                text += (
                    f'• {f["description"]}'
                    f' (ред.: /edit_feeling_{f["id"]})\n'
                )

    # Кнопки для редактирования (через колбэки)
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton('◀ Назад', callback_data='back_to_main'))
    bot.edit_message_text(
        text,
        user_id,
        message_id,
        parse_mode='HTML',
        reply_markup=markup
    )


def handle_manual_start(user_id, message_id, action):
    """Начинает процесс ручного ввода для указанного действия."""
    mt = load_meal_types()

    if action == 'breakfast':
        meal_type_id = next(k for k, v in mt.items() if v == 'завтрак')
        start_manual_meal(user_id, message_id, meal_type_id)
    elif action == 'lunch':
        meal_type_id = next(k for k, v in mt.items() if v == 'обед')
        start_manual_meal(user_id, message_id, meal_type_id)
    elif action == 'dinner':
        meal_type_id = next(k for k, v in mt.items() if v == 'ужин')
        start_manual_meal(user_id, message_id, meal_type_id)
    elif action == 'snack':
        meal_type_id = next(k for k, v in mt.items() if v == 'перекус')
        start_manual_meal(user_id, message_id, meal_type_id)
    elif action == 'medicine':
        start_manual_medicine(user_id, message_id)
    elif action == 'stool':
        start_manual_stool(user_id, message_id)
    elif action == 'feeling':
        start_manual_feeling(user_id, message_id)


def start_manual_meal(user_id, message_id, meal_type_id):
    """Запуск ручного ввода еды: просим описание."""
    bot.edit_message_text(
        '🍽️ Введите описание блюд:',
        user_id,
        message_id
    )
    with pending_lock:
        manual_input[user_id] = {
            'step': 'wait_description',
            'action': 'meal',
            'meal_type_id': meal_type_id,
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def start_manual_medicine(user_id, message_id):
    """Запуск ручного ввода лекарства: шаг 1 — название."""
    bot.edit_message_text(
        '💊 Введите название лекарства:',
        user_id,
        message_id
    )
    with pending_lock:
        manual_input[user_id] = {
            'step': 'wait_name',
            'action': 'medicine',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def start_manual_stool(user_id, message_id):
    """Запуск ручного ввода стула: просим оценку."""
    scale = get_bristol_scale()
    text = '🚽 Оцените качество стула по Бристольской шкале:\n\n'
    for id_, desc in scale:
        text += f'{id_} — {desc}\n'
    text += '\nВведите цифру от 0 до 7:'

    bot.edit_message_text(
        text,
        user_id,
        message_id
    )

    with pending_lock:
        manual_input[user_id] = {
            'step': 'wait_quality',
            'action': 'stool',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def start_manual_feeling(user_id, message_id):
    """Запуск ручного ввода самочувствия: просим описание."""
    bot.edit_message_text(
        '😊 Опишите ваше самочувствие:',
        user_id,
        message_id
    )
    with pending_lock:
        manual_input[user_id] = {
            'step': 'wait_feeling_description',
            'action': 'feeling',
            'date': datetime.now(MOSCOW_TZ).strftime(DATE_FORMAT)
        }


def start_editing(user_id, message_id, item_type, item_id):
    """Начинает редактирование указанной записи."""
    if item_type == 'meal':
        bot.send_message(
            user_id,
            'Введите новое описание блюда:'
        )
        with pending_lock:
            manual_input[user_id] = {
                'step': 'edit_meal_desc',
                'item_id': int(item_id)
            }
    elif item_type == 'med':
        bot.send_message(
            user_id,
            'Введите новое название лекарства (или /cancel для отмены):'
        )
        with pending_lock:
            manual_input[user_id] = {
                'step': 'edit_med_name',
                'item_id': int(item_id)
            }
    elif item_type == 'stool':
        bot.send_message(
            user_id,
            'Введите новую оценку (0–7):'
        )
        with pending_lock:
            manual_input[user_id] = {
                'step': 'edit_stool_quality',
                'item_id': int(item_id)
            }
    elif item_type == 'feeling':
        bot.send_message(
            user_id,
            'Введите новое описание самочувствия:'
        )
        with pending_lock:
            manual_input[user_id] = {
                'step': 'edit_feeling_description',
                'item_id': int(item_id)
            }
    bot.edit_message_reply_markup(user_id, message_id, reply_markup=None)


def confirm_delete(user_id, message_id, item_type, item_id):
    """Запрашивает подтверждение удаления."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(
            '✅ Да, удалить',
            callback_data=f'confirm_delete_{item_type}_{item_id}'
        ),
        InlineKeyboardButton('❌ Нет', callback_data='cancel_delete')
    )
    bot.edit_message_text(
        '❓ Вы уверены, что хотите удалить эту запись?',
        user_id,
        message_id,
        reply_markup=markup
    )


def perform_delete(call, user_id, message_id, item_type, item_id):
    """Удаляет запись и показывает обновлённый список."""
    if item_type == 'meal':
        delete_meal(int(item_id))
    elif item_type == 'med':
        delete_medicine(int(item_id))
    elif item_type == 'stool':
        delete_stool(int(item_id))
    elif item_type == 'feeling':
        delete_feeling(int(item_id))
    bot.answer_callback_query(call.id, text='Запись удалена')
    show_today_entries(user_id, message_id)


# ------------------- Обработчик текстовых сообщений -------------------
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    # Проверяем, не ждём ли мы ввод времени (настройка расписания)
    with pending_lock:
        if user_id in awaiting_time:
            meal_type = awaiting_time.pop(user_id)
            meal_names = {
                'breakfast': 'завтрака',
                'lunch': 'обеда',
                'dinner': 'ужина',
                'toilet': 'туалета'
            }
            name = meal_names.get(meal_type, meal_type)
            # Проверка формата
            try:
                datetime.strptime(text, '%H:%M')
            except ValueError:
                bot.reply_to(
                    message,
                    '❌ Неверный формат. Введите время в формате ЧЧ:ММ.',
                    reply_markup=main_menu()
                )
                return
            if update_user_time(user_id, meal_type, text):
                bot.reply_to(
                    message,
                    f'✅ Время <b>{name}</b> установлено на <b>{text}</b>.',
                    parse_mode='HTML',
                    reply_markup=main_menu()
                )
            else:
                bot.reply_to(
                    message,
                    '❌ Ошибка при сохранении.',
                    reply_markup=main_menu()
                )
            return

        # Проверяем, не находимся ли мы в процессе ручного ввода
        if user_id in manual_input:
            state = manual_input[user_id]
            step = state['step']

            # Ручной ввод еды
            if step == 'wait_description' and state['action'] == 'meal':
                save_meal(
                    user_id,
                    state['meal_type_id'],
                    text,
                    state['date']
                )
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Запись о приёме пищи сохранена.',
                    reply_markup=main_menu()
                )
                return

            # Ручной ввод лекарства
            if state['action'] == 'medicine':
                if step == 'wait_name':
                    state['name'] = text
                    state['step'] = 'wait_dosage'
                    bot.reply_to(
                        message, 'Введите дозировку (или пропустите, введя «-»):')
                    return
                elif step == 'wait_dosage':
                    dosage = None if text == '-' else text
                    state['dosage'] = dosage
                    save_medicine(
                        user_id,
                        state['name'],
                        state['dosage'],
                        state['date']
                    )
                    del manual_input[user_id]
                    bot.reply_to(
                        message,
                        '✅ Лекарство добавлено.',
                        reply_markup=main_menu()
                    )
                    return

            # Ручной ввод стула
            if step == 'wait_quality' and state['action'] == 'stool':
                if not text.isdigit() or not (0 <= int(text) <= 7):
                    bot.reply_to(
                        message,
                        '❌ Пожалуйста, введите цифру от 0 до 7.'
                    )
                    return
                quality = int(text)
                state['quality'] = quality
                save_stool(
                    user_id,
                    state['quality'],
                    state['date']
                )
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Запись о стуле сохранена.',
                    reply_markup=main_menu()
                )
                return

            # Ручной ввод самочувствия
            if step == 'wait_feeling_description' and state['action'] == 'feeling':
                save_feeling(
                    user_id,
                    text,
                    state['date']
                )
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Запись о самочувствии сохранена.',
                    reply_markup=main_menu()
                )
                return

            # Редактирование записей
            if step == 'edit_meal_desc':
                update_meal_description(state['item_id'], text)
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Описание обновлено.',
                    reply_markup=main_menu()
                )
                return
            if step == 'edit_med_name':
                state['new_name'] = text
                state['step'] = 'edit_med_dosage'
                bot.reply_to(message, 'Введите новую дозировку (или «-»):')
                return
            if step == 'edit_med_dosage':
                dosage = None if text == '-' else text
                state['dosage'] = dosage
                update_medicine(
                    state['item_id'],
                    state['new_name'],
                    state['dosage']
                )
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Лекарство обновлено.',
                    reply_markup=main_menu()
                )
                return
            if step == 'edit_stool_quality':
                if not text.isdigit() or not (0 <= int(text) <= 7):
                    bot.reply_to(
                        message,
                        '❌ Введите число от 0 до 7.'
                    )
                    return
                state['new_quality'] = int(text)
                update_stool(
                    state['item_id'],
                    state['new_quality']
                )
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Запись о стуле обновлена.',
                    reply_markup=main_menu()
                )
                return
            if step == 'edit_feeling_description':
                update_feeling(state['item_id'], text)
                del manual_input[user_id]
                bot.reply_to(
                    message,
                    '✅ Запись о самочувствии обновлена.',
                    reply_markup=main_menu()
                )
                return

        # Если не ждём время и не в ручном вводе, проверяем ответ на уведомление
        if user_id not in pending:
            bot.reply_to(
                message,
                'Я не ожидаю ответа. Используй /menu для навигации.',
                reply_markup=main_menu()
            )
            return

        p = pending[user_id]
        p_type = p['type']
        p_date = p['date']

        # Ответ на вопрос о еде (завтрак/обед/ужин)
        if p_type in ('breakfast', 'lunch', 'dinner'):
            mt = load_meal_types()
            type_map = {
                'breakfast': 'завтрак',
                'lunch': 'обед',
                'dinner': 'ужин'
            }
            meal_type_name = type_map[p_type]
            meal_type_id = next(k for k, v in mt.items()
                                if v == meal_type_name)
            save_meal(user_id, meal_type_id, text, p_date)
            bot.reply_to(
                message,
                f'✅ Информация о <b>{meal_type_name}</b> сохранена.',
                parse_mode='HTML',
                reply_markup=main_menu()
            )
            del pending[user_id]

        # Ответ на вопрос о стуле
        elif p_type == 'toilet':
            if not text.isdigit() or not (0 <= int(text) <= 7):
                bot.reply_to(
                    message,
                    '❌ Пожалуйста, введите число от 0 до 7.',
                    parse_mode='HTML'
                )
                return
            quality = int(text)
            save_stool(user_id, quality, p_date)
            bot.reply_to(
                message,
                '✅ Оценка стула сохранена.',
                reply_markup=main_menu()
            )
            del pending[user_id]


# ------------------- Запуск -------------------
if __name__ == '__main__':
    create_tables()
    load_meal_types()

    scheduler_thread = threading.Thread(target=scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    print('Бот запущен...')
    bot.polling(none_stop=True, interval=0,
                timeout=30, long_polling_timeout=30)
