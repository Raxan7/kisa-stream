"""The production startup pathway must never inject demonstration records."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_migration_creates_schema_without_seeding_even_when_flag_is_true(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    db_path = tmp_path / 'production_candidate.db'
    env = dict(os.environ)
    env.update({
        'DATABASE_URL': f'sqlite:///{db_path}',
        'APP_ENV': 'development',
        'SEED_DEMO': 'true',  # Must no longer trigger implicit seeding.
        'DEMO_MODE': 'false',
        'PAYMENT_MODE': 'disabled',
        'JWT_SECRET': 'test-only-secret-for-schema-migration-test-0000',
        'ADMIN_API_KEY': 'test-only-admin-key-for-schema-migration-test-0000',
    })

    def migrate():
        result = subprocess.run(
            [sys.executable, 'migrate.py'], cwd=backend, env=env,
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'No sample data inserted' in result.stdout

    migrate()
    with sqlite3.connect(db_path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'shows', 'episodes', 'users', 'payments', 'wallet_entries', 'entitlements'} <= tables
        for table in ('shows','episodes','users','payments','wallet_entries'):
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        assert 'bunny_video_id' in {r[1] for r in conn.execute('PRAGMA table_info(episodes)')}
        # Verify existing records are not deleted on re-run.
        conn.execute("INSERT INTO shows (id,title,synopsis,genre,accent,poster_url,is_published) "
                     "VALUES ('manual','Real Movie','Real story','Drama','#101010',NULL,1)")
        conn.commit()
    migrate()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute('SELECT count(*) FROM shows').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM episodes').fetchone()[0] == 0


def test_demo_seed_command_requires_local_opt_in(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.update({
        'DATABASE_URL': f'sqlite:///{tmp_path / "db.sqlite"}',
        'APP_ENV': 'production',
        'CONFIRM_LOCAL_DEMO_SEED': 'YES',
    })
    r = subprocess.run([sys.executable,'seed_demo_local.py'], cwd=backend, env=env,
                       capture_output=True,text=True,timeout=10)
    assert r.returncode != 0
    assert 'Refusing demo data import' in r.stderr + r.stdout
