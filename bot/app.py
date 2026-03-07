import logging
import re
import threading
import unicodedata
from datetime import datetime
from html import escape

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import (BotCommand, CallbackQuery, MenuButtonCommands,
                           Message, ForceReply)

from bot.keyboards import (back_to_main, confirm_delete, edit_timetable_menu,
                           main_menu, manual_menu)
from bot.scheduler import run_scheduler
from bot.states import StateStore, UserState
from bot.validators import (validate_date_display, validate_stool_quality,
                            validate_text, validate_time_hhmm)
from config import (APP_TZ, DATE_FORMAT_DISPLAY, DATE_FORMAT_STORAGE,
                    TELEGRAM_TOKEN)
from db.repositories import (add_feeling, add_medicine, add_stool,
                             delete_feeling, delete_meal, delete_medicine,
                             delete_stool, ensure_sleep_for_day,
                             get_feeling_by_id, get_meal_by_id,
                             get_medicine_by_id, get_sleep_for_day,
                             get_stool_by_id, get_user_times,
                             get_water_for_day, increment_water,
                             list_feelings_for_day, list_meals_for_day,
                             list_medicines_for_day, list_stools_for_day,
                             register_user, set_water_for_day, update_feeling,
                             update_meal, update_medicine, update_stool,
                             update_user_time, upsert_meal,
                             upsert_sleep_quality, upsert_sleep_times)
from db.schema import init_db
from services.report_service import BRISTOL, generate_user_report_xlsx

log = logging.getLogger(__name__)

OPTIONAL_DATE_COMMAND_PATTERN = r'(?:_((?:\d{8})|(?:\d{4}-\d{2}-\d{2})))?$'
EDIT_MEAL_PATTERN = rf'^/edit_meal_(\d+){OPTIONAL_DATE_COMMAND_PATTERN}'
EDIT_MED_PATTERN = rf'^/edit_med_(\d+){OPTIONAL_DATE_COMMAND_PATTERN}'
EDIT_STOOL_PATTERN = rf'^/edit_stool_(\d+){OPTIONAL_DATE_COMMAND_PATTERN}'
EDIT_FEELING_PATTERN = (
    rf'^/edit_feeling_(\d+){OPTIONAL_DATE_COMMAND_PATTERN}'
)
EDIT_WATER_PATTERN = rf'^/edit_water{OPTIONAL_DATE_COMMAND_PATTERN}'
EDIT_SLEEP_WAKEUP_PATTERN = (
    rf'^/edit_sleep_wakeup{OPTIONAL_DATE_COMMAND_PATTERN}'
)
EDIT_SLEEP_BED_PATTERN = rf'^/edit_sleep_bed{OPTIONAL_DATE_COMMAND_PATTERN}'
EDIT_SLEEP_QUALITY_PATTERN = (
    rf'^/edit_sleep_quality{OPTIONAL_DATE_COMMAND_PATTERN}'
)
DELETE_COMMAND_PATTERN = (
    rf'^/delete_(meal|med|stool|feeling)_(\d+)'
    rf'{OPTIONAL_DATE_COMMAND_PATTERN}'
)


def create_bot() -> telebot.TeleBot:
    """
    Выполняет операцию `create_bot` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        telebot.TeleBot: Результат выполнения функции.
    """
    return telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')


def _safe_delete_message(
    bot: telebot.TeleBot,
    chat_id: int,
    message_id: int,
) -> None:
    """Удаляет сообщение Telegram и игнорирует ожидаемые ошибки API.

    Args:
        bot: Экземпляр Telegram-бота для вызова метода удаления.
        chat_id: Идентификатор чата в Telegram.
        message_id: Идентификатор удаляемого сообщения.

    Returns:
        None: Возвращаемое значение отсутствует.
    """
    try:
        bot.delete_message(chat_id, message_id)
    except ApiTelegramException as error:
        error_text = str(error).lower()
        ignored_errors = (
            'message to delete not found',
            'message can\'t be deleted',
            'message identifier is not specified',
        )
        if any(pattern in error_text for pattern in ignored_errors):
            return
        raise


def _delete_messages_in_background(
    bot: telebot.TeleBot,
    chat_id: int,
    message_ids: list[int],
) -> None:
    """Удаляет список сообщений в отдельном потоке без блокировки UI-ответа."""
    unique_ids = list(dict.fromkeys(message_ids))
    if not unique_ids:
        return

    def _delete_task() -> None:
        for target_message_id in unique_ids:
            _safe_delete_message(bot, chat_id, target_message_id)

    delete_thread = threading.Thread(target=_delete_task)
    delete_thread.daemon = True
    delete_thread.start()


def _today_iso() -> str:
    """
    Выполняет операцию `_today_iso` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        str: Результат выполнения функции.
    """
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_STORAGE)


def _today_display() -> str:
    """
    Выполняет операцию `_today_display` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        str: Результат выполнения функции.
    """
    return datetime.now(APP_TZ).strftime(DATE_FORMAT_DISPLAY)


def _display_date(date_iso: str) -> str:
    """
    Преобразует дату из формата хранения в пользовательский формат.

    Args:
        date_iso: Дата в формате хранения.

    Returns:
        str: Дата в пользовательском формате.
    """
    return datetime.strptime(date_iso, DATE_FORMAT_STORAGE).strftime(
        DATE_FORMAT_DISPLAY
    )


def _date_to_command_token(date_iso: str) -> str:
    """
    Возвращает безопасный для Telegram-команды токен даты.

    Args:
        date_iso: Дата в формате хранения.

    Returns:
        str: Токен даты без дефисов.
    """
    return date_iso.replace('-', '')


def _date_from_command_token(token: str | None) -> str | None:
    """
    Преобразует токен даты из команды в формат хранения.

    Args:
        token: Токен из текста команды.

    Returns:
        str | None: Дата в формате хранения или `None`.
    """
    if not token:
        return None
    if re.fullmatch(r'\d{8}', token):
        return datetime.strptime(token, '%Y%m%d').strftime(DATE_FORMAT_STORAGE)
    return token


