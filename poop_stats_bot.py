import os
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

import telebot
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

# Глобальный словарь для хранения состояний ожидания ответа
pending_lock = threading.Lock()
pending = {}  # {user_id: {'type': 'breakfast', 'date': '2025-03-28'}}


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
                     "Используй /help для списка команд.")


@bot.message_handler(commands=['help'])
def cmd_help(message):
    text = (
        "📋 <b>Доступные команды:</b>\n"
        "/set_breakfast HH:MM — время завтрака\n"
        "/set_lunch HH:MM — время обеда\n"
        "/set_dinner HH:MM — время ужина\n"
        "/set_toilet HH:MM — время опроса о стуле\n"
        "/bristol — показать Бристольскую шкалу стула\n"
        "/show_settings — текущие настройки\n"
        "/cancel — отменить ожидаемый вопрос\n"
        "/help — это сообщение"
    )
    bot.send_message(message.from_user.id, text, parse_mode="HTML")


@bot.message_handler(commands=['bristol'])
def cmd_bristol(message):
    scale = get_bristol_scale()
    text = "📊 <b>Бристольская шкала формы кала:</b>\n"
    for id, desc in scale:
        text += f"{id} — {desc}\n"
    bot.send_message(message.from_user.id, text, parse_mode="HTML")


@bot.message_handler(commands=['set_breakfast', 'set_lunch', 'set_dinner', 'set_toilet'])
def cmd_set_time(message):
    user_id = message.from_user.id
    command = message.text.split()[0]
    meal_type = command.split('_')[1]  # breakfast, lunch, dinner, toilet
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ Использование: /set_breakfast 08:00")
        return
    time_str = args[1]
    if update_user_time(user_id, meal_type, time_str):
        bot.reply_to(
            message, f"✅ Время для <b>{meal_type}</b> установлено на <b>{time_str}</b>", parse_mode="HTML")
    else:
        bot.reply_to(
            message, "❌ Неверный формат времени. Используй HH:MM (например, 08:00).")


@bot.message_handler(commands=['show_settings'])
def cmd_show_settings(message):
    user_id = message.from_user.id
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
        bot.send_message(user_id, text, parse_mode="HTML")
    else:
        bot.send_message(user_id, "❌ Ты не зарегистрирован. Напиши /start")


@bot.message_handler(commands=['cancel'])
def cmd_cancel(message):
    user_id = message.from_user.id
    with pending_lock:
        if user_id in pending:
            del pending[user_id]
            bot.reply_to(message, "✅ Ожидание отменено.")
        else:
            bot.reply_to(message, "❌ Нет активного ожидания.")


# ------------------- Обработчик текстовых сообщений (ответы на вопросы) -------------------
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    with pending_lock:
        if user_id not in pending:
            bot.reply_to(
                message, "Я не ожидаю ответа. Используй /help для списка команд.")
            return

        p = pending[user_id]
        p_type = p['type']
        p_date = p['date']  # дата, к которой относится запись

        if p_type in ('breakfast', 'lunch', 'dinner'):
            save_meal(user_id, p_type, text, p_date)
            bot.reply_to(
                message, f"✅ Информация о <b>{p_type}</b> сохранена.", parse_mode="HTML")
            del pending[user_id]

        elif p_type == 'toilet':
            if not text.isdigit() or not (0 <= int(text) <= 7):
                bot.reply_to(
                    message, "❌ Пожалуйста, введи <b>число от 0 до 7</b>.", parse_mode="HTML")
                return
            quality = int(text)
            save_stool(user_id, quality, p_date)
            bot.reply_to(message, "✅ Оценка стула сохранена.")
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
