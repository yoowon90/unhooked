#!/usr/bin/env python3
"""Debug the Gmail backfill flow without persisting anything to the DB.

Loads the connected Gmail tokens for a given user from the dev DB, runs the
exact same scan query and Claude prompt the live /backfill/scan endpoint uses,
and dumps:
  - per-email Claude classification (order confirmation? what items? what qty?)
  - cross-email dedup grouping (which emails would merge into which card)
  - within-order duplicate-line detection (same name+price appearing twice)

Usage:
    python scripts/debug_email_parse.py --user yoowon@airops.com --days 30
    python scripts/debug_email_parse.py --user yoowon@airops.com --days 30 --limit 10
    python scripts/debug_email_parse.py --user yoowon@airops.com --output /tmp/foo.json

The full dump (every email body, every Claude response) is written to
/tmp/email_parse_debug.json by default — never the repo.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Make the repo root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# These must be set before any OAuth lib imports
os.environ.setdefault('OAUTHLIB_INSECURE_TRANSPORT', '1')
os.environ.setdefault('FLASK_ENV', 'development')

import anthropic
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from website import create_app
from website.models import User
from website.backfill import (
    GMAIL_SCOPES,
    ORDER_QUERY,
    _extract_body,
    _parse_order_with_claude,
    _dedupe_orders_within_scan,
)


def get_service_for_user(user):
    creds = Credentials(
        token=user.gmail_access_token,
        refresh_token=user.gmail_refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        scopes=GMAIL_SCOPES,
        expiry=user.gmail_token_expiry,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build('gmail', 'v1', credentials=creds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True, help='Unhooked account email (not the Gmail mailbox)')
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--limit', type=int, default=60, help='Max emails to fetch from Gmail')
    ap.add_argument('--output', default='/tmp/email_parse_debug.json')
    args = ap.parse_args()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=args.user).first()
        if not user:
            print(f'No user found with Unhooked email {args.user!r}.')
            sys.exit(1)
        if not user.gmail_access_token:
            print(f'User {args.user} has no Gmail tokens stored. Connect first via the app.')
            sys.exit(1)

        print(f'User: {user.email}  →  Gmail mailbox: {user.gmail_connected_email}')
        print(f'Window: last {args.days} days, max {args.limit} emails\n')

        service = get_service_for_user(user)
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        query = f'{ORDER_QUERY} newer_than:{args.days}d'
        results = service.users().messages().list(userId='me', q=query, maxResults=args.limit).execute()
        messages = results.get('messages', [])
        print(f'Subject filter matched {len(messages)} emails.')

        all_records = []
        order_results = []   # things classified as order confirmations

        for i, msg in enumerate(messages, 1):
            full = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = {h['name']: h['value'] for h in full['payload'].get('headers', [])}
            subject = headers.get('Subject', '')
            sender = headers.get('From', '')
            date_str = headers.get('Date', '')

            body = _extract_body(full['payload'])
            parsed = _parse_order_with_claude(client, body, subject, sender, date_str)

            record = {
                'index': i,
                'email_id': msg['id'],
                'subject': subject,
                'sender': sender,
                'date': date_str,
                'body_chars': len(body),
                'body_preview': body[:800],
                'parsed': parsed,
            }
            all_records.append(record)

            # Compact stdout summary
            short_subj = (subject or '(no subject)')[:70]
            short_from = (sender or '')[:40]
            if parsed and parsed.get('is_order_confirmation'):
                items = parsed.get('items') or []
                item_summary = '; '.join(
                    f'{(it.get("name") or "?")[:25]}×{it.get("quantity", 1)}@${it.get("price", 0)}'
                    for it in items
                ) or '(no items)'
                print(f'[{i:>2}] ✓ {short_subj}')
                print(f'      from={short_from}')
                print(f'      brand={parsed.get("brand")!r}  #{parsed.get("order_number")}  total=${parsed.get("order_total")}')
                print(f'      items=[{item_summary}]')
                parsed_with_meta = dict(parsed)
                parsed_with_meta['email_id'] = msg['id']
                parsed_with_meta['email_subject'] = subject
                order_results.append(parsed_with_meta)
            elif parsed:
                print(f'[{i:>2}] ✗ NOT-ORDER  {short_subj}  (from {short_from})')
            else:
                print(f'[{i:>2}] ! PARSE-FAILED  {short_subj}')

        # ── Cross-email dedup ──────────────────────────────────────────────
        deduped, merged_count = _dedupe_orders_within_scan(order_results)
        print(f'\n══ Cross-email dedup ══')
        print(f'{len(order_results)} order-confirmation emails → {len(deduped)} unique orders ({merged_count} merged away)')
        for o in deduped:
            also = o.get('also_email_ids') or []
            tag = f'  (+{len(also)} related: {also})' if also else ''
            print(f'  • {o.get("brand")} #{o.get("order_number") or "—"} on {o.get("order_date") or "—"}: kept email {o["email_id"]}{tag}')

        # ── Within-order line duplicate detection ──────────────────────────
        print(f'\n══ Within-order line duplicates ══')
        any_dups = False
        for o in deduped:
            items = o.get('items') or []
            seen = {}
            for it in items:
                key = (
                    (it.get('name') or '').strip().lower(),
                    round(float(it.get('price') or 0), 2),
                )
                seen.setdefault(key, []).append(it)
            for key, group in seen.items():
                if len(group) > 1:
                    any_dups = True
                    print(f'  • {o.get("brand")} #{o.get("order_number")}  email={o["email_id"]}')
                    print(f'      duplicate line: name={key[0]!r} price=${key[1]} appears {len(group)}× (each with quantity={[g.get("quantity",1) for g in group]})')
        if not any_dups:
            print('  (none — Claude collapsed identical lines correctly for all parsed orders)')

        # ── Persist full dump ──────────────────────────────────────────────
        out_path = Path(args.output)
        out_path.write_text(json.dumps({
            'unhooked_user': user.email,
            'gmail_mailbox': user.gmail_connected_email,
            'days': args.days,
            'all_records': all_records,
            'deduped_orders': deduped,
            'merged_email_count': merged_count,
        }, indent=2, default=str))
        print(f'\nFull dump written to {out_path}')
        print('That file contains every email body — keep it private and outside the repo.')


if __name__ == '__main__':
    main()
