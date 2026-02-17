import os
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from db import (
    create_tables,
    register_user,
    get_user_times,
    update_user_time,
    get_all_users,
    is_notification_sent,
    mark_notification_sent,
    save_meal,
    save_stool,
    get_bristol_scale
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TIMEOUT = 30

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Глобальный словарь для хранения состояний ожидания ответа и ввода времени
pending_lock = threading.Lock()
pending = {}          # {user_id: {'type': 'breakfast', 'date': '2025-03-28'}}
awaiting_time = {}    # {user_id: 'breakfast'} – ждём ввод времени для типа


# ------------------- Клавиатуры -------------------
def main_menu():
    """Главное меню."""
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🍳 Завтрак", callback_data="set_breakfast"),
        InlineKeyboardButton("🍲 Обед", callback_data="set_lunch"),
        InlineKeyboardButton("🍽️ Ужин", callback_data="set_dinner"),
        InlineKeyboardButton("🚽 Туалет", callback_data="set_toilet"),
        InlineKeyboardButton("⏰ Мои настройки", callback_data="show_settings"),
        InlineKeyboardButton("📊 Бристольская шкала", callback_data="bristol"),
        InlineKeyboardButton("❓ Помощь", callback_data="help")
    )
    return markup


def back_button():
    """Кнопка возврата в главное меню."""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("◀ Назад", callback_data="back_to_main"))
    return markup


# ------------------- Отправка вопросов -------------------
def send_breakfast_question(user_id):
    bot.send_message(user_id, "🍳 Что вы ели на завтрак?")
    with pending_lock:
        pending[user_id] = {'type': 'breakfast',
                            'date': datetime.now().strftime("%Y-%m-%d")}


def send_lunch_question(user_id):
    bot.send_message(user_id, "🍲 Что вы ели на обед?")
    with pending_lock:
        pending[user_id] = {'type': 'lunch',
                            'date': datetime.now().strftime("%Y-%m-%d")}


def send_dinner_question(user_id):
    bot.send_message(user_id, "🍽️ Что вы ели на ужин?")
    with pending_lock:
        pending[user_id] = {'type': 'dinner',
                            'date': datetime.now().strftime("%Y-%m-%d")}


def send_toilet_question(user_id):
    bot.send_message(user_id,
                     "🚽 Оцените качество стула за <b>вчерашний день</b> по Бристольской шкале (0–7):\n"
                     "0 — отсутствие дефекации\n"
                     "1–7 — типы стула (введите /bristol для подробностей)\n"
                     "Пожалуйста, введите число от 0 до 7.",
                     parse_mode="HTML")
    with pending_lock:
        # Сохраняем дату ответа (сегодня) — стул привяжется к meals за вчера при анализе
        pending[user_id] = {'type': 'toilet',
                            'date': datetime.now().strftime("%Y-%m-%d")}


# ------------------- Планировщик уведомлений -------------------
def scheduler():
    """Фоновый поток: каждые 30 секунд проверяет время и отправляет вопросы."""
    while True:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        for user in get_all_users():
            user_id = user[0]
            bt, lt, dt, tt = user[1], user[2], user[3], user[4]

            if bt == current_time and not is_notification_sent(user_id, 'breakfast', current_date):
                send_breakfast_question(user_id)
                mark_notification_sent(user_id, 'breakfast', current_date)

            if lt == current_time and not is_notification_sent(user_id, 'lunch', current_date):
                send_lunch_question(user_id)
                mark_notification_sent(user_id, 'lunch', current_date)

            if dt == current_time and not is_notification_sent(user_id, 'dinner', current_date):
                send_dinner_question(user_id)
                mark_notification_sent(user_id, 'dinner', current_date)

            if tt == current_time and not is_notification_sent(user_id, 'toilet', current_date):
                send_toilet_question(user_id)
                mark_notification_sent(user_id, 'toilet', current_date)

        time.sleep(TIMEOUT)


# ------------------- Обработчики команд -------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    register_user(user_id)
    bot.send_message(user_id,
                     "👋 Привет! Я помогу отслеживать связь между питанием и стулом.\n"
                     "Я буду присылать вопросы в установленное время.\n"
                     "Используй кнопки ниже для настройки.",
                     reply_markup=main_menu())


@bot.message_handler(commands=['menu'])
def cmd_menu(message):
    """Показать главное меню."""
    bot.send_message(message.from_user.id, "Главное меню:",
                     reply_markup=main_menu())


@bot.message_handler(commands=['help'])
def cmd_help(message):
    """Помощь."""
    text = (
        "📋 <b>Доступные команды:</b>\n"
        "/menu — показать главное меню\n"
        "/cancel — отменить ожидаемый вопрос или ввод времени\n"
        "Также вы можете использовать кнопки в меню для настройки."
    )
    bot.send_message(message.from_user.id, text,
                     parse_mode="HTML", reply_markup=back_button())


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
    if cleared:
        bot.reply_to(message, "✅ Ожидание отменено.", reply_markup=main_menu())
    else:
        bot.reply_to(message, "❌ Нет активного ожидания.",
                     reply_markup=main_menu())


