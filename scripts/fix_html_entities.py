"""One-time cleanup: decode HTML entities in WishItem text fields.

Some scraped/backfilled rows ended up with raw entities like '&amp;' or
'&#39;'. This script applies html.unescape() to name, brand, category,
tag, and description so 'Tiffany &amp; Co.' becomes 'Tiffany & Co.'.

Defaults to a dry run that prints proposed changes. Pass --apply to commit.

    FLASK_ENV=development python scripts/fix_html_entities.py
    FLASK_ENV=development python scripts/fix_html_entities.py --apply
    FLASK_ENV=production  python scripts/fix_html_entities.py --apply

Back up the database first (see scripts/backup_db.sh).
"""
import argparse
import os
import sys

# Make `website` importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from website import create_app, db
from website.models import WishItem, clean_text

FIELDS = ('name', 'brand', 'category', 'tag', 'description')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Actually commit changes. Without this flag the script is a dry run.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        items = WishItem.query.all()
        proposed = []  # list of (id, field, old, new)
        for item in items:
            for field in FIELDS:
                old = getattr(item, field)
                if old is None:
                    continue
                new = clean_text(old)
                if new != old:
                    proposed.append((item.id, field, old, new))

        if not proposed:
            print(f'No changes needed across {len(items)} item(s).')
            return

        affected_ids = sorted({i for i, *_ in proposed})
        print(f'{len(proposed)} field update(s) across {len(affected_ids)} item(s) of {len(items)}:')
        for item_id, field, old, new in proposed:
            print(f'  id={item_id:<5}  {field:<12} {old!r}  ->  {new!r}')

        if not args.apply:
            print('\nDry run. Re-run with --apply to commit these changes.')
            return

        for item_id, field, _, new in proposed:
            db.session.query(WishItem).filter(WishItem.id == item_id).update({field: new})
        db.session.commit()
        print(f'\nApplied {len(proposed)} update(s).')


if __name__ == '__main__':
    main()
