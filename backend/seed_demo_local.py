"""Explicit local-only test catalogue population; NEVER run on production."""
import os

url = os.environ.get('DATABASE_URL', '')
if (
    os.environ.get('APP_ENV') != 'development'
    or not url.startswith('sqlite:')
    or os.environ.get('CONFIRM_LOCAL_DEMO_SEED') != 'YES'
):
    raise SystemExit(
        'Refusing demo data import. Requires APP_ENV=development, an SQLite '
        'DATABASE_URL and CONFIRM_LOCAL_DEMO_SEED=YES.'
    )

from app.main import seed
seed()
print('Local demonstration catalogue created.')
