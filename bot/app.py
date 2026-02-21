import logging
import threading
import re
from datetime import datetime
import telebot
from telebot.types import Message, CallbackQuery
from telebot.apihelper import ApiTelegramException

from config import TELEGRAM_TOKEN, APP_TZ, DATE_FORMAT_STORAGE, DATE_FORMAT_DISPLAY
from db.schema import init_db
from db.repositories import (
    register_user,
    get_user_times,
    update_user_time,
    upsert_meal,
    list_meals_for_day,
    update_meal,
    delete_meal,
    add_medicine,
    list_medicines_for_day,
    update_medicine,
    delete_medicine,
    add_stool,
    list_stools_for_day,
    update_stool,
    delete_stool,
    add_feeling,
    list_feelings_for_day,
    update_feeling,
    delete_feeling,
)
from bot.keyboards import main_menu, back_to_main, edit_timetable_menu, manual_menu, confirm_delete
from bot.states import StateStore, UserState
from bot.validators import validate_text, validate_time_hhmm, validate_stool_quality
from services.report_service import generate_user_report_xlsx, BRISTOL
from bot.scheduler import run_scheduler

log = logging.getLogger(__name__)


def create_bot() -> telebot.TeleBot:
    return telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')


def _safe_edit_message_text(
    bot: telebot.TeleBot, text: str, chat_id: int, message_id: int, reply_markup=None
) -> None:
    try:
        bot.edit_message_text(text, chat_id, message_id,
                              reply_markup=reply_markup)
    except ApiTelegramException as e:
        if 'message is not modified' in str(e).lower():
            return
        raise


def _safe_edit_message_reply_markup(
    bot: telebot.TeleBot, chat_id: int, message_id: int, reply_markup=None
) -> None:
    try:
        bot.edit_message_reply_markup(
            chat_id, message_id, reply_markup=reply_markup)
    except ApiTelegramException as e:
        if 'message is not modified' in str(e).lower():
            return
        raise


def _today_iso() -> str:
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_STORAGE)


def _today_display() -> str:
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_DISPLAY)


