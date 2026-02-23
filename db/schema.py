from db.connection import with_db


@with_db
def init_db(cur) -> None:
    """Initialize database schema."""
    statements = [
        '''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            breakfast_time TEXT NOT NULL DEFAULT '08:00',
            lunch_time     TEXT NOT NULL DEFAULT '13:00',
            dinner_time    TEXT NOT NULL DEFAULT '19:00',
            toilet_time    TEXT NOT NULL DEFAULT '09:00',
            wakeup_time    TEXT NOT NULL DEFAULT '07:00',
            bed_time       TEXT NOT NULL DEFAULT '23:00',
            created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
        )
        ''',
        '''
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS wakeup_time TEXT NOT NULL DEFAULT '07:00'
        ''',
        '''
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS bed_time TEXT NOT NULL DEFAULT '23:00'
        ''',
        '''
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()
        ''',
        '''
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()
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
        CREATE TABLE IF NOT EXISTS water (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            glasses_count INTEGER NOT NULL DEFAULT 0 CHECK(glasses_count >= 0),
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS sleeps (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date DATE NOT NULL,
            wakeup_time TEXT NOT NULL,
            bed_time TEXT NOT NULL,
            quality_description TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS notifications_log (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            type TEXT NOT NULL CHECK(
                type IN ('breakfast', 'lunch', 'dinner', 'toilet', 'sleep_quality')
            ),
            date DATE NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, type, date),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
        ''',
        '''
        ALTER TABLE notifications_log
        DROP CONSTRAINT IF EXISTS notifications_log_type_check
        ''',
        '''
        ALTER TABLE notifications_log
        ADD CONSTRAINT notifications_log_type_check
        CHECK(type IN ('breakfast', 'lunch', 'dinner', 'toilet', 'sleep_quality'))
        ''',
        'CREATE INDEX IF NOT EXISTS idx_meals_user_date '
        'ON meals(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_medicines_user_date '
        'ON medicines(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_stools_user_date '
        'ON stools(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_feelings_user_date '
        'ON feelings(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_water_user_date '
        'ON water(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_sleeps_user_date '
        'ON sleeps(user_id, date)',
        'CREATE INDEX IF NOT EXISTS idx_notif_user_date_type '
        'ON notifications_log(user_id, date, type)',
    ]
    for statement in statements:
        cur.execute(statement)
