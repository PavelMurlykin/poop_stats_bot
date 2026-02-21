import os

import pytz
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '').strip()
if not TELEGRAM_TOKEN:
    raise RuntimeError('TELEGRAM_TOKEN не установлен, добавьте его в .env')

DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
PG_HOST = os.getenv('PG_HOST', 'localhost').strip()
PG_PORT = int(os.getenv('PG_PORT', '5432'))
PG_DB = os.getenv('PG_DB', 'poop_stats_bot').strip()
PG_USER = os.getenv('PG_USER', 'postgres').strip()
PG_PASSWORD = os.getenv('PG_PASSWORD', '').strip()
PG_CONNECT_TIMEOUT = int(os.getenv('PG_CONNECT_TIMEOUT', '10'))

DATE_FORMAT_STORAGE = '%Y-%m-%d'
DATE_FORMAT_DISPLAY = '%d.%m.%Y'

TZ_NAME = os.getenv('TZ_NAME', 'Europe/Moscow').strip()
APP_TZ = pytz.timezone(TZ_NAME)

SCHEDULER_TICK_SECONDS = int(os.getenv('SCHEDULER_TICK_SECONDS', '20'))

MAX_TEXT_LENGTH = int(os.getenv('MAX_TEXT_LENGTH', '1000'))

POLLING_TIMEOUT = int(os.getenv('POLLING_TIMEOUT', '30'))
LONG_POLLING_TIMEOUT = int(os.getenv('LONG_POLLING_TIMEOUT', '30'))
