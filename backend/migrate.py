"""Additive database migration executed before FastAPI app imports models.

The migration does not destroy user data and is safe to rerun. Longer-term migrations
should be maintained with Alembic after this initial PWA bridge release.
"""
import os
from sqlalchemy import create_engine, inspect, text

url=os.environ.get('DATABASE_URL', '')
if not url:
    raise SystemExit('DATABASE_URL must be configured for deployment')
if url.startswith('postgres://'):
    url='postgresql+psycopg://' + url[len('postgres://'):]
elif url.startswith('postgresql://'):
    url='postgresql+psycopg://' + url[len('postgresql://'):]
engine=create_engine(url, pool_pre_ping=True)
with engine.begin() as con:
    tables=set(inspect(con).get_table_names())
    if 'episodes' in tables:
        columns={c['name'] for c in inspect(con).get_columns('episodes')}
        if 'bunny_video_id' not in columns:
            con.execute(text('ALTER TABLE episodes ADD COLUMN bunny_video_id VARCHAR(64)'))
        con.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_episodes_bunny_video_id ON episodes (bunny_video_id)'))
print('KISA additive migration complete')
