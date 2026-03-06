"""Планировщик напоминаний бота по пользовательскому расписанию."""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from config import APP_TZ, DATE_FORMAT_STORAGE, SCHEDULER_TICK_SECONDS
from db.repositories import (ensure_sleep_for_day, get_all_users,
                             is_notification_sent, mark_notification_sent)

log = logging.getLogger(__name__)
NotificationSender = Callable[[int], None]


def _plus_minutes_hhmm(time_str: str, minutes: int) -> str:
    """Сдвигает время `ЧЧ:ММ` на заданное число минут.

    Args:
        time_str: Базовое время в формате `ЧЧ:ММ`.
        minutes: Количество минут для смещения.

    Returns:
        str: Новое время в формате `ЧЧ:ММ`.
    """
    base = datetime.strptime(time_str, '%H:%M')
    shifted = base + timedelta(minutes=minutes)
    return shifted.strftime('%H:%M')


def _notify_once_per_day(
    sender: NotificationSender,
    user_id: int,
    notification_type: str,
    current_time: str,
    scheduled_time: str,
    date_iso: str,
) -> None:
    """Отправляет напоминание, если оно запланировано на текущую минуту.

    Args:
        sender: Функция отправки уведомления конкретного типа.
        user_id: Идентификатор пользователя Telegram.
        notification_type: Тип события для журнала уведомлений.
        current_time: Текущее время в формате `ЧЧ:ММ`.
        scheduled_time: Плановое время уведомления в формате `ЧЧ:ММ`.
        date_iso: Текущая дата в формате хранения `YYYY-MM-DD`.
    """
    if scheduled_time != current_time:
        return
    if is_notification_sent(user_id, notification_type, date_iso):
        return
    sender(user_id)
    mark_notification_sent(user_id, notification_type, date_iso)


def run_scheduler(
    send_breakfast: NotificationSender,
    send_lunch: NotificationSender,
    send_dinner: NotificationSender,
    send_toilet: NotificationSender,
    send_sleep_quality: NotificationSender,
) -> None:
    """Запускает бесконечный цикл проверки и отправки напоминаний.

    Args:
        send_breakfast: Отправка вопроса о завтраке.
        send_lunch: Отправка вопроса об обеде.
        send_dinner: Отправка вопроса об ужине.
        send_toilet: Отправка вопроса о качестве стула.
        send_sleep_quality: Отправка вопроса о качестве сна.
    """
    log.info('Scheduler started')
    while True:
        try:
            now = datetime.now(APP_TZ)
            current_time = now.strftime('%H:%M')
            today_iso = now.strftime(DATE_FORMAT_STORAGE)

            for (
                user_id,
                breakfast_time,
                lunch_time,
                dinner_time,
                toilet_time,
                wakeup_time,
                _,
            ) in get_all_users():
                ensure_sleep_for_day(user_id, today_iso)
                _notify_once_per_day(
                    send_breakfast,
                    user_id,
                    'breakfast',
                    current_time,
                    breakfast_time,
                    today_iso,
                )
                _notify_once_per_day(
                    send_lunch,
                    user_id,
                    'lunch',
                    current_time,
                    lunch_time,
                    today_iso,
                )
                _notify_once_per_day(
                    send_dinner,
                    user_id,
                    'dinner',
                    current_time,
                    dinner_time,
                    today_iso,
                )
                _notify_once_per_day(
                    send_toilet,
                    user_id,
                    'toilet',
                    current_time,
                    toilet_time,
                    today_iso,
                )
                sleep_quality_time = _plus_minutes_hhmm(wakeup_time, 30)
                _notify_once_per_day(
                    send_sleep_quality,
                    user_id,
                    'sleep_quality',
                    current_time,
                    sleep_quality_time,
                    today_iso,
                )
        except Exception:
            log.exception('Scheduler loop error')

        time.sleep(SCHEDULER_TICK_SECONDS)