def _help_text() -> str:
    """
    Формирует краткую инструкцию по использованию бота.

    Returns:
        str: Текст подсказки для команды `/help` и пункта «Помощь».
    """
    return (
        'ℹ️ <b>Как пользоваться ботом</b>\n'
        '1. Откройте <b>⏰ Расписание</b> и настройте время напоминаний.\n'
        '2. Через <b>➕ Добавить событие</b> вносите еду, воду, лекарства, '
        'туалет, самочувствие и сон.\n'
        '3. В <b>📋 Дневная статистика</b> смотрите записи за сегодня, '
        'редактируйте и удаляйте их.\n'
        '4. <b>📥 Полная статистика</b> выгружает '
        'Excel-отчёт за весь период.\n'
        '5. <b>📊 Бристольская шкала</b> помогает выбрать оценку стула.\n\n'
        '<b>Команды:</b> /menu — меню, '
        '/cancel — отменить текущий ввод.'
    )


def _bristol_scale_prompt() -> str:
    """Возвращает текст-подсказку для ввода оценки по шкале Бристоля.

    Returns:
        str: Сформированный текст с описаниями значений от 0 до 7.
    """
    lines = ['🚽 Оцените качество стула по Бристольской шкале:\n']
    default_label = 'неизвестно'
    for key in range(0, 8):
        lines.append(f'{key} — {BRISTOL.get(key, default_label)}')
    lines.append('\nВведите цифру от 0 до 7:')
    return '\n'.join(lines)


def _configure_telegram_commands(bot: telebot.TeleBot) -> None:
    """
    Выполняет операцию `_configure_telegram_commands` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        bot: Экземпляр Telegram-бота для отправки и редактирования сообщений.

    Returns:
        None: Возвращаемое значение отсутствует.
    """
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
            bot.set_chat_menu_button(
                menu_button=MenuButtonCommands('commands'))
        except ApiTelegramException as error:
            log.warning('Failed to set menu button: %s', error)
    except ApiTelegramException as error:
        log.warning('Failed to set menu button: %s', error)


def _display_width(value: str) -> int:
    """
    Выполняет операцию `_display_width` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        value: Входное значение для проверки или обработки.

    Returns:
        int: Результат выполнения функции.
    """
    width = 0
    for char in value:
        if unicodedata.combining(char):
            continue
        if unicodedata.category(char) == 'Cf':
            continue
        width += 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1
    return width


def _pad_cell(value: str, width: int) -> str:
    """
    Выполняет операцию `_pad_cell` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        value: Входное значение для проверки или обработки.
        width: Параметр `width` для текущего шага обработки.

    Returns:
        str: Результат выполнения функции.
    """
    return value + (' ' * max(0, width - _display_width(value)))


def _format_timetable_table(
    breakfast: str,
    lunch: str,
    dinner: str,
    toilet: str,
    wakeup: str,
    bed: str,
) -> str:
    """
    Выполняет операцию `_format_timetable_table` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        breakfast: Параметр `breakfast` для текущего шага обработки.
        lunch: Параметр `lunch` для текущего шага обработки.
        dinner: Параметр `dinner` для текущего шага обработки.
        toilet: Параметр `toilet` для текущего шага обработки.
        wakeup: Параметр `wakeup` для текущего шага обработки.
        bed: Параметр `bed` для текущего шага обработки.

    Returns:
        str: Результат выполнения функции.
    """
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
        (
            f'| {_pad_cell(left_header, left_width)} | '
            f'{_pad_cell(right_header, right_width)} |'
        ),
        separator,
    ]
    for name, value in normalized_rows:
        lines.append(
            (
                f'| {_pad_cell(name, left_width)} | '
                f'{_pad_cell(value, right_width)} |'
            ))
    lines.append(separator)
    return '<pre>' + '\n'.join(lines) + '</pre>'