# Обработчики команд установки времени (для обратной совместимости)
@bot.message_handler(commands=['set_breakfast', 'set_lunch', 'set_dinner', 'set_toilet'])
def cmd_set_time(message):
    user_id = message.from_user.id
    command = message.text.split()[0]
    meal_type = command.split('_')[1]  # breakfast, lunch, dinner, toilet

    # Определяем русское название и пример для подсказки
    if meal_type == "breakfast":
        meal_name = "завтрака"
        example = "08:00"
    elif meal_type == "lunch":
        meal_name = "обеда"
        example = "13:00"
    elif meal_type == "dinner":
        meal_name = "ужина"
        example = "19:00"
    elif meal_type == "toilet":
        meal_name = "туалета"
        example = "09:00"
    else:
        meal_name = meal_type
        example = "08:00"

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(
            message, f"❌ Использование: {command} ЧЧ:ММ (например, {example})")
        return

    time_str = args[1]
    if update_user_time(user_id, meal_type, time_str):
        bot.reply_to(
            message,
            f"✅ Время <b>{meal_name}</b> установлено на <b>{time_str}</b>",
            parse_mode="HTML",
            reply_markup=main_menu()
        )
    else:
        bot.reply_to(
            message,
            "❌ Неверный формат времени. Используй ЧЧ:ММ (например, 08:00)."
        )


# ------------------- Обработчики колбэков -------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "back_to_main":
        bot.edit_message_text("Главное меню:", user_id, call.message.message_id,
                              reply_markup=main_menu())
        return

    if data == "show_settings":
        times = get_user_times(user_id)
        if times:
            bt, lt, dt, tt = times
            text = (
                f"⏰ <b>Твои настройки:</b>\n"
                f"Завтрак: {bt}\n"
                f"Обед:   {lt}\n"
                f"Ужин:   {dt}\n"
                f"Туалет: {tt}"
            )
        else:
            text = "❌ Ты не зарегистрирован. Напиши /start"
        bot.edit_message_text(text, user_id, call.message.message_id,
                              parse_mode="HTML", reply_markup=back_button())
        return

    if data == "bristol":
        scale = get_bristol_scale()
        text = "📊 <b>Бристольская шкала формы кала:</b>\n"
        for id, desc in scale:
            text += f"{id} — {desc}\n"
        bot.edit_message_text(text, user_id, call.message.message_id,
                              parse_mode="HTML", reply_markup=back_button())
        return

    if data == "help":
        text = (
            "📋 <b>Доступные команды:</b>\n"
            "/menu — показать главное меню\n"
            "/cancel — отменить ожидаемый вопрос или ввод времени\n"
            "Также вы можете использовать кнопки в меню для настройки."
        )
        bot.edit_message_text(text, user_id, call.message.message_id,
                              parse_mode="HTML", reply_markup=back_button())
        return

    if data in ("set_breakfast", "set_lunch", "set_dinner", "set_toilet"):
        meal_type = data.replace("set_", "")
        # Определяем русское название и пример времени
        if meal_type == "breakfast":
            meal_name = "завтрака"
            example = "08:00"
        elif meal_type == "lunch":
            meal_name = "обеда"
            example = "13:00"
        elif meal_type == "dinner":
            meal_name = "ужина"
            example = "19:00"
        elif meal_type == "toilet":
            meal_name = "туалета"
            example = "09:00"
        else:
            meal_name = meal_type
            example = "08:00"

        msg = bot.send_message(
            user_id,
            f"Введите время <b>{meal_name}</b> в формате ЧЧ:ММ (например, {example}):",
            parse_mode="HTML"
        )
        with pending_lock:
            awaiting_time[user_id] = meal_type
        # Редактируем исходное сообщение, чтобы убрать кнопки
        bot.edit_message_reply_markup(
            user_id, call.message.message_id, reply_markup=None)
        return


# ------------------- Обработчик текстовых сообщений -------------------
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    # Сначала проверяем, не ждём ли мы ввод времени
    with pending_lock:
        if user_id in awaiting_time:
            meal_type = awaiting_time.pop(user_id)

            # Определяем русское название для ответа
            if meal_type == "breakfast":
                meal_name = "завтрака"
            elif meal_type == "lunch":
                meal_name = "обеда"
            elif meal_type == "dinner":
                meal_name = "ужина"
            elif meal_type == "toilet":
                meal_name = "туалета"
            else:
                meal_name = meal_type

            # Проверяем формат
            try:
                datetime.strptime(text, "%H:%M")
            except ValueError:
                bot.reply_to(message,
                             "❌ Неверный формат. Введите время в формате ЧЧ:ММ (например, 08:00).",
                             reply_markup=main_menu())
                return
            # Сохраняем
            if update_user_time(user_id, meal_type, text):
                bot.reply_to(message,
                             f"✅ Время <b>{meal_name}</b> установлено на <b>{text}</b>.",
                             parse_mode="HTML", reply_markup=main_menu())
            else:
                # Эта ситуация маловероятна, т.к. мы уже проверили формат
                bot.reply_to(message, "❌ Ошибка при сохранении.",
                             reply_markup=main_menu())
            return

        # Если не ждём время, проверяем ожидание ответа на вопрос
        if user_id not in pending:
            bot.reply_to(
                message, "Я не ожидаю ответа. Используй /menu для навигации.")
            return

        p = pending[user_id]
        p_type = p['type']
        p_date = p['date']

        if p_type in ('breakfast', 'lunch', 'dinner'):
            save_meal(user_id, p_type, text, p_date)
            bot.reply_to(message, f"✅ Информация о <b>{p_type}</b> сохранена.",
                         parse_mode="HTML", reply_markup=main_menu())
            del pending[user_id]

        elif p_type == 'toilet':
            if not text.isdigit() or not (0 <= int(text) <= 7):
                bot.reply_to(message, "❌ Пожалуйста, введи <b>число от 0 до 7</b>.",
                             parse_mode="HTML")
                return
            quality = int(text)
            save_stool(user_id, quality, p_date)
            bot.reply_to(message, "✅ Оценка стула сохранена.",
                         reply_markup=main_menu())
            del pending[user_id]


# ------------------- Запуск -------------------
if __name__ == '__main__':
    create_tables()

    # Запускаем поток с планировщиком
    scheduler_thread = threading.Thread(target=scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()

    # Запускаем бота
    print("Бот запущен...")
    bot.polling(none_stop=True)
