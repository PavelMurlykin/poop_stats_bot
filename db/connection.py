import psycopg
from psycopg.rows import dict_row

from config import (DATABASE_URL, PG_CONNECT_TIMEOUT, PG_DB, PG_HOST,
                    PG_PASSWORD, PG_PORT, PG_USER)


def get_connection() -> psycopg.Connection:
    """
    Выполняет операцию `get_connection` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Returns:
        psycopg.Connection: Результат выполнения функции.
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


def with_db(function_to_wrap):
    """
    Выполняет операцию `with_db` в бизнес-логике модуля.

    Функция используется внутри приложения и поддерживает контракт между
    компонентами.

    Args:
        function_to_wrap: Параметр `function_to_wrap` для текущего шага
                          обработки.

    Returns:
        Ноне: Возвращаемое значение отсутствует.
    """
    def wrapper(*args, **kwargs):
        """
        Выполняет операцию `wrapper` в бизнес-логике модуля.

        Функция используется внутри приложения и поддерживает контракт между
        компонентами.

        Args:
            args: Параметр `args` для текущего шага обработки.
            kwargs: Параметр `kwargs` для текущего шага обработки.

        Returns:
            Ноне: Возвращаемое значение отсутствует.
        """
        connection = get_connection()
        try:
            cursor = connection.cursor()
            result = function_to_wrap(cursor, *args, **kwargs)
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    return wrapper
