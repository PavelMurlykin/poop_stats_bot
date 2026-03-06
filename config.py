"""Централизованная загрузка и валидация конфигурации приложения."""

import os
from typing import Final

import pytz
from dotenv import load_dotenv

load_dotenv()


def _read_env(name: str, default: str = '') -> str:
    """Возвращает строковое значение переменной окружения без пробелов.

    Args:
        name: Имя переменной окружения.
        default: Значение по умолчанию, если переменная отсутствует.

    Returns:
        str: Нормализованное значение переменной окружения.
    """
    return os.getenv(name, default).strip()


def _read_env_int(name: str, default: int) -> int:
    """Возвращает целочисленную переменную окружения.

    Args:
        name: Имя переменной окружения.
        default: Значение по умолчанию при отсутствии переменной.

    Returns:
        int: Преобразованное целое значение.
    """
    return int(_read_env(name, str(default)))


TELEGRAM_TOKEN: Final[str] = _read_env('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise RuntimeError('TELEGRAM_TOKEN не установлен, добавьте его в .env')

DATABASE_URL: Final[str] = _read_env('DATABASE_URL')
PG_HOST: Final[str] = _read_env('PG_HOST', 'localhost')
PG_PORT: Final[int] = _read_env_int('PG_PORT', 5432)
PG_DB: Final[str] = _read_env('PG_DB', 'poop_stats_bot')
PG_USER: Final[str] = _read_env('PG_USER', 'postgres')
PG_PASSWORD: Final[str] = _read_env('PG_PASSWORD')
PG_CONNECT_TIMEOUT: Final[int] = _read_env_int('PG_CONNECT_TIMEOUT', 10)

DATE_FORMAT_STORAGE: Final[str] = '%Y-%m-%d'
DATE_FORMAT_DISPLAY: Final[str] = '%d.%m.%Y'

TZ_NAME: Final[str] = _read_env('TZ_NAME', 'Europe/Moscow')
APP_TZ: Final[pytz.BaseTzInfo] = pytz.timezone(TZ_NAME)

SCHEDULER_TICK_SECONDS: Final[int] = _read_env_int(
    'SCHEDULER_TICK_SECONDS',
    20,
)
MAX_TEXT_LENGTH: Final[int] = _read_env_int('MAX_TEXT_LENGTH', 1000)
POLLING_TIMEOUT: Final[int] = _read_env_int('POLLING_TIMEOUT', 30)
LONG_POLLING_TIMEOUT: Final[int] = _read_env_int(
    'LONG_POLLING_TIMEOUT',
    30,
)
