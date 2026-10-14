"""KISA database schema-only migration; safe to run before each API boot.

Creates missing tables and applies explicit additive migrations for known columns.
Never seeds sample users, shows, episodes, wallets or payments; existing data stays intact.
For further model changes, add an explicit Alembic migration rather than dropping tables.
"""
import os
from sqlalchemy import create_engine, inspect, text

url = os.environ.get('DATABASE_URL', '')
if not url:
    raise SystemExit('DATABASE_URL must be configured for deployment')
if url.startswith('postgres://'):
    url = 'postgresql+psycopg://' + url[len('postgres://'):]
elif url.startswith('postgresql://'):
    url = 'postgresql+psycopg://' + url[len('postgresql://'):]

engine = create_engine(url, pool_pre_ping=True)

# Existing databases can be missing columns introduced by later application versions.
# Add these before importing the mapped models; model metadata.create_all() only
# creates missing tables, not missing columns in already-existing tables.
with engine.begin() as conn:
    tables = set(inspect(conn).get_table_names())
    additions = {
        'shows': {
            'poster_url': 'TEXT',
            'is_published': 'BOOLEAN NOT NULL DEFAULT TRUE',
        },
        'episodes': {
            'bunny_video_id': 'VARCHAR(64)',
            'is_published': 'BOOLEAN NOT NULL DEFAULT TRUE',
        },
    }
    for table, specs in additions.items():
        if table not in tables:
            continue
        columns = {c['name'] for c in inspect(conn).get_columns(table)}
        for column, ddl in specs.items():
            if column not in columns:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
                print(f'KISA schema: added {table}.{column}')
    if 'episodes' in tables:
        conn.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS ix_episodes_bunny_video_id '
            'ON episodes (bunny_video_id)'
        ))

# Import has NO seed side effects. Schema metadata creates any newly missing tables.
from app.main import Base, engine as app_engine  # noqa: E402
Base.metadata.create_all(bind=app_engine)
print('KISA schema-only migration complete. No sample data inserted.')
