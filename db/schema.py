from db.connection import with_db


def _column_type(cur, table_name: str, column_name: str) -> str | None:
    cur.execute(
        '''
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        ''',
        (table_name, column_name),
    )
    row = cur.fetchone()
    return row['data_type'] if row else None


def _migrate_temporal_columns(cur) -> None:
    date_columns = [
        ('meals', 'date'),
        ('medicines', 'date'),
        ('stools', 'date'),
        ('feelings', 'date'),
        ('notifications_log', 'date'),
    ]
    ts_columns = [
        ('meals', 'created_at'),
        ('meals', 'updated_at'),
        ('medicines', 'created_at'),
        ('medicines', 'updated_at'),
        ('stools', 'created_at'),
        ('stools', 'updated_at'),
        ('feelings', 'created_at'),
        ('feelings', 'updated_at'),
    ]

    for table_name, column_name in date_columns:
        dtype = _column_type(cur, table_name, column_name)
        if dtype and dtype != 'date':
            if dtype in ('text', 'character varying'):
                cur.execute(
                    f'''
                    ALTER TABLE {table_name}
                    ALTER COLUMN {column_name} TYPE DATE
                    USING CASE
                        WHEN {column_name} ~ '^[0-9]{{2}}\\.[0-9]{{2}}\\.[0-9]{{4}}$'
                            THEN to_date({column_name}, 'DD.MM.YYYY')
                        ELSE {column_name}::date
                    END
                    '''
                )
                continue
            cur.execute(
                f'''
                ALTER TABLE {table_name}
                ALTER COLUMN {column_name} TYPE DATE
                USING {column_name}::date
                '''
            )

    for table_name, column_name in ts_columns:
        dtype = _column_type(cur, table_name, column_name)
        if not dtype or dtype == 'timestamp without time zone':
            continue
        if dtype == 'timestamp with time zone':
            cur.execute(
                f'''
                ALTER TABLE {table_name}
                ALTER COLUMN {column_name} TYPE TIMESTAMP
                USING ({column_name} AT TIME ZONE 'UTC')
                '''
            )
            continue
        cur.execute(
            f'''
            ALTER TABLE {table_name}
            ALTER COLUMN {column_name} TYPE TIMESTAMP
            USING {column_name}::timestamp
            '''
        )


@with_db
def init_db(cur) -> None:
    statements = [
        '''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            breakfast_time TEXT NOT NULL DEFAULT '08:00',
            lunch_time     TEXT NOT NULL DEFAULT '13:00',
            dinner_time    TEXT NOT NULL DEFAULT '19:00',
            toilet_time    TEXT NOT NULL DEFAULT '09:00'
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS meals (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            meal_type TEXT NOT NULL CHECK(meal_type IN ('breakfast','lunch','dinner','snack')),
            description TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS medicines (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            name TEXT NOT NULL,
            dosage TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS stools (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            quality INTEGER NOT NULL CHECK(quality BETWEEN 0 AND 7),
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS feelings (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS notifications_log (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('breakfast','lunch','dinner','toilet')),
            date DATE NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, type, date),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        'CREATE INDEX IF NOT EXISTS idx_meals_user_date      ON meals(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_medicines_user_date  ON medicines(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_stools_user_date     ON stools(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_feelings_user_date   ON feelings(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_notif_user_date_type ON notifications_log(user_id, date, type)',
    ]
    for statement in statements:
        cur.execute(statement)
    _migrate_temporal_columns(cur)
