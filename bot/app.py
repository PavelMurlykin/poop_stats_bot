import logging
import re
import threading
import unicodedata
from datetime import datetime

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import BotCommand, CallbackQuery, MenuButtonCommands, Message

from bot.keyboards import (back_to_main, confirm_delete, edit_timetable_menu,
                           main_menu, manual_menu)
from bot.scheduler import run_scheduler
from bot.states import StateStore, UserState
from bot.validators import (validate_stool_quality, validate_text,
                            validate_time_hhmm)
from config import (APP_TZ, DATE_FORMAT_DISPLAY, DATE_FORMAT_STORAGE,
                    TELEGRAM_TOKEN)
from db.repositories import (add_feeling, add_medicine, add_stool,
                             delete_feeling, delete_meal, delete_medicine,
                             delete_stool, ensure_sleep_for_day,
                             get_sleep_for_day, get_user_times,
                             get_water_for_day, increment_water,
                             list_feelings_for_day, list_meals_for_day,
                             list_medicines_for_day, list_stools_for_day,
                             register_user, update_feeling, update_meal,
                             update_medicine, update_stool, update_user_time,
                             upsert_meal, upsert_sleep_quality,
                             upsert_sleep_times)
from db.schema import init_db
from services.report_service import BRISTOL, generate_user_report_xlsx

log = logging.getLogger(__name__)


def create_bot() -> telebot.TeleBot:
    return telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')


def _safe_edit_message_text(
    bot: telebot.TeleBot,
    text: str,
    chat_id: int,
    message_id: int,
    reply_markup=None,
) -> None:
    try:
        bot.edit_message_text(
            text,
            chat_id,
            message_id,
            reply_markup=reply_markup,
        )
    except ApiTelegramException as error:
        if 'message is not modified' in str(error).lower():
            return
        raise


def _safe_edit_message_reply_markup(
    bot: telebot.TeleBot,
    chat_id: int,
    message_id: int,
    reply_markup=None,
) -> None:
    try:
        bot.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=reply_markup,
        )
    except ApiTelegramException as error:
        if 'message is not modified' in str(error).lower():
            return
        raise


def _today_iso() -> str:
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_STORAGE)


def _today_display() -> str:
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_DISPLAY)


def _configure_telegram_commands(bot: telebot.TeleBot) -> None:
    commands = [
        BotCommand('start', 'Перезапустить бота'),
        BotCommand('menu', 'Открыть главное меню'),
        BotCommand('cancel', 'Отменить текущий ввод'),
        BotCommand('help', 'Справка'),
    ]
    try:
        bot.set_my_commands(commands)
    except ApiTelegramException as error:
        log.warning('Failed to set bot commands: %s', error)
        return

    if not hasattr(bot, 'set_chat_menu_button'):
        return

    try:
        bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except TypeError:
        try:
            bot.set_chat_menu_button(menu_button=MenuButtonCommands('commands'))
        except ApiTelegramException as error:
            log.warning('Failed to set menu button: %s', error)
    except ApiTelegramException as error:
        log.warning('Failed to set menu button: %s', error)


def _display_width(value: str) -> int:
    width = 0
    for char in value:
        if unicodedata.combining(char):
            continue
        if unicodedata.category(char) == 'Cf':
            continue
        width += 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
    return width


def _pad_cell(value: str, width: int) -> str:
    return value + (' ' * max(0, width - _display_width(value)))


def _format_timetable_table(
    breakfast: str,
    lunch: str,
    dinner: str,
    toilet: str,
    wakeup: str,
    bed: str,
) -> str:
    rows = [
        ('🍳 Завтрак', breakfast),
        ('🍲 Обед', lunch),
        ('🍽️ Ужин', dinner),
        ('🚽 Туалет', toilet),
        ('🌅 Подъем', wakeup),
        ('🌙 Отход ко сну', bed),
    ]
    normalized_rows = [(name, value or '--:--') for name, value in rows]
    left_header = 'Событие'
    right_header = 'Время'

    left_width = max(
        _display_width(left_header),
        *(_display_width(name) for name, _ in normalized_rows),
    )
    right_width = max(
        _display_width(right_header),
        *(_display_width(value) for _, value in normalized_rows),
    )

    separator = f'+-{"-" * left_width}-+-{"-" * right_width}-+'
    lines = [
        separator,
        f'| {_pad_cell(left_header, left_width)} | {_pad_cell(right_header, right_width)} |',
        separator,
    ]
    for name, value in normalized_rows:
        lines.append(f'| {_pad_cell(name, left_width)} | {_pad_cell(value, right_width)} |')
    lines.append(separator)
    return '<pre>' + '\n'.join(lines) + '</pre>'


