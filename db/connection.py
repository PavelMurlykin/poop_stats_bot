import psycopg
from psycopg.rows import dict_row
from config import (
    DATABASE_URL,
    PG_HOST,
    PG_PORT,
    PG_DB,
    PG_USER,
    PG_PASSWORD,
    PG_CONNECT_TIMEOUT,
)


def get_connection() -> psycopg.Connection:
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


def with_db(fn):
    # Decorator: opens connection, commits/rolls back, closes.
    def wrapper(*args, **kwargs):
        conn = get_connection()
        try:
            cur = conn.cursor()
            res = fn(cur, *args, **kwargs)
            conn.commit()
            return res
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return wrapper
