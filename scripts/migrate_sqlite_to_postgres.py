"""One-shot migration of prod data from SQLite to Postgres (Supabase).

Reads from instance/database_prod.db, inserts into the DB pointed to by
DATABASE_URL. Run once after `db.create_all()` + `flask db stamp head` have
populated the Postgres schema.

Idempotent only if the Postgres tables are empty — re-running with data
already present will fail on duplicate primary keys.
"""
import datetime
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.types import Interval

EPOCH = datetime.datetime(1970, 1, 1)


def coerce(value, dst_col):
    """SQLite stores Interval as datetime-from-epoch; Postgres needs a timedelta."""
    if value is None:
        return None
    if isinstance(value, datetime.datetime) and 'INTERVAL' in str(dst_col.type).upper():
        return value - EPOCH
    return value

load_dotenv()

SQLITE_URL = 'sqlite:///' + os.path.abspath('instance/database_prod.db')
PG_URL = os.environ.get('DATABASE_URL')
if not PG_URL:
    sys.exit('DATABASE_URL not set in .env')
if PG_URL.startswith('postgresql://'):
    PG_URL = 'postgresql+psycopg2://' + PG_URL[len('postgresql://'):]

# FK order: parents first.
TABLES = ['user', 'wish_item', 'note', 'backfill_review']

src = create_engine(SQLITE_URL)
dst = create_engine(PG_URL)

src_meta = MetaData()
dst_meta = MetaData()

for tname in TABLES:
    src_tbl = Table(tname, src_meta, autoload_with=src, quote=True)
    dst_tbl = Table(tname, dst_meta, autoload_with=dst, quote=True)
    common = sorted(set(c.name for c in src_tbl.columns)
                    & set(c.name for c in dst_tbl.columns))
    with src.connect() as sc:
        rows = sc.execute(src_tbl.select()).mappings().all()
    if not rows:
        print(f'{tname}: 0 rows (skipped)')
        continue
    payload = [{k: coerce(r[k], dst_tbl.c[k]) for k in common} for r in rows]
    with dst.begin() as dc:
        dc.execute(dst_tbl.insert(), payload)
    print(f'{tname}: {len(rows)} rows migrated')

print('Resetting Postgres sequences...')
with dst.begin() as dc:
    for tname in TABLES:
        dc.execute(text(
            f'SELECT setval(pg_get_serial_sequence(\'"{tname}"\', \'id\'), '
            f'COALESCE((SELECT MAX(id) FROM "{tname}"), 0) + 1, false)'
        ))
        print(f'  {tname}: sequence reset')

print('Done.')
