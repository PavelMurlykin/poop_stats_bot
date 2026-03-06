"""Утилиты подключения к PostgreSQL и обёртки транзакций."""

from collections.abc import Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

import psycopg
from psycopg.rows import dict_row

from config import (DATABASE_URL, PG_CONNECT_TIMEOUT, PG_DB, PG_HOST,
                    PG_PASSWORD, PG_PORT, PG_USER)

P = ParamSpec('P')
R = TypeVar('R')


def get_connection() -> psycopg.Connection:
    """Создаёт новое подключение к PostgreSQL с `dict_row` row factory.

    Returns:
        psycopg.Connection: Активное подключение к базе данных.
    """
    if DATABASE_URL:
        return psycopg.connect(
            DATABASE_URL,
            connect_timeout=PG_CONNECT_TIMEOUT,
            row_factory=dict_row,
        )
    return psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD,
        connect_timeout=PG_CONNECT_TIMEOUT,
        row_factory=dict_row,
    )


def with_db(
    function_to_wrap: Callable[Concatenate[psycopg.Cursor, P], R],
) -> Callable[P, R]:
    """Оборачивает репозиторную функцию в транзакцию PostgreSQL.

    Функция, помеченная декоратором, получает первым аргументом курсор и
    автоматически выполняется в рамках одной транзакции: при успехе делается
    `commit`, при любой ошибке выполняется `rollback`.

    Args:
        function_to_wrap: Репозиторная функция вида
            `func(cursor, *args, **kwargs)`.

    Returns:
        Callable[P, R]: Обёрнутая функция с сохранённой сигнатурой.
    """

    @wraps(function_to_wrap)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        """Выполняет обёрнутую функцию в транзакции и закрывает подключение.

        Args:
            *args: Позиционные аргументы исходной функции без курсора.
            **kwargs: Именованные аргументы исходной функции.

        Returns:
            R: Результат выполнения обёрнутой функции.
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                result = function_to_wrap(cursor, *args, **kwargs)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    return wrapper
