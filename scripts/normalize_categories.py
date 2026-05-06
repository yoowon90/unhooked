"""One-time cleanup: capitalize the first character of every WishItem.category.

Defaults to a dry run that prints proposed changes. Pass --apply to commit.

Run against dev or prod by setting FLASK_ENV before invoking:
    FLASK_ENV=development python scripts/normalize_categories.py
    FLASK_ENV=development python scripts/normalize_categories.py --apply
    FLASK_ENV=production  python scripts/normalize_categories.py --apply

Back up the database first (see scripts/backup_db.sh).
"""
import argparse
import os
import sys

# Make `website` importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from website import create_app, db
from website.models import WishItem, normalize_category


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true',
                        help='Actually commit changes. Without this flag the script is a dry run.')
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        items = WishItem.query.all()
        proposed = []
        for item in items:
            new_value = normalize_category(item.category) if item.category else item.category
            if new_value != item.category:
                proposed.append((item.id, item.category, new_value))

        if not proposed:
            print(f'No changes needed. {len(items)} item(s) already normalized.')
            return

        print(f'{len(proposed)} of {len(items)} item(s) would change:')
        for item_id, old, new in proposed:
            print(f'  id={item_id:<5}  {old!r:30s} -> {new!r}')

        if not args.apply:
            print('\nDry run. Re-run with --apply to commit these changes.')
            return

        for item_id, _, new in proposed:
            db.session.query(WishItem).filter(WishItem.id == item_id).update({'category': new})
        db.session.commit()
        print(f'\nApplied {len(proposed)} update(s).')


if __name__ == '__main__':
    main()