def build_app(bot: telebot.TeleBot) -> None:
    init_db()
    _configure_telegram_commands(bot)
    states = StateStore()

    def send_breakfast(user_id: int) -> None:
        bot.send_message(user_id, '🍳 Что вы ели на завтрак?', reply_markup=back_to_main())
        states.set(
            user_id,
            UserState('pending_question', 'meal', {'meal_type': 'breakfast', 'date': _today_iso()}),
        )

    def send_lunch(user_id: int) -> None:
        bot.send_message(user_id, '🍲 Что вы ели на обед?', reply_markup=back_to_main())
        states.set(
            user_id,
            UserState('pending_question', 'meal', {'meal_type': 'lunch', 'date': _today_iso()}),
        )

    def send_dinner(user_id: int) -> None:
        bot.send_message(user_id, '🍽️ Что вы ели на ужин?', reply_markup=back_to_main())
        states.set(
            user_id,
            UserState('pending_question', 'meal', {'meal_type': 'dinner', 'date': _today_iso()}),
        )

    def send_toilet(user_id: int) -> None:
        lines = ['🚽 Оцените качество стула по Бристольской шкале:\n']
        for key in range(0, 8):
            lines.append(f'{key} — {BRISTOL.get(key, "неизвестно")}')
        lines.append('\nВведите цифру от 0 до 7:')
        bot.send_message(user_id, '\n'.join(lines), reply_markup=back_to_main())
        states.set(user_id, UserState('pending_question', 'stool', {'date': _today_iso()}))

    def send_sleep_quality(user_id: int) -> None:
        ensure_sleep_for_day(user_id, _today_iso())
        bot.send_message(
            user_id,
            '🛌 Как вы оцениваете качество сна этой ночью?',
            reply_markup=back_to_main(),
        )
        states.set(user_id, UserState('pending_question', 'sleep_quality', {'date': _today_iso()}))

    @bot.message_handler(commands=['start'])
    def cmd_start(message: Message):
        user_id = message.from_user.id
        register_user(user_id)
        ensure_sleep_for_day(user_id, _today_iso())
        bot.send_message(
            user_id,
            '👋 Привет! Бот помогает вести дневник питания, самочувствия и сна.\n'
            'Используйте меню ниже для настройки расписания и добавления событий.',
            reply_markup=main_menu(),
        )

    @bot.message_handler(commands=['menu'])
    def cmd_menu(message: Message):
        bot.send_message(message.from_user.id, 'Главное меню:', reply_markup=main_menu())

    @bot.message_handler(commands=['cancel'])
    def cmd_cancel(message: Message):
        states.clear(message.from_user.id)
        bot.send_message(message.from_user.id, '✅ Ожидание отменено.', reply_markup=main_menu())

    @bot.message_handler(commands=['help'])
    def cmd_help(message: Message):
        bot.send_message(
            message.from_user.id,
            '📋 <b>Команды:</b>\n/menu — меню\n/cancel — отменить ввод\n\n'
            'Остальные действия доступны через кнопки.',
            reply_markup=back_to_main(),
        )

    @bot.message_handler(regexp=r'^/edit_meal_(\d+)$')
    def edit_meal_cmd(message: Message):
        meal_id = int(re.match(r'^/edit_meal_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState('edit', 'meal_desc', {'id': meal_id}))
        bot.reply_to(message, 'Введите новое описание:')

    @bot.message_handler(regexp=r'^/edit_med_(\d+)$')
    def edit_med_cmd(message: Message):
        med_id = int(re.match(r'^/edit_med_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState('edit', 'med_name', {'id': med_id}))
        bot.reply_to(message, 'Введите новое название:')

    @bot.message_handler(regexp=r'^/edit_stool_(\d+)$')
    def edit_stool_cmd(message: Message):
        stool_id = int(re.match(r'^/edit_stool_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState('edit', 'stool_quality', {'id': stool_id}))
        bot.reply_to(message, 'Введите новую оценку (0-7):')

    @bot.message_handler(regexp=r'^/edit_feeling_(\d+)$')
    def edit_feeling_cmd(message: Message):
        feeling_id = int(re.match(r'^/edit_feeling_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState('edit', 'feeling_desc', {'id': feeling_id}))
        bot.reply_to(message, 'Введите новое описание:')

    @bot.message_handler(regexp=r'^/delete_(meal|med|stool|feeling)_(\d+)$')
    def delete_cmd(message: Message):
        match = re.match(r'^/delete_(meal|med|stool|feeling)_(\d+)$', message.text)
        item_type = match.group(1)
        item_id = int(match.group(2))
        bot.send_message(
            message.from_user.id,
            '❓ Вы уверены, что хотите удалить эту запись?',
            reply_markup=confirm_delete(item_type, item_id),
        )

    @bot.callback_query_handler(func=lambda _: True)
    def on_callback(call: CallbackQuery):
        user_id = call.from_user.id
        data = call.data or ''

        if data == 'back_to_main':
            _safe_edit_message_text(
                bot,
                'Главное меню:',
                user_id,
                call.message.message_id,
                reply_markup=main_menu(),
            )
            states.clear(user_id)
            return

        if data == 'show_timetable':
            times = get_user_times(user_id)
            if not times:
                _safe_edit_message_text(
                    bot,
                    '❌ Вы не зарегистрированы. Напишите /start',
                    user_id,
                    call.message.message_id,
                    reply_markup=back_to_main(),
                )
                return
            breakfast, lunch, dinner, toilet, wakeup, bed = times
            text = (
                '⏰ <b>Ваше расписание:</b>\n'
                f'{_format_timetable_table(breakfast, lunch, dinner, toilet, wakeup, bed)}\n\n'
                'Нажмите кнопку, чтобы изменить время.'
            )
            _safe_edit_message_text(
                bot,
                text,
                user_id,
                call.message.message_id,
                reply_markup=edit_timetable_menu(),
            )
            return

        if data.startswith('set_time_'):
            slot = data.replace('set_time_', '')
            examples = {
                'breakfast': '08:00',
                'lunch': '13:00',
                'dinner': '19:00',
                'toilet': '09:00',
                'wakeup': '07:00',
                'bed': '23:00',
            }
            names = {
                'breakfast': 'завтрака',
                'lunch': 'обеда',
                'dinner': 'ужина',
                'toilet': 'туалета',
                'wakeup': 'подъема',
                'bed': 'отхода ко сну',
            }
            slot_name = names.get(slot, slot)
            example_time = examples.get(slot, '08:00')
            bot.send_message(
                user_id,
                f'Введите время <b>{slot_name}</b> в формате ЧЧ:ММ (например, {example_time}):',
            )
            states.set(user_id, UserState('awaiting_time', 'time', {'slot': slot}))
            _safe_edit_message_reply_markup(bot, user_id, call.message.message_id, reply_markup=None)
            return

        if data == 'manual_menu':
            bot.edit_message_text(
                '➕ Добавить событие: выберите тип записи',
                user_id,
                call.message.message_id,
                reply_markup=manual_menu(),
            )
            return

        if data.startswith('manual_meal_'):
            meal_type = data.replace('manual_meal_', '')
            bot.edit_message_text('🍽️ Введите описание:', user_id, call.message.message_id)
            states.set(
                user_id,
                UserState('manual', 'meal_desc', {'meal_type': meal_type, 'date': _today_iso()}),
            )
            return

        if data == 'manual_medicine':
            bot.edit_message_text('💊 Введите название лекарства:', user_id, call.message.message_id)
            states.set(user_id, UserState('manual', 'med_name', {'date': _today_iso()}))
            return

        if data == 'manual_stool':
            lines = ['🚽 Оцените качество стула по Бристольской шкале:\n']
            for key in range(0, 8):
                lines.append(f'{key} — {BRISTOL.get(key, "неизвестно")}')
            lines.append('\nВведите цифру от 0 до 7:')
            bot.edit_message_text('\n'.join(lines), user_id, call.message.message_id)
            states.set(user_id, UserState('manual', 'stool_quality', {'date': _today_iso()}))
            return

        if data == 'manual_feeling':
            bot.edit_message_text('😊 Опишите ваше самочувствие:', user_id, call.message.message_id)
            states.set(user_id, UserState('manual', 'feeling_desc', {'date': _today_iso()}))
            return

        if data == 'manual_sleep_wakeup':
            ensure_sleep_for_day(user_id, _today_iso())
            bot.edit_message_text(
                '🌅 Введите фактическое время подъема (ЧЧ:ММ):',
                user_id,
                call.message.message_id,
            )
            states.set(user_id, UserState('manual', 'sleep_wakeup_time', {'date': _today_iso()}))
            return

        if data == 'manual_sleep_bed':
            ensure_sleep_for_day(user_id, _today_iso())
            bot.edit_message_text(
                '🌙 Введите фактическое время отхода ко сну (ЧЧ:ММ):',
                user_id,
                call.message.message_id,
            )
            states.set(user_id, UserState('manual', 'sleep_bed_time', {'date': _today_iso()}))
            return

        if data == 'manual_sleep_quality':
            ensure_sleep_for_day(user_id, _today_iso())
            bot.edit_message_text('🛌 Опишите качество сна:', user_id, call.message.message_id)
            states.set(user_id, UserState('manual', 'sleep_quality_desc', {'date': _today_iso()}))
            return

        if data == 'manual_water':
            total_glasses = increment_water(user_id, _today_iso())
            states.clear(user_id)
            bot.answer_callback_query(call.id, text='✅ Добавлен стакан воды.')
            _safe_edit_message_text(
                bot,
                f'💧 Добавлен стакан воды. Сегодня: {total_glasses}.',
                user_id,
                call.message.message_id,
                reply_markup=manual_menu(),
            )
            return

        if data == 'show_today':
            _show_today(bot, user_id, call.message.message_id)
            return

        if data == 'help':
            bot.edit_message_text(
                '📋 <b>Доступно:</b>\n'
                '• Настройка времени\n'
                '• Добавление событий\n'
                '• Просмотр/редактирование/удаление\n'
                '• Экспорт статистики',
                user_id,
                call.message.message_id,
                reply_markup=back_to_main(),
            )
            return

        if data == 'bristol':
            text = '📊 <b>Бристольская шкала:</b>\n' + '\n'.join(
                [f'{key} — {BRISTOL[key]}' for key in range(0, 8)]
            )
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main())
            return

        if data == 'cancel_delete':
            bot.edit_message_text(
                'Удаление отменено.',
                user_id,
                call.message.message_id,
                reply_markup=back_to_main(),
            )
            return

        if data.startswith('confirm_delete:'):
            _, item_type, item_id_s = data.split(':', 2)
            item_id = int(item_id_s)
            ok = False
            if item_type == 'meal':
                ok = delete_meal(user_id, item_id)
            elif item_type == 'med':
                ok = delete_medicine(user_id, item_id)
            elif item_type == 'stool':
                ok = delete_stool(user_id, item_id)
            elif item_type == 'feeling':
                ok = delete_feeling(user_id, item_id)

            bot.answer_callback_query(call.id, text='Удалено' if ok else 'Не найдено / нет прав')
            _show_today(bot, user_id, call.message.message_id)
            return

        if data == 'export_all_stats':
            bot.answer_callback_query(call.id, text='Формирую отчёт…')
            bot.send_message(user_id, '🔄 Формирую отчёт. Это может занять некоторое время.')
            thread = threading.Thread(target=_export_and_send, args=(bot, user_id))
            thread.daemon = True
            thread.start()
            return

    @bot.message_handler(func=lambda _: True)
    def on_text(message: Message):
        user_id = message.from_user.id
        text = (message.text or '').strip()
        state = states.get(user_id)

        if not state:
            bot.reply_to(
                message,
                'Я не ожидаю ввод. Используйте /menu.',
                reply_markup=main_menu(),
            )
            return

        if state.kind == 'edit':
            try:
                if state.step == 'meal_desc':
                    desc = validate_text(text)
                    ok = update_meal(user_id, state.data['id'], desc)
                    bot.reply_to(
                        message,
                        '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.',
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'med_name':
                    name = validate_text(text)
                    state.step = 'med_dosage'
                    state.data['name'] = name
                    bot.reply_to(message, 'Введите новую дозировку (или "-"):')
                    return

                if state.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    ok = update_medicine(user_id, state.data['id'], state.data['name'], dosage)
                    bot.reply_to(
                        message,
                        '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.',
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'stool_quality':
                    quality = validate_stool_quality(text)
                    ok = update_stool(user_id, state.data['id'], quality)
                    bot.reply_to(
                        message,
                        '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.',
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'feeling_desc':
                    desc = validate_text(text)
                    ok = update_feeling(user_id, state.data['id'], desc)
                    bot.reply_to(
                        message,
                        '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.',
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return
            except ValueError as error:
                bot.reply_to(message, f'❌ {error}')
                return

        if state.kind == 'awaiting_time':
            if not validate_time_hhmm(text):
                bot.reply_to(
                    message,
                    '❌ Неверный формат. Введите время ЧЧ:ММ.',
                    reply_markup=main_menu(),
                )
                return

            slot = state.data['slot']
            ok = update_user_time(user_id, slot, text)
            if ok and slot == 'wakeup':
                upsert_sleep_times(user_id, _today_iso(), wakeup_time=text)
            if ok and slot == 'bed':
                upsert_sleep_times(user_id, _today_iso(), bed_time=text)

            bot.reply_to(
                message,
                '✅ Время сохранено.' if ok else '❌ Ошибка сохранения.',
                reply_markup=main_menu(),
            )
            states.clear(user_id)
            return

        try:
            if state.kind == 'manual':
                if state.step == 'meal_desc':
                    desc = validate_text(text)
                    upsert_meal(user_id, state.data['date'], state.data['meal_type'], desc)
                    bot.reply_to(message, '✅ Запись сохранена.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'med_name':
                    name = validate_text(text)
                    state.step = 'med_dosage'
                    state.data['name'] = name
                    bot.reply_to(message, 'Введите дозировку (или "-" чтобы пропустить):')
                    return

                if state.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    add_medicine(user_id, state.data['date'], state.data['name'], dosage)
                    bot.reply_to(message, '✅ Лекарство добавлено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'stool_quality':
                    quality = validate_stool_quality(text)
                    add_stool(user_id, state.data['date'], quality)
                    bot.reply_to(message, '✅ Запись сохранена.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'feeling_desc':
                    desc = validate_text(text)
                    add_feeling(user_id, state.data['date'], desc)
                    bot.reply_to(message, '✅ Запись сохранена.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'sleep_wakeup_time':
                    if not validate_time_hhmm(text):
                        raise ValueError('Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(user_id, state.data['date'], wakeup_time=text)
                    bot.reply_to(message, '✅ Время подъема сохранено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'sleep_bed_time':
                    if not validate_time_hhmm(text):
                        raise ValueError('Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(user_id, state.data['date'], bed_time=text)
                    bot.reply_to(
                        message,
                        '✅ Время отхода ко сну сохранено.',
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_quality_desc':
                    desc = validate_text(text)
                    upsert_sleep_quality(user_id, state.data['date'], desc)
                    bot.reply_to(message, '✅ Качество сна сохранено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

            if state.kind == 'pending_question':
                if state.step == 'meal':
                    desc = validate_text(text)
                    upsert_meal(user_id, state.data['date'], state.data['meal_type'], desc)
                    bot.reply_to(message, '✅ Сохранено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'stool':
                    quality = validate_stool_quality(text)
                    add_stool(user_id, state.data['date'], quality)
                    bot.reply_to(message, '✅ Сохранено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if state.step == 'sleep_quality':
                    desc = validate_text(text)
                    upsert_sleep_quality(user_id, state.data['date'], desc)
                    bot.reply_to(message, '✅ Сохранено.', reply_markup=main_menu())
                    states.clear(user_id)
                    return
        except ValueError as error:
            bot.reply_to(message, f'❌ {error}')
            return

    thread = threading.Thread(
        target=run_scheduler,
        args=(send_breakfast, send_lunch, send_dinner, send_toilet, send_sleep_quality),
    )
    thread.daemon = True
    thread.start()


def _show_today(bot: telebot.TeleBot, user_id: int, message_id: int) -> None:
    date_iso = _today_iso()
    date_display = _today_display()

    ensure_sleep_for_day(user_id, date_iso)
    sleep = get_sleep_for_day(user_id, date_iso)
    meals = list_meals_for_day(user_id, date_iso)
    medicines = list_medicines_for_day(user_id, date_iso)
    stools = list_stools_for_day(user_id, date_iso)
    feelings = list_feelings_for_day(user_id, date_iso)
    water_glasses = get_water_for_day(user_id, date_iso)

    lines = [f'<b>Записи за {date_display}</b>\n']

    if meals:
        lines.append('<b>Еда:</b>')
        meal_order = [
            ('breakfast', '🍳 Завтрак'),
            ('lunch', '🍲 Обед'),
            ('dinner', '🍽️ Ужин'),
            ('snack', '🍪 Перекус'),
        ]
        grouped = {meal_type: [] for meal_type, _ in meal_order}
        for meal in meals:
            meal_type = meal['meal_type']
            if meal_type in grouped:
                grouped[meal_type].append(meal)
        for meal_type, meal_title in meal_order:
            for meal in grouped[meal_type]:
                meal_id = meal['id']
                meal_desc = meal['description']
                lines.append(
                    f'<b>{meal_title}</b>: {meal_desc}'
                    f'\n(ред.: /edit_meal_{meal_id})'
                    f'\n(удал.: /delete_meal_{meal_id})\n'
                )

    if medicines:
        lines.append('\n💊 <b>Лекарства:</b>')
        for medicine in medicines:
            medicine_id = medicine['id']
            medicine_name = medicine['name']
            dosage = (medicine['dosage'] or '').strip()
            tail = f' ({dosage})' if dosage else ''
            lines.append(
                f'- {medicine_name}{tail}'
                f'\n(ред.: /edit_med_{medicine_id})'
                f'\n(удал.: /delete_med_{medicine_id})\n'
            )

    if stools:
        lines.append('\n🚽 <b>Туалет:</b>')
        for stool in stools:
            stool_id = stool['id']
            quality = int(stool['quality'])
            quality_text = BRISTOL.get(quality, 'неизвестно')
            lines.append(
                f'- {quality} - {quality_text}'
                f'\n(ред.: /edit_stool_{stool_id})'
                f'\n(удал.: /delete_stool_{stool_id})\n'
            )

    if feelings:
        lines.append('\n😊 <b>Самочувствие:</b>')
        for feeling in feelings:
            feeling_id = feeling['id']
            feeling_desc = feeling['description']
            lines.append(
                f'- {feeling_desc}'
                f'\n(ред.: /edit_feeling_{feeling_id})'
                f'\n(удал.: /delete_feeling_{feeling_id})\n'
            )

    if water_glasses:
        lines.append('\n💧 <b>Вода:</b>')
        lines.append(f'- Выпито стаканов: {water_glasses}')

    if sleep:
        wakeup_time = sleep.get('wakeup_time', '--:--')
        bed_time = sleep.get('bed_time', '--:--')
        quality_desc = (sleep.get('quality_description') or '').strip() or 'не указано'
        lines.append('\n🛌 <b>Сон:</b>')
        lines.append(f'- Подъем: {wakeup_time}')
        lines.append(f'- Отход ко сну: {bed_time}')
        lines.append(f'- Качество сна: {quality_desc}')

    if len(lines) == 1:
        lines.append('За сегодня записей нет.')

    _safe_edit_message_text(
        bot,
        '\n'.join(lines),
        user_id,
        message_id,
        reply_markup=back_to_main(),
    )


def _export_and_send(bot: telebot.TeleBot, user_id: int) -> None:
    try:
        xlsx = generate_user_report_xlsx(user_id)
        stamp = datetime.now(APP_TZ).strftime('%Y%m%d_%H%M%S')
        filename = f'Статистика_{stamp}.xlsx'
        bot.send_document(
            user_id,
            xlsx,
            visible_file_name=filename,
            caption='Ваша полная статистика',
        )
    except Exception as error:
        log.exception('Report error')
        bot.send_message(user_id, f'❌ Ошибка при формировании отчёта: {error}')
