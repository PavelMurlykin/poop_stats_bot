import logging
import time
from datetime import datetime

from config import APP_TZ, DATE_FORMAT_STORAGE, SCHEDULER_TICK_SECONDS
from db.repositories import (get_all_users, is_notification_sent,
                             mark_notification_sent)

log = logging.getLogger(__name__)


def run_scheduler(
        send_breakfast,
        send_lunch,
        send_dinner,
        send_toilet) -> None:
    """Run scheduler."""
    log.info('Scheduler started')
    while True:
        try:
            now = datetime.now(APP_TZ)
            current_time = now.strftime('%H:%M')
            today = now.strftime(DATE_FORMAT_STORAGE)

            for user_id, bt, lt, dt, tt in get_all_users():
                if bt == current_time and not is_notification_sent(
                        user_id, 'breakfast', today):
                    send_breakfast(user_id)
                    mark_notification_sent(user_id, 'breakfast', today)
                if lt == current_time and not is_notification_sent(
                        user_id, 'lunch', today):
                    send_lunch(user_id)
                    mark_notification_sent(user_id, 'lunch', today)
                if dt == current_time and not is_notification_sent(
                        user_id, 'dinner', today):
                    send_dinner(user_id)
                    mark_notification_sent(user_id, 'dinner', today)
                if tt == current_time and not is_notification_sent(
                        user_id, 'toilet', today):
                    send_toilet(user_id)
                    mark_notification_sent(user_id, 'toilet', today)

        except Exception:
            log.exception('Scheduler loop error')
        time.sleep(SCHEDULER_TICK_SECONDS)
