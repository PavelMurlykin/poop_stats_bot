# Poop Stats Bot (PostgreSQL)

## Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Copy env template and configure PostgreSQL connection:
```bash
cp .env.example .env
```
3. Fill `TELEGRAM_TOKEN` and PostgreSQL settings in `.env`.

## Migrate data from SQLite
If you have old `db.sqlite3`, run:
```bash
python scripts/migrate_sqlite_to_postgres.py
```

The script:
- creates PostgreSQL schema (if needed);
- migrates users/meals/medicines/stools/feelings/notifications;
- supports both old meal formats (`meal_type_id` and `meal_type`);
- syncs PostgreSQL sequences after import.

## Run bot
```bash
python main.py
```