def build_app(bot: telebot.TeleBot) -> None:
    """
    Выполняет операцию `build_app` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        bot: Экземпляр Telegram-бота для отправки и редактирования сообщений.

    Returns:
        None: Возвращаемое значение отсутствует.
    """
    init_db()
    _configure_telegram_commands(bot)
    states = StateStore()
    stats_context: dict[int, dict[str, int | str]] = {}
    ui_messages: dict[int, int] = {}

    def _set_ui_message(user_id: int, message_id: int) -> None:
        """Запоминает последнее сообщение бота для пользователя.

        Args:
            user_id: Идентификатор пользователя Telegram.
            message_id: Идентификатор отправленного сообщения бота.
        """
        ui_messages[user_id] = message_id

    def _get_ui_message(user_id: int) -> int | None:
        """Возвращает последнее сообщение бота для пользователя.

        Args:
            user_id: Идентификатор пользователя Telegram.

        Returns:
            int | None: Идентификатор сообщения или `None`.
        """
        return ui_messages.get(user_id)

    def _send_fresh_message(
        user_id: int,
        text: str,
        reply_markup=None,
        replace_message_id: int | None = None,
    ) -> int:
        """Отправляет новое сообщение и удаляет старое в фоне.

        Args:
            user_id: Идентификатор пользователя Telegram.
            text: Текст нового сообщения.
            reply_markup: Inline-клавиатура нового сообщения.
            replace_message_id: Явный `message_id` для удаления.

        Returns:
            int: Идентификатор нового сообщения.
        """
        message_ids_to_remove: list[int] = []
        if replace_message_id is not None:
            message_ids_to_remove.append(replace_message_id)

        tracked_message_id = _get_ui_message(user_id)
        if (
            tracked_message_id is not None
            and tracked_message_id not in message_ids_to_remove
        ):
            message_ids_to_remove.append(tracked_message_id)

        sent_message = bot.send_message(
            user_id,
            text,
            reply_markup=reply_markup,
        )
        _set_ui_message(user_id, sent_message.message_id)
        _delete_messages_in_background(bot, user_id, message_ids_to_remove)
        return sent_message.message_id

    def _replace_message_fresh(
        user_id: int,
        message_id: int,
        text: str,
        reply_markup=None,
    ) -> int:
        """Заменяет сообщение бота новым сообщением в чате.

        Args:
            user_id: Идентификатор пользователя Telegram.
            message_id: Идентификатор удаляемого сообщения.
            text: Текст нового сообщения.
            reply_markup: Inline-клавиатура нового сообщения.

        Returns:
            int: Идентификатор нового сообщения.
        """
        return _send_fresh_message(
            user_id,
            text,
            reply_markup=reply_markup,
            replace_message_id=message_id,
        )

    def _reply_fresh(
        message: Message,
        text: str,
        reply_markup=None,
    ) -> int:
        """Отправляет «чистый» ответ бота пользователю.

        Args:
            message: Пользовательское сообщение-источник.
            text: Текст ответа бота.
            reply_markup: Inline-клавиатура нового сообщения.

        Returns:
            int: Идентификатор нового сообщения.
        """
        return _send_fresh_message(
            message.from_user.id,
            text,
            reply_markup=reply_markup,
        )

    def _set_stats_context(
        user_id: int,
        message_id: int,
        date_iso: str,
    ) -> None:
        stats_context[user_id] = {
            'message_id': message_id,
            'date': date_iso,
        }

    def _clear_stats_context(user_id: int) -> None:
        stats_context.pop(user_id, None)

    def _get_stats_context(user_id: int) -> dict[str, int | str] | None:
        return stats_context.get(user_id)

    def _stats_context_matches(user_id: int, message_id: int) -> bool:
        context = _get_stats_context(user_id)
        if not context:
            return False
        return context['message_id'] == message_id

    def _show_stats(
        message_id: int,
        user_id: int,
        date_iso: str | None = None,
        status_text: str | None = None,
    ) -> None:
        normalized_date = date_iso or _today_iso()
        new_message_id = _show_today(
            bot,
            user_id,
            message_id,
            normalized_date,
            status_text=status_text,
        )
        _set_stats_context(user_id, new_message_id, normalized_date)
        _set_ui_message(user_id, new_message_id)

    def _refresh_stats_context(
        user_id: int,
        status_text: str | None = None,
    ) -> bool:
        context = _get_stats_context(user_id)
        if not context:
            return False
        date_iso = str(context['date'])
        new_message_id = _show_today(
            bot,
            user_id,
            int(context['message_id']),
            date_iso,
            status_text=status_text,
        )
        _set_stats_context(user_id, new_message_id, date_iso)
        _set_ui_message(user_id, new_message_id)
        return True

    def _reply_after_change(
        message: Message,
        text: str,
        return_to_stats: bool,
    ) -> None:
        if return_to_stats and _refresh_stats_context(
            message.from_user.id,
            status_text=text,
        ):
            return
        _reply_fresh(message, text, reply_markup=main_menu())

    def _safe_placeholder(value: str, limit: int = 64) -> str:
        """Возвращает безопасный placeholder для поля ввода Telegram.

        Args:
            value: Значение, которое нужно отобразить в поле ввода.
            limit: Максимальная длина placeholder.

        Returns:
            str: Укороченное значение для `input_field_placeholder`.
        """
        clean_value = value.strip()
        if len(clean_value) <= limit:
            return clean_value
        return clean_value[:limit - 3].rstrip() + '...'

    def _prompt_edit_with_current_value(
        message: Message,
        prompt: str,
        current_value: str,
    ) -> int:
        """Показывает текущую запись и просит ввести новое значение.

        Args:
            message: Входящее сообщение пользователя.
            prompt: Базовый текст запроса на редактирование.
            current_value: Текущее значение из базы данных.

        Returns:
            int: Идентификатор отправленного сообщения.
        """
        active_state = states.get(message.from_user.id)
        if not active_state or active_state.kind != 'edit':
            return _reply_fresh(message, prompt)

        safe_value = current_value.strip()
        if not safe_value:
            return _reply_fresh(message, prompt)

        message_text = (
            f'{prompt}\n\n'
            f'Текущее значение:\n'
            f'<code>{escape(safe_value)}</code>'
        )
        force_reply = ForceReply(
            selective=False,
            input_field_placeholder=_safe_placeholder(safe_value),
        )
        return _reply_fresh(message, message_text, reply_markup=force_reply)

    def _stats_date_for_interaction(
        user_id: int,
        message_id: int | None = None,
    ) -> str:
        context = _get_stats_context(user_id)
        if not context:
            return _today_iso()
        if message_id is not None and context['message_id'] != message_id:
            return _today_iso()
        return str(context['date'])

    def _has_stats_context(user_id: int) -> bool:
        """Проверяет, есть ли активный контекст экрана статистики.

        Args:
            user_id: Идентификатор пользователя Telegram.

        Returns:
            bool: `True`, если контекст статистики присутствует.
        """
        return _get_stats_context(user_id) is not None

    def _set_state(
        user_id: int,
        kind: str,
        step: str,
        data: dict[str, int | str | bool] | None = None,
    ) -> None:
        """Сохраняет состояние сценария для пользователя.

        Args:
            user_id: Идентификатор пользователя Telegram.
            kind: Тип состояния диалога.
            step: Текущий шаг состояния.
            data: Дополнительные данные шага.
        """
        states.set(user_id, UserState(kind, step, data or {}))

    def _state_date_iso(state: UserState) -> str:
        """Возвращает дату события из состояния пользователя.

        Args:
            state: Состояние диалога пользователя.

        Returns:
            str: Дата в формате хранения `YYYY-MM-DD`.
        """
        date_iso = state.data.get('date')
        if isinstance(date_iso, str):
            return date_iso
        return _today_iso()

    def _event_name_for_state(state: UserState) -> str:
        """Возвращает название события в предложном падеже.

        Args:
            state: Состояние диалога пользователя.

        Returns:
            str: Название события для информационного сообщения.
        """
        meal_names = {
            'breakfast': 'завтраке',
            'lunch': 'обеде',
            'dinner': 'ужине',
            'snack': 'перекусе',
        }
        if state.step in ('meal_desc', 'meal'):
            meal_type = state.data.get('meal_type')
            if isinstance(meal_type, str):
                return meal_names.get(meal_type, 'приеме пищи')
            return 'приеме пищи'

        event_names = {
            'med_dosage': 'приеме лекарства',
            'stool_quality': 'качестве стула',
            'stool': 'качестве стула',
            'feeling_desc': 'самочувствии',
            'sleep_wakeup_today': 'времени подъема',
            'sleep_wakeup_time': 'времени подъема',
            'sleep_bed_today': 'времени отхода ко сну',
            'sleep_bed_time': 'времени отхода ко сну',
            'sleep_quality_today': 'качестве сна',
            'sleep_quality_desc': 'качестве сна',
            'sleep_quality': 'качестве сна',
            'water_count_today': 'воде',
        }
        return event_names.get(state.step, 'событии')

    def _record_save_message(action: str, state: UserState) -> str:
        """Формирует информационный текст об изменении записи.

        Args:
            action: Глагол действия (`Добавлена`, `Изменена`).
            state: Состояние диалога пользователя.

        Returns:
            str: Готовый текст сообщения для пользователя.
        """
        date_display = _display_date(_state_date_iso(state))
        event_name = _event_name_for_state(state)
        return f'✅ {action} запись о {event_name} за {date_display}.'

    def _ask_meal_question(
        user_id: int,
        meal_type: str,
        question: str,
    ) -> None:
        """Отправляет вопрос о приёме пищи и включает ожидание ввода.

        Args:
            user_id: Идентификатор пользователя Telegram.
            meal_type: Тип приёма пищи (`breakfast`, `lunch`, `dinner`).
            question: Текст вопроса для пользователя.
        """
        _send_fresh_message(
            user_id,
            question,
            reply_markup=back_to_main(),
        )
        _set_state(
            user_id,
            'pending_question',
            'meal',
            {'meal_type': meal_type, 'date': _today_iso()},
        )

    def send_breakfast(user_id: int) -> None:
        """
        Отправляет сообщение для следующего шага сценария.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _ask_meal_question(user_id, 'breakfast', '🍳 Что вы ели на завтрак?')

    def send_lunch(user_id: int) -> None:
        """
        Отправляет сообщение для следующего шага сценария.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _ask_meal_question(user_id, 'lunch', '🍲 Что вы ели на обед?')

    def send_dinner(user_id: int) -> None:
        """
        Отправляет сообщение для следующего шага сценария.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _ask_meal_question(user_id, 'dinner', '🍽️ Что вы ели на ужин?')

    def send_toilet(user_id: int) -> None:
        """
        Отправляет сообщение для следующего шага сценария.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _send_fresh_message(
            user_id,
            _bristol_scale_prompt(),
            reply_markup=back_to_main(),
        )
        _set_state(
            user_id,
            'pending_question',
            'stool',
            {'date': _today_iso()},
        )

    def send_sleep_quality(user_id: int) -> None:
        """
        Отправляет сообщение для следующего шага сценария.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            user_id: Идентификатор пользователя в Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        ensure_sleep_for_day(user_id, _today_iso())
        _send_fresh_message(
            user_id,
            '🛌 Как вы оцениваете качество сна этой ночью?',
            reply_markup=back_to_main(),
        )
        _set_state(
            user_id,
            'pending_question',
            'sleep_quality',
            {'date': _today_iso()},
        )

    @bot.message_handler(commands=['start'])
    def cmd_start(message: Message):
        """
        Обрабатывает команду Telegram, полученную от пользователя.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        user_id = message.from_user.id
        _clear_stats_context(user_id)
        register_user(user_id)
        ensure_sleep_for_day(user_id, _today_iso())
        _send_fresh_message(
            user_id,
            (
                '👋 Привет! Бот помогает вести дневник питания, '
                'самочувствия и сна.\n'
                'Используйте меню ниже для настройки расписания '
                'и добавления событий.'
            ),
            reply_markup=main_menu(),
        )

    @bot.message_handler(commands=['menu'])
    def cmd_menu(message: Message):
        """
        Обрабатывает команду Telegram, полученную от пользователя.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _clear_stats_context(message.from_user.id)
        _send_fresh_message(
            message.from_user.id,
            'Главное меню:',
            reply_markup=main_menu(),
        )

    @bot.message_handler(commands=['cancel'])
    def cmd_cancel(message: Message):
        """
        Обрабатывает команду Telegram, полученную от пользователя.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        states.clear(message.from_user.id)
        _clear_stats_context(message.from_user.id)
        _send_fresh_message(
            message.from_user.id,
            '✅ Ожидание отменено.',
            reply_markup=main_menu(),
        )

    @bot.message_handler(commands=['help'])
    def cmd_help(message: Message):
        """
        Обрабатывает команду Telegram, полученную от пользователя.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        _send_fresh_message(
            message.from_user.id,
            _help_text(),
            reply_markup=back_to_main(),
        )

    @bot.message_handler(regexp=EDIT_MEAL_PATTERN)
    def edit_meal_cmd(message: Message):
        """
        Выполняет операцию `edit_meal_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_MEAL_PATTERN, message.text)
        meal_id = int(match.group(1))
        meal = get_meal_by_id(message.from_user.id, meal_id)
        if not meal:
            _reply_fresh(message, '❌ Запись не найдена / нет прав.')
            return
        date_iso = (
            _date_from_command_token(match.group(2))
            or _stats_date_for_interaction(message.from_user.id)
        )
        _set_state(
            message.from_user.id,
            'edit',
            'meal_desc',
            {
                'id': meal_id,
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        meal_label_by_type = {
            'breakfast': 'завтрака',
            'lunch': 'обеда',
            'dinner': 'ужина',
            'snack': 'перекуса',
        }
        meal_type = str(meal.get('meal_type') or '')
        meal_label = meal_label_by_type.get(meal_type, 'приема пищи')
        _prompt_edit_with_current_value(
            message,
            f'Введите новое описание {meal_label}:',
            str(meal['description']),
        )

    @bot.message_handler(regexp=EDIT_MED_PATTERN)
    def edit_med_cmd(message: Message):
        """
        Выполняет операцию `edit_med_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_MED_PATTERN, message.text)
        med_id = int(match.group(1))
        medicine = get_medicine_by_id(message.from_user.id, med_id)
        if not medicine:
            _reply_fresh(message, '❌ Запись не найдена / нет прав.')
            return
        date_iso = (
            _date_from_command_token(match.group(2))
            or _stats_date_for_interaction(message.from_user.id)
        )
        _set_state(
            message.from_user.id,
            'edit',
            'med_name',
            {
                'id': med_id,
                'date': date_iso,
                'current_dosage': (medicine.get('dosage') or '').strip(),
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        _prompt_edit_with_current_value(
            message,
            'Введите новое название:',
            str(medicine['name']),
        )

    @bot.message_handler(regexp=EDIT_STOOL_PATTERN)
    def edit_stool_cmd(message: Message):
        """
        Выполняет операцию `edit_stool_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_STOOL_PATTERN, message.text)
        stool_id = int(match.group(1))
        stool = get_stool_by_id(message.from_user.id, stool_id)
        if not stool:
            _reply_fresh(message, '❌ Запись не найдена / нет прав.')
            return
        date_iso = (
            _date_from_command_token(match.group(2))
            or _stats_date_for_interaction(message.from_user.id)
        )
        _set_state(
            message.from_user.id,
            'edit',
            'stool_quality',
            {
                'id': stool_id,
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        _prompt_edit_with_current_value(
            message,
            _bristol_scale_prompt(),
            str(stool['quality']),
        )

    @bot.message_handler(regexp=EDIT_FEELING_PATTERN)
    def edit_feeling_cmd(message: Message):
        """
        Выполняет операцию `edit_feeling_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_FEELING_PATTERN, message.text)
        feeling_id = int(match.group(1))
        feeling = get_feeling_by_id(message.from_user.id, feeling_id)
        if not feeling:
            _reply_fresh(message, '❌ Запись не найдена / нет прав.')
            return
        date_iso = (
            _date_from_command_token(match.group(2))
            or _stats_date_for_interaction(message.from_user.id)
        )
        _set_state(
            message.from_user.id,
            'edit',
            'feeling_desc',
            {
                'id': feeling_id,
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        _prompt_edit_with_current_value(
            message,
            'Введите новое описание самочувствия:',
            str(feeling['description']),
        )

    @bot.message_handler(regexp=EDIT_WATER_PATTERN)
    def edit_water_cmd(message: Message):
        """
        Выполняет операцию `edit_water_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_WATER_PATTERN, message.text)
        date_iso = _date_from_command_token(match.group(1)) or _today_iso()
        current_water = get_water_for_day(message.from_user.id, date_iso)
        _set_state(
            message.from_user.id,
            'edit',
            'water_count_today',
            {
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        _prompt_edit_with_current_value(
            message,
            (
                'Введите количество стаканов воды за '
                f'{_display_date(date_iso)} (целое число, 0+):'
            ),
            str(current_water),
        )

    @bot.message_handler(regexp=EDIT_SLEEP_WAKEUP_PATTERN)
    def edit_sleep_wakeup_cmd(message: Message):
        """
        Выполняет операцию `edit_sleep_wakeup_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_SLEEP_WAKEUP_PATTERN, message.text)
        date_iso = _date_from_command_token(match.group(1)) or _today_iso()
        sleep = ensure_sleep_for_day(message.from_user.id, date_iso)
        _set_state(
            message.from_user.id,
            'edit',
            'sleep_wakeup_today',
            {
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        wakeup_time = str((sleep or {}).get('wakeup_time') or '--:--')
        _prompt_edit_with_current_value(
            message,
            (
                'Введите время подъема за '
                f'{_display_date(date_iso)} в формате ЧЧ:ММ:'
            ),
            wakeup_time,
        )

    @bot.message_handler(regexp=EDIT_SLEEP_BED_PATTERN)
    def edit_sleep_bed_cmd(message: Message):
        """
        Выполняет операцию `edit_sleep_bed_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_SLEEP_BED_PATTERN, message.text)
        date_iso = _date_from_command_token(match.group(1)) or _today_iso()
        sleep = ensure_sleep_for_day(message.from_user.id, date_iso)
        _set_state(
            message.from_user.id,
            'edit',
            'sleep_bed_today',
            {
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        bed_time = str((sleep or {}).get('bed_time') or '--:--')
        _prompt_edit_with_current_value(
            message,
            (
                'Введите время отхода ко сну за '
                f'{_display_date(date_iso)} в формате ЧЧ:ММ:'
            ),
            bed_time,
        )

    @bot.message_handler(regexp=EDIT_SLEEP_QUALITY_PATTERN)
    def edit_sleep_quality_cmd(message: Message):
        """
        Выполняет операцию `edit_sleep_quality_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(EDIT_SLEEP_QUALITY_PATTERN, message.text)
        date_iso = _date_from_command_token(match.group(1)) or _today_iso()
        sleep = ensure_sleep_for_day(message.from_user.id, date_iso)
        _set_state(
            message.from_user.id,
            'edit',
            'sleep_quality_today',
            {
                'date': date_iso,
                'return_to_stats': _has_stats_context(message.from_user.id),
            },
        )
        quality = str((sleep or {}).get('quality_description') or '')
        _prompt_edit_with_current_value(
            message,
            f'Введите описание качества сна за {_display_date(date_iso)}:',
            quality,
        )

    @bot.message_handler(regexp=DELETE_COMMAND_PATTERN)
    def delete_cmd(message: Message):
        """
        Выполняет операцию `delete_cmd` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        match = re.match(DELETE_COMMAND_PATTERN, message.text)
        item_type = match.group(1)
        item_id = int(match.group(2))
        date_iso = (
            _date_from_command_token(match.group(3))
            or _stats_date_for_interaction(message.from_user.id)
        )
        _send_fresh_message(
            message.from_user.id,
            '❓ Вы уверены, что хотите удалить эту запись?',
            reply_markup=confirm_delete(item_type, item_id, date_iso),
        )

    @bot.callback_query_handler(func=lambda _: True)
    def on_callback(call: CallbackQuery):
        """
        Обрабатывает нажатия inline-кнопок интерфейса.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            call: Объект callback-запроса от inline-кнопки.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        user_id = call.from_user.id
        data = call.data or ''

        if data == 'back_to_main':
            _clear_stats_context(user_id)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                'Главное меню:',
                reply_markup=main_menu(),
            )
            states.clear(user_id)
            return

        if data == 'show_timetable':
            times = get_user_times(user_id)
            if not times:
                _replace_message_fresh(
                    user_id,
                    call.message.message_id,
                    '❌ Вы не зарегистрированы. Напишите /start',
                    reply_markup=back_to_main(),
                )
                return
            breakfast, lunch, dinner, toilet, wakeup, bed = times
            text = (
                '⏰ <b>Ваше расписание:</b>\n'
                f'{_format_timetable_table(
                    breakfast,
                    lunch,
                    dinner,
                    toilet,
                    wakeup,
                    bed,
                )}\n\n'
                'Нажмите кнопку, чтобы изменить время.'
            )
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                text,
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
            prompt_text = (
                f'Введите время <b>{slot_name}</b> в формате ЧЧ:ММ '
                f'(например, {example_time}):'
            )
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                prompt_text,
            )
            _set_state(user_id, 'awaiting_time', 'time', {'slot': slot})
            return

        if data == 'manual_menu':
            if not _stats_context_matches(user_id, call.message.message_id):
                _clear_stats_context(user_id)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '➕ Добавить событие: выберите тип записи',
                reply_markup=manual_menu(),
            )
            return

        if data.startswith('manual_meal_'):
            meal_type = data.replace('manual_meal_', '')
            meal_names = {
                'breakfast': 'завтрака',
                'lunch': 'обеда',
                'dinner': 'ужина',
                'snack': 'перекуса',
            }
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            meal_name = meal_names.get(meal_type, 'приема пищи')
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                f'🍽️ Введите описание {meal_name}:',
            )
            _set_state(
                user_id,
                'manual',
                'meal_desc',
                {
                    'meal_type': meal_type,
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_medicine':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '💊 Введите название лекарства:',
            )
            _set_state(
                user_id,
                'manual',
                'med_name',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_stool':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                _bristol_scale_prompt(),
            )
            _set_state(
                user_id,
                'manual',
                'stool_quality',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_feeling':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '😊 Опишите ваше самочувствие:',
            )
            _set_state(
                user_id,
                'manual',
                'feeling_desc',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_sleep_wakeup':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            ensure_sleep_for_day(user_id, target_date)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '🌅 Введите фактическое время подъема (ЧЧ:ММ):',
            )
            _set_state(
                user_id,
                'manual',
                'sleep_wakeup_time',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_sleep_bed':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            ensure_sleep_for_day(user_id, target_date)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '🌙 Введите фактическое время отхода ко сну (ЧЧ:ММ):',
            )
            _set_state(
                user_id,
                'manual',
                'sleep_bed_time',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_sleep_quality':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            ensure_sleep_for_day(user_id, target_date)
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                '🛌 Опишите качество сна:',
            )
            _set_state(
                user_id,
                'manual',
                'sleep_quality_desc',
                {
                    'date': target_date,
                    'return_to_stats': _stats_context_matches(
                        user_id,
                        call.message.message_id,
                    ),
                },
            )
            return

        if data == 'manual_water':
            target_date = _stats_date_for_interaction(
                user_id, call.message.message_id)
            total_glasses = increment_water(user_id, target_date)
            states.clear(user_id)
            bot.answer_callback_query(call.id, text='✅ Добавлен стакан воды.')
            if _stats_context_matches(user_id, call.message.message_id):
                _show_stats(call.message.message_id, user_id, target_date)
            else:
                _replace_message_fresh(
                    user_id,
                    call.message.message_id,
                    f'💧 Добавлен стакан воды. Сегодня: {total_glasses}.',
                    reply_markup=manual_menu(),
                )
            return

        if data == 'show_today':
            _show_stats(call.message.message_id, user_id)
            return

        if data == 'show_stats_by_date':
            new_message_id = _replace_message_fresh(
                user_id,
                call.message.message_id,
                (
                    '🗓 Введите дату в формате ДД.ММ.ГГГГ, '
                    'за которую нужна статистика:'
                ),
                reply_markup=back_to_main(),
            )
            _set_state(
                user_id,
                'pending_question',
                'stats_date',
                {'message_id': new_message_id},
            )
            return

        if data == 'help':
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                _help_text(),
                reply_markup=back_to_main(),
            )
            return

        if data == 'bristol':
            text = '📊 <b>Бристольская шкала:</b>\n' + '\n'.join(
                [f'{key} — {BRISTOL[key]}' for key in range(0, 8)]
            )
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                text,
                reply_markup=back_to_main(),
            )
            return

        if data == 'cancel_delete':
            _replace_message_fresh(
                user_id,
                call.message.message_id,
                'Удаление отменено.',
                reply_markup=back_to_main(),
            )
            return

        if data.startswith('confirm_delete:'):
            parts = data.split(':', 3)
            _, item_type, item_id_s = parts[:3]
            date_iso = parts[3] if len(parts) > 3 else None
            item_id = int(item_id_s)
            is_successful = False
            if item_type == 'meal':
                is_successful = delete_meal(user_id, item_id)
            elif item_type == 'med':
                is_successful = delete_medicine(user_id, item_id)
            elif item_type == 'stool':
                is_successful = delete_stool(user_id, item_id)
            elif item_type == 'feeling':
                is_successful = delete_feeling(user_id, item_id)

            bot.answer_callback_query(
                call.id,
                text=(
                    'Удалено'
                    if is_successful
                    else 'Не найдено / нет прав'
                ))
            status_text = (
                '✅ Запись удалена.'
                if is_successful
                else '❌ Не найдено / нет прав.'
            )
            context = _get_stats_context(user_id)
            if date_iso and context:
                _set_stats_context(
                    user_id,
                    int(context['message_id']),
                    date_iso,
                )
            if not _refresh_stats_context(user_id, status_text=status_text):
                _show_stats(
                    call.message.message_id,
                    user_id,
                    date_iso,
                    status_text=status_text,
                )
            return

        if data == 'export_all_stats':
            bot.answer_callback_query(call.id, text='Формирую отчёт…')
            _send_fresh_message(
                user_id,
                '🔄 Формирую отчёт. Это может занять некоторое время.',
            )
            thread = threading.Thread(
                target=_export_and_send, args=(bot, user_id))
            thread.daemon = True
            thread.start()
            return

    @bot.message_handler(func=lambda _: True)
    def on_text(message: Message):
        """
        Обрабатывает текстовый ввод с учетом текущего состояния.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            message: Входящее сообщение от пользователя Telegram.

        Returns:
            None: Возвращаемое значение отсутствует.
        """
        user_id = message.from_user.id
        text = (message.text or '').strip()
        state = states.get(user_id)

        if not state:
            _reply_fresh(
                message,
                'Я не ожидаю ввод. Используйте /menu.',
                reply_markup=main_menu(),
            )
            return

        if state.kind == 'edit':
            try:
                if state.step == 'meal_desc':
                    desc = validate_text(text)
                    is_successful = update_meal(
                        user_id, state.data['id'], desc)
                    status_text = (
                        _record_save_message('Изменена', state)
                        if is_successful
                        else '❌ Не найдено / нет прав.'
                    )
                    _reply_after_change(
                        message,
                        status_text,
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'med_name':
                    name = validate_text(text)
                    state.step = 'med_dosage'
                    state.data['name'] = name
                    current_dosage = str(
                        state.data.get('current_dosage') or '-',
                    )
                    _prompt_edit_with_current_value(
                        message,
                        'Введите новую дозировку (или "-"):',
                        current_dosage,
                    )
                    return

                if state.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    is_successful = update_medicine(
                        user_id, state.data['id'], state.data['name'], dosage)
                    status_text = (
                        _record_save_message('Изменена', state)
                        if is_successful
                        else '❌ Не найдено / нет прав.'
                    )
                    _reply_after_change(
                        message,
                        status_text,
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'stool_quality':
                    quality = validate_stool_quality(text)
                    is_successful = update_stool(
                        user_id, state.data['id'], quality)
                    status_text = (
                        _record_save_message('Изменена', state)
                        if is_successful
                        else '❌ Не найдено / нет прав.'
                    )
                    _reply_after_change(
                        message,
                        status_text,
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'feeling_desc':
                    desc = validate_text(text)
                    is_successful = update_feeling(
                        user_id, state.data['id'], desc)
                    status_text = (
                        _record_save_message('Изменена', state)
                        if is_successful
                        else '❌ Не найдено / нет прав.'
                    )
                    _reply_after_change(
                        message,
                        status_text,
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return
                if state.step == 'water_count_today':
                    if not text.isdigit():
                        raise ValueError('Введите целое число от 0 и больше.')
                    water_count = int(text)
                    set_water_for_day(user_id, state.data['date'], water_count)
                    _reply_after_change(
                        message,
                        _record_save_message('Изменена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_wakeup_today':
                    if not validate_time_hhmm(text):
                        raise ValueError(
                            'Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(
                        user_id, state.data['date'], wakeup_time=text)
                    _reply_after_change(
                        message,
                        _record_save_message('Изменена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_bed_today':
                    if not validate_time_hhmm(text):
                        raise ValueError(
                            'Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(
                        user_id, state.data['date'], bed_time=text)
                    _reply_after_change(
                        message,
                        _record_save_message('Изменена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_quality_today':
                    desc = validate_text(text)
                    upsert_sleep_quality(user_id, state.data['date'], desc)
                    _reply_after_change(
                        message,
                        _record_save_message('Изменена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

            except ValueError as error:
                _reply_fresh(message, f'❌ {error}')
                return

        if state.kind == 'awaiting_time':
            if not validate_time_hhmm(text):
                _reply_fresh(
                    message,
                    '❌ Неверный формат. Введите время ЧЧ:ММ.',
                    reply_markup=main_menu(),
                )
                return

            slot = state.data['slot']
            is_successful = update_user_time(user_id, slot, text)
            if is_successful and slot == 'wakeup':
                upsert_sleep_times(user_id, _today_iso(), wakeup_time=text)
            if is_successful and slot == 'bed':
                upsert_sleep_times(user_id, _today_iso(), bed_time=text)

            _reply_fresh(
                message,
                (
                    '✅ Время сохранено.'
                    if is_successful
                    else '❌ Ошибка сохранения.'
                ),
                reply_markup=main_menu(),
            )
            states.clear(user_id)
            return

        try:
            if state.kind == 'manual':
                if state.step == 'meal_desc':
                    desc = validate_text(text)
                    upsert_meal(
                        user_id,
                        state.data['date'],
                        state.data['meal_type'],
                        desc,
                    )
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'med_name':
                    name = validate_text(text)
                    state.step = 'med_dosage'
                    state.data['name'] = name
                    _reply_fresh(
                        message,
                        (
                            'Введите дозировку (или "-" '
                            'чтобы пропустить):'
                        ),
                    )
                    return

                if state.step == 'med_dosage':
                    dosage = None if text == '-' else validate_text(text)
                    add_medicine(
                        user_id,
                        state.data['date'],
                        state.data['name'],
                        dosage,
                    )
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'stool_quality':
                    quality = validate_stool_quality(text)
                    add_stool(user_id, state.data['date'], quality)
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'feeling_desc':
                    desc = validate_text(text)
                    add_feeling(user_id, state.data['date'], desc)
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_wakeup_time':
                    if not validate_time_hhmm(text):
                        raise ValueError(
                            'Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(
                        user_id, state.data['date'], wakeup_time=text)
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_bed_time':
                    if not validate_time_hhmm(text):
                        raise ValueError(
                            'Неверный формат. Введите время ЧЧ:ММ.')
                    upsert_sleep_times(
                        user_id, state.data['date'], bed_time=text)
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_quality_desc':
                    desc = validate_text(text)
                    upsert_sleep_quality(user_id, state.data['date'], desc)
                    _reply_after_change(
                        message,
                        _record_save_message('Добавлена', state),
                        bool(state.data.get('return_to_stats')),
                    )
                    states.clear(user_id)
                    return

            if state.kind == 'pending_question':
                if state.step == 'stats_date':
                    date_iso = validate_date_display(text)
                    _show_stats(
                        int(state.data['message_id']),
                        user_id,
                        date_iso,
                    )
                    states.clear(user_id)
                    return

                if state.step == 'meal':
                    desc = validate_text(text)
                    upsert_meal(
                        user_id,
                        state.data['date'],
                        state.data['meal_type'],
                        desc,
                    )
                    _reply_fresh(
                        message,
                        _record_save_message('Добавлена', state),
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'stool':
                    quality = validate_stool_quality(text)
                    add_stool(user_id, state.data['date'], quality)
                    _reply_fresh(
                        message,
                        _record_save_message('Добавлена', state),
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return

                if state.step == 'sleep_quality':
                    desc = validate_text(text)
                    upsert_sleep_quality(user_id, state.data['date'], desc)
                    _reply_fresh(
                        message,
                        _record_save_message('Добавлена', state),
                        reply_markup=main_menu(),
                    )
                    states.clear(user_id)
                    return
        except ValueError as error:
            _reply_fresh(message, f'❌ {error}')
            return

    thread = threading.Thread(
        target=run_scheduler,
        args=(send_breakfast, send_lunch, send_dinner,
              send_toilet, send_sleep_quality),
    )
    thread.daemon = True
    thread.start()


def _show_today(
    bot: telebot.TeleBot,
    user_id: int,
    message_id: int,
    date_iso: str | None = None,
    status_text: str | None = None,
) -> int:
    """
    Выполняет операцию `_show_today` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        bot: Экземпляр Telegram-бота для отправки и редактирования сообщений.
        user_id: Идентификатор пользователя в Telegram.
        message_id: Идентификатор сообщения в Telegram.
        date_iso: Дата статистики в формате хранения. По умолчанию сегодня.
        status_text: Дополнительный статус перед содержимым статистики.

    Returns:
        int: Идентификатор нового сообщения со статистикой.
    """
    date_iso = date_iso or _today_iso()
    date_display = _display_date(date_iso)
    is_today = date_iso == _today_iso()
    if is_today:
        dated_command_suffix = ''
    else:
        dated_command_suffix = f'_{_date_to_command_token(date_iso)}'

    ensure_sleep_for_day(user_id, date_iso)
    sleep = get_sleep_for_day(user_id, date_iso)
    meals = list_meals_for_day(user_id, date_iso)
    medicines = list_medicines_for_day(user_id, date_iso)
    stools = list_stools_for_day(user_id, date_iso)
    feelings = list_feelings_for_day(user_id, date_iso)
    water_glasses = get_water_for_day(user_id, date_iso)

    lines: list[str] = []
    if status_text:
        lines.append(status_text)
    lines.append(f'<b>Записи за {date_display}</b>\n')

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
                    f'\n(ред.: /edit_meal_{meal_id}{dated_command_suffix})'
                    f'\n(удал.: /delete_meal_{meal_id}'
                    f'{dated_command_suffix})\n'
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
                f'\n(ред.: /edit_med_{medicine_id}{dated_command_suffix})'
                f'\n(удал.: /delete_med_{medicine_id}'
                f'{dated_command_suffix})\n'
            )

    if stools:
        lines.append('\n🚽 <b>Туалет:</b>')
        for stool in stools:
            stool_id = stool['id']
            quality = int(stool['quality'])
            quality_text = BRISTOL.get(quality, 'неизвестно')
            lines.append(
                f'- {quality} - {quality_text}'
                f'\n(ред.: /edit_stool_{stool_id}{dated_command_suffix})'
                f'\n(удал.: /delete_stool_{stool_id}'
                f'{dated_command_suffix})\n'
            )

    if feelings:
        lines.append('\n😊 <b>Самочувствие:</b>')
        for feeling in feelings:
            feeling_id = feeling['id']
            feeling_desc = feeling['description']
            lines.append(
                f'- {feeling_desc}'
                f'\n(ред.: /edit_feeling_{feeling_id}{dated_command_suffix})'
                f'\n(удал.: /delete_feeling_{feeling_id}'
                f'{dated_command_suffix})\n'
            )
    lines.append('\n💧 <b>Вода:</b>')
    lines.append(
        f'- Выпито стаканов: {water_glasses}'
        f'\n(ред.: /edit_water{dated_command_suffix})\n'
    )

    wakeup_time = '--:--'
    bed_time = '--:--'
    quality_desc = 'не указано'
    if sleep:
        wakeup_time = sleep.get('wakeup_time', '--:--')
        bed_time = sleep.get('bed_time', '--:--')
        quality_desc = (sleep.get('quality_description')
                        or '').strip() or 'не указано'

    lines.append('\n🛌 <b>Сон:</b>')
    lines.append(
        (
            f'- Подъем: {wakeup_time}\n'
            f'(ред.: /edit_sleep_wakeup{dated_command_suffix})\n'
        )
    )
    lines.append(
        (
            f'- Отход ко сну: {bed_time}\n'
            f'(ред.: /edit_sleep_bed{dated_command_suffix})\n'
        )
    )
    lines.append(
        (
            f'- Качество сна: {quality_desc}\n'
            f'(ред.: /edit_sleep_quality{dated_command_suffix})\n'
        )
    )

    if len(lines) == 1:
        lines.append(f'За {date_display} записей нет.')

    lines.append('Добавить новое событие:')

    sent_message = bot.send_message(
        user_id,
        '\n'.join(lines),
        reply_markup=manual_menu(),
    )
    _delete_messages_in_background(bot, user_id, [message_id])
    return sent_message.message_id


def _export_and_send(bot: telebot.TeleBot, user_id: int) -> None:
    """
    Выполняет операцию `_export_and_send` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        bot: Экземпляр Telegram-бота для отправки и редактирования сообщений.
        user_id: Идентификатор пользователя в Telegram.

    Returns:
        None: Возвращаемое значение отсутствует.
    """
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