def build_app(bot: telebot.TeleBot) -> None:
    init_db()
    states = StateStore()

    def send_breakfast(user_id: int) -> None:
        bot.send_message(user_id, '🍳 Что вы ели на завтрак?',
                         reply_markup=back_to_main())
        states.set(user_id, UserState('pending_question', 'meal', {
                   'meal_type': 'breakfast', 'date': _today_iso()}))

    def send_lunch(user_id: int) -> None:
        bot.send_message(user_id, '🍲 Что вы ели на обед?',
                         reply_markup=back_to_main())
        states.set(user_id, UserState('pending_question', 'meal',
                   {'meal_type': 'lunch', 'date': _today_iso()}))

    def send_dinner(user_id: int) -> None:
        bot.send_message(user_id, '🍽️ Что вы ели на ужин?',
                         reply_markup=back_to_main())
        states.set(user_id, UserState('pending_question', 'meal',
                   {'meal_type': 'dinner', 'date': _today_iso()}))

    def send_toilet(user_id: int) -> None:
        lines = ['🚽 Оцените качество стула по Бристольской шкале:\n']
        for k in range(0, 8):
            lines.append(f'{k} — {BRISTOL.get(k, "неизвестно")}')
        lines.append('\nВведите цифру от 0 до 7:')
        bot.send_message(user_id, '\n'.join(lines),
                         reply_markup=back_to_main())
        states.set(user_id, UserState('pending_question',
                   'stool', {'date': _today_iso()}))

    @bot.message_handler(commands=['start'])
    def cmd_start(message: Message):
        user_id = message.from_user.id
        register_user(user_id)
        bot.send_message(
            user_id,
            '👋 Привет! Я помогу отслеживать связь между питанием и стулом.\n'
            'Используй кнопки ниже для настройки и ручного ввода.',
            reply_markup=main_menu(),
        )

    @bot.message_handler(commands=['menu'])
    def cmd_menu(message: Message):
        bot.send_message(message.from_user.id, 'Главное меню:',
                         reply_markup=main_menu())

    @bot.message_handler(commands=['cancel'])
    def cmd_cancel(message: Message):
        states.clear(message.from_user.id)
        bot.send_message(message.from_user.id,
                         '✅ Ожидание отменено.', reply_markup=main_menu())

    @bot.message_handler(commands=['help'])
    def cmd_help(message: Message):
        bot.send_message(
            message.from_user.id,
            '📋 <b>Команды:</b>\n/menu — меню\n/cancel — отменить ввод\n\nОстальное — через кнопки.',
            reply_markup=back_to_main(),
        )

    @bot.message_handler(regexp=r'^/edit_meal_(\d+)$')
    def edit_meal_cmd(message: Message):
        meal_id = int(re.match(r'^/edit_meal_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState(
            'edit', 'meal_desc', {'id': meal_id}))
        bot.reply_to(message, 'Введите новое описание:')

    @bot.message_handler(regexp=r'^/edit_med_(\d+)$')
    def edit_med_cmd(message: Message):
        med_id = int(re.match(r'^/edit_med_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState(
            'edit', 'med_name', {'id': med_id}))
        bot.reply_to(message, 'Введите новое название:')

    @bot.message_handler(regexp=r'^/edit_stool_(\d+)$')
    def edit_stool_cmd(message: Message):
        stool_id = int(re.match(r'^/edit_stool_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState(
            'edit', 'stool_quality', {'id': stool_id}))
        bot.reply_to(message, 'Введите новую оценку (0–7):')

    @bot.message_handler(regexp=r'^/edit_feeling_(\d+)$')
    def edit_feeling_cmd(message: Message):
        feeling_id = int(
            re.match(r'^/edit_feeling_(\d+)$', message.text).group(1))
        states.set(message.from_user.id, UserState(
            'edit', 'feeling_desc', {'id': feeling_id}))
        bot.reply_to(message, 'Введите новое описание:')

    @bot.message_handler(regexp=r'^/delete_(meal|med|stool|feeling)_(\d+)$')
    def delete_cmd(message: Message):
        m = re.match(r'^/delete_(meal|med|stool|feeling)_(\d+)$', message.text)
        item_type = m.group(1)
        item_id = int(m.group(2))
        bot.send_message(message.from_user.id, '❓ Вы уверены, что хотите удалить эту запись?',
                         reply_markup=confirm_delete(item_type, item_id))

    @bot.callback_query_handler(func=lambda _: True)
    def on_callback(call: CallbackQuery):
        user_id = call.from_user.id
        data = call.data or ''

        if data == 'back_to_main':
            _safe_edit_message_text(bot,
                                    'Главное меню:', user_id, call.message.message_id, reply_markup=main_menu())
            states.clear(user_id)
            return

        if data == 'show_timetable':
            times = get_user_times(user_id)
            if not times:
                _safe_edit_message_text(bot, '❌ Ты не зарегистрирован. Напиши /start',
                                        user_id, call.message.message_id, reply_markup=back_to_main())
                return
            bt, lt, dt, tt = times
            txt = (
                '⏰ <b>Твоё расписание:</b>\n'
                f'Завтрак: {bt}\n'
                f'Обед:    {lt}\n'
                f'Ужин:    {dt}\n'
                f'Туалет:  {tt}\n\n'
                'Нажми кнопку, чтобы изменить время.'
            )
            _safe_edit_message_text(bot,
                                    txt, user_id, call.message.message_id, reply_markup=edit_timetable_menu())
            return

        if data.startswith('set_time_'):
            slot = data.replace('set_time_', '')
            examples = {'breakfast': '08:00', 'lunch': '13:00',
                        'dinner': '19:00', 'toilet': '09:00'}
            names = {'breakfast': 'завтрака', 'lunch': 'обеда',
                     'dinner': 'ужина', 'toilet': 'туалета'}
            bot.send_message(
                user_id, f'Введите время <b>{names.get(slot, slot)}</b> в формате ЧЧ:ММ (например, {examples.get(slot, "08:00")}):')
            states.set(user_id, UserState(
                'awaiting_time', 'time', {'slot': slot}))
            bot.edit_message_reply_markup(
                user_id, call.message.message_id, reply_markup=None)
            return

        if data == 'manual_menu':
            bot.edit_message_text('➕ Добавить событие: выберите тип записи',
                                  user_id, call.message.message_id, reply_markup=manual_menu())
            return

        if data.startswith('manual_meal_'):
            meal_type = data.replace('manual_meal_', '')
            bot.edit_message_text('🍽️ Введите описание:',
                                  user_id, call.message.message_id)
            states.set(user_id, UserState('manual', 'meal_desc', {
                       'meal_type': meal_type, 'date': _today_iso()}))
            return

        if data == 'manual_medicine':
            bot.edit_message_text(
                '💊 Введите название лекарства:', user_id, call.message.message_id)
            states.set(user_id, UserState(
                'manual', 'med_name', {'date': _today_iso()}))
            return

        if data == 'manual_stool':
            lines = ['🚽 Оцените качество стула по Бристольской шкале:\n']
            for k in range(0, 8):
                lines.append(f'{k} — {BRISTOL.get(k, "неизвестно")}')
            lines.append('\nВведите цифру от 0 до 7:')
            bot.edit_message_text(
                '\n'.join(lines), user_id, call.message.message_id)
            states.set(user_id, UserState(
                'manual', 'stool_quality', {'date': _today_iso()}))
            return

        if data == 'manual_feeling':
            bot.edit_message_text(
                '😊 Опишите ваше самочувствие:', user_id, call.message.message_id)
            states.set(user_id, UserState(
                'manual', 'feeling_desc', {'date': _today_iso()}))
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
                user_id, call.message.message_id, reply_markup=back_to_main()
            )
            return

        if data == 'bristol':
            text = '📊 <b>Бристольская шкала:</b>\n' + \
                '\n'.join([f'{k} — {BRISTOL[k]}' for k in range(0, 8)])
            bot.edit_message_text(
                text, user_id, call.message.message_id, reply_markup=back_to_main())
            return

        if data == 'cancel_delete':
            bot.edit_message_text('Удаление отменено.', user_id,
                                  call.message.message_id, reply_markup=back_to_main())
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

            bot.answer_callback_query(
                call.id, text='Удалено' if ok else 'Не найдено / нет прав')
            _show_today(bot, user_id, call.message.message_id)
            return

        if data == 'export_all_stats':
            bot.answer_callback_query(call.id, text='Формирую отчёт…')
            bot.send_message(
                user_id, '🔄 Формирую отчёт. Это может занять некоторое время.')
            t = threading.Thread(target=_export_and_send, args=(bot, user_id))
            t.daemon = True
            t.start()
            return

    @bot.message_handler(func=lambda _: True)
    def on_text(message: Message):
        user_id = message.from_user.id
        text = (message.text or '').strip()
        st = states.get(user_id)

        if not st:
            bot.reply_to(
                message, 'Я не ожидаю ввода. Используй /menu.', reply_markup=main_menu())
            return

        if st.kind == 'edit':
            try:
                if st.step == 'meal_desc':
                    desc = validate_text(text)
                    ok = update_meal(user_id, st.data['id'], desc)
                    bot.reply_to(
                        message, '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'med_name':
                    name = validate_text(text)
                    st.step = 'med_dosage'
                    st.data['name'] = name
                    bot.reply_to(message, 'Введите новую дозировку (или «-»):')
                    return

                if st.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    ok = update_medicine(
                        user_id, st.data['id'], st.data['name'], dosage)
                    bot.reply_to(
                        message, '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'stool_quality':
                    q = validate_stool_quality(text)
                    ok = update_stool(user_id, st.data['id'], q)
                    bot.reply_to(
                        message, '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'feeling_desc':
                    desc = validate_text(text)
                    ok = update_feeling(user_id, st.data['id'], desc)
                    bot.reply_to(
                        message, '✅ Обновлено.' if ok else '❌ Не найдено / нет прав.', reply_markup=main_menu())
                    states.clear(user_id)
                    return

            except ValueError as e:
                bot.reply_to(message, f'❌ {e}')
                return

        if st.kind == 'awaiting_time':
            if not validate_time_hhmm(text):
                bot.reply_to(
                    message, '❌ Неверный формат. Введите время ЧЧ:ММ.', reply_markup=main_menu())
                return
            slot = st.data['slot']
            ok = update_user_time(user_id, slot, text)
            bot.reply_to(
                message, '✅ Время сохранено.' if ok else '❌ Ошибка сохранения.', reply_markup=main_menu())
            states.clear(user_id)
            return

        try:
            if st.kind == 'manual':
                if st.step == 'meal_desc':
                    desc = validate_text(text)
                    upsert_meal(
                        user_id, st.data['date'], st.data['meal_type'], desc)
                    bot.reply_to(message, '✅ Запись сохранена.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'med_name':
                    name = validate_text(text)
                    st.step = 'med_dosage'
                    st.data['name'] = name
                    bot.reply_to(
                        message, 'Введите дозировку (или «-» чтобы пропустить):')
                    return

                if st.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    add_medicine(
                        user_id, st.data['date'], st.data['name'], dosage)
                    bot.reply_to(message, '✅ Лекарство добавлено.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'stool_quality':
                    q = validate_stool_quality(text)
                    add_stool(user_id, st.data['date'], q)
                    bot.reply_to(message, '✅ Запись сохранена.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return

                if st.step == 'feeling_desc':
                    desc = validate_text(text)
                    add_feeling(user_id, st.data['date'], desc)
                    bot.reply_to(message, '✅ Запись сохранена.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return

            if st.kind == 'pending_question':
                if st.step == 'meal':
                    desc = validate_text(text)
                    upsert_meal(
                        user_id, st.data['date'], st.data['meal_type'], desc)
                    bot.reply_to(message, '✅ Сохранено.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return
                if st.step == 'stool':
                    q = validate_stool_quality(text)
                    add_stool(user_id, st.data['date'], q)
                    bot.reply_to(message, '✅ Сохранено.',
                                 reply_markup=main_menu())
                    states.clear(user_id)
                    return

        except ValueError as e:
            bot.reply_to(message, f'❌ {e}')
            return

    th = threading.Thread(target=run_scheduler, args=(
        send_breakfast, send_lunch, send_dinner, send_toilet))
    th.daemon = True
    th.start()


def _show_today(bot: telebot.TeleBot, user_id: int, message_id: int) -> None:
    date_iso = _today_iso()
    date_disp = _today_display()

    meals = list_meals_for_day(user_id, date_iso)
    meds = list_medicines_for_day(user_id, date_iso)
    stools = list_stools_for_day(user_id, date_iso)
    feelings = list_feelings_for_day(user_id, date_iso)

    lines = [f'📋 <b>Записи за {date_disp}</b>\n']
    if not meals and not meds and not stools and not feelings:
        lines.append('За сегодня записей нет.')
    else:
        if meals:
            lines.append('<b>🍽️ Еда:</b>')
            meal_order = [
                ('breakfast', 'Завтрак'),
                ('lunch', 'Обед'),
                ('dinner', 'Ужин'),
                ('snack', 'Перекус'),
            ]
            grouped = {meal_type: [] for meal_type, _ in meal_order}
            for m in meals:
                if m['meal_type'] in grouped:
                    grouped[m['meal_type']].append(m)
            for meal_type, meal_title in meal_order:
                for m in grouped[meal_type]:
                    lines.append(
                        f'• <b>{meal_title}</b>: {m["description"]}'
                        f'\n(ред.: /edit_meal_{m["id"]})'
                        f'\n(удал.: /delete_meal_{m["id"]})\n'
                    )
        if meds:
            lines.append('\n<b>💊 Лекарства:</b>')
            for med in meds:
                dosage = (med['dosage'] or '').strip()
                tail = f' {dosage}' if dosage else ''
                lines.append(
                    f'• {med["name"]}{tail}'
                    f'\n(ред.: /edit_med_{med["id"]})'
                    f'\n(удал.: /delete_med_{med["id"]})\n'
                )
        if stools:
            lines.append('\n<b>🚽 Туалет:</b>')
            for s in stools:
                q = int(s['quality'])
                lines.append(
                    f'• {q} — {BRISTOL.get(q, "неизвестно")}'
                    f'\n(ред.: /edit_stool_{s["id"]})'
                    f'\n(удал.: /delete_stool_{s["id"]})\n'
                )
        if feelings:
            lines.append('\n<b>😊 Самочувствие:</b>')
            for f in feelings:
                lines.append(
                    f'• {f["description"]}'
                    f'\n(ред.: /edit_feeling_{f["id"]})'
                    f'\n(удал.: /delete_feeling_{f["id"]})\n'
                )

    bot.edit_message_text('\n'.join(lines), user_id,
                          message_id, reply_markup=back_to_main())


def _export_and_send(bot: telebot.TeleBot, user_id: int) -> None:
    try:
        xlsx = generate_user_report_xlsx(user_id)
        filename = f'Статистика_{datetime.now(APP_TZ).strftime("%Y%m%d_%H%M%S")}.xlsx'
        bot.send_document(user_id, xlsx, visible_file_name=filename,
                          caption='📊 Ваша полная статистика')
    except Exception as e:
        log.exception('Report error')
        bot.send_message(user_id, f'❌ Ошибка при формировании отчёта: {e}')
