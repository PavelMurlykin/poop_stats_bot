import logging
import time
from datetime import datetime, timedelta

from config import APP_TZ, DATE_FORMAT_STORAGE, SCHEDULER_TICK_SECONDS
from db.repositories import (ensure_sleep_for_day, get_all_users,
                             is_notification_sent, mark_notification_sent)

log = logging.getLogger(__name__)


def _plus_minutes_hhmm(time_str: str, minutes: int) -> str:
    """Return HH:MM with added minutes."""
    base = datetime.strptime(time_str, '%H:%M')
    shifted = base + timedelta(minutes=minutes)
    return shifted.strftime('%H:%M')


def run_scheduler(
    send_breakfast,
    send_lunch,
    send_dinner,
    send_toilet,
    send_sleep_quality,
) -> None:
    """Run scheduler loop."""
    log.info('Scheduler started')
    while True:
        try:
            now = datetime.now(APP_TZ)
            current_time = now.strftime('%H:%M')
            today = now.strftime(DATE_FORMAT_STORAGE)

            for user_id, bt, lt, dt, tt, wt, _ in get_all_users():
                ensure_sleep_for_day(user_id, today)

                if bt == current_time and not is_notification_sent(
                    user_id, 'breakfast', today
                ):
                    send_breakfast(user_id)
                    mark_notification_sent(user_id, 'breakfast', today)

                if lt == current_time and not is_notification_sent(
                    user_id, 'lunch', today
                ):
                    send_lunch(user_id)
                    mark_notification_sent(user_id, 'lunch', today)

                if dt == current_time and not is_notification_sent(
                    user_id, 'dinner', today
                ):
                    send_dinner(user_id)
                    mark_notification_sent(user_id, 'dinner', today)

                if tt == current_time and not is_notification_sent(
                    user_id, 'toilet', today
                ):
                    send_toilet(user_id)
                    mark_notification_sent(user_id, 'toilet', today)

                sleep_notification_time = _plus_minutes_hhmm(wt, 30)
                if sleep_notification_time == current_time and not is_notification_sent(
                    user_id, 'sleep_quality', today
                ):
                    send_sleep_quality(user_id)
                    mark_notification_sent(user_id, 'sleep_quality', today)

        except Exception:
            log.exception('Scheduler loop error')

        time.sleep(SCHEDULER_TICK_SECONDS)
