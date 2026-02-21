from db.connection import with_db


@with_db
def init_db(cur) -> None:
    """Инициализация БД. Создание таблиц."""
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
            meal_type TEXT NOT NULL CHECK(
                meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')
            ),
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
            type TEXT NOT NULL CHECK(
                type IN ('breakfast', 'lunch', 'dinner', 'toilet')
            ),
            date DATE NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, type, date),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        'CREATE INDEX IF NOT EXISTS idx_meals_user_date '
        'ON meals(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_medicines_user_date '
        'ON medicines(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_stools_user_date '
        'ON stools(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_feelings_user_date '
        'ON feelings(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_notif_user_date_type '
        'ON notifications_log(user_id, date, type)',
    ]
    for statement in statements:
        cur.execute(statement)
