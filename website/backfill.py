import base64
import datetime
import json
import os

import anthropic
from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import db, limiter
from .models import WishItem

backfill = Blueprint('backfill', __name__)

TAX = {'11217': 0.0875, '15206': 0}
NYC = ['10001', '10011', '11019', '10023', '10128',
       '11201', '11211', '11217', '11231', '11238',
       '11101', '11354', '11375', '11432', '11691',
       '10451', '10452', '10463', '10467', '10469',
       '10301', '10304', '10306', '10314']

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

ORDER_QUERY = (
    'subject:("order confirmation" OR "order placed" OR "order received" OR '
    '"thank you for your order" OR "order shipped" OR "purchase confirmation" OR '
    '"your order" OR "order summary")'
)


def _get_gmail_service():
    """Build Gmail API service, refreshing the access token if expired."""
    creds = Credentials(
        token=current_user.gmail_access_token,
        refresh_token=current_user.gmail_refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        scopes=GMAIL_SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        current_user.gmail_access_token = creds.token
        current_user.gmail_token_expiry = creds.expiry
        db.session.commit()
    return build('gmail', 'v1', credentials=creds)


def _extract_body(payload):
    """Recursively extract plain-text (preferred) or HTML body from a Gmail message payload."""
    mime = payload.get('mimeType', '')
    if mime == 'text/plain':
        data = payload.get('body', {}).get('data', '')
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore') if data else ''
    if mime == 'text/html':
        data = payload.get('body', {}).get('data', '')
        return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore') if data else ''
    if 'parts' in payload:
        # Prefer plain text
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                result = _extract_body(part)
                if result:
                    return result
        # Fall back to html or recurse
        for part in payload['parts']:
            result = _extract_body(part)
            if result:
                return result
    return ''


def _parse_order_with_claude(body, subject, sender, date_str):
    """Call Claude Haiku to parse an email into structured order data."""
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    prompt = f"""Parse this email and extract purchase/order details.

Subject: {subject}
From: {sender}
Date: {date_str}
Body (first 3000 chars):
{body[:3000]}

Return ONLY valid JSON — no explanation, no markdown. Use null for unknown fields.
{{
  "is_order_confirmation": true,
  "brand": "store or brand name",
  "order_number": "order number or null",
  "order_date": "YYYY-MM-DD or null",
  "items": [
    {{
      "name": "item name",
      "price": 0.00,
      "category": "one of: tops, bottoms, dress, outerwear, shoes, bag, accessories, beauty, home, other"
    }}
  ],
  "order_total": 0.00
}}

If this is NOT an order confirmation, return {{"is_order_confirmation": false}}.
If items cannot be parsed, return an empty items array with a single item using the brand name as the name."""

    message = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=1024,
        messages=[{'role': 'user', 'content': prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if present
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return None


def _calc_tax(zipcode, price):
    tax_rate = 0 if (zipcode in NYC and price < 110.00) else TAX.get(zipcode, 0)
    return round(price * (1 + tax_rate), 2)


@backfill.route('/backfill')
@login_required
def backfill_page():
    if not current_user.gmail_access_token:
        return redirect(url_for('connectors.settings'))
    return render_template('backfill.html', user=current_user)


@backfill.route('/backfill/scan', methods=['POST'])
@login_required
@limiter.limit('5 per day')
def scan_emails():
    if not current_user.gmail_access_token:
        return jsonify({'error': 'Gmail not connected'}), 401

    days = request.json.get('days', 30)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30

    service = _get_gmail_service()

    already_imported = set(
        item.source_email_id
        for item in WishItem.query.filter_by(user_id=current_user.id)
        .filter(WishItem.source_email_id.isnot(None))
        .all()
    )

    query = f'{ORDER_QUERY} newer_than:{days}d'
    results = service.users().messages().list(userId='me', q=query, maxResults=60).execute()
    messages = results.get('messages', [])

    orders = []
    for msg in messages:
        if msg['id'] in already_imported:
            continue
        try:
            full = service.users().messages().get(
                userId='me', id=msg['id'], format='full'
            ).execute()
        except Exception:
            continue

        headers = {h['name']: h['value'] for h in full['payload'].get('headers', [])}
        subject = headers.get('Subject', '')
        sender = headers.get('From', '')
        date_str = headers.get('Date', '')

        body = _extract_body(full['payload'])
        parsed = _parse_order_with_claude(body, subject, sender, date_str)

        if parsed and parsed.get('is_order_confirmation'):
            parsed['email_id'] = msg['id']
            parsed['email_subject'] = subject
            parsed['email_sender'] = sender
            if not parsed.get('items'):
                parsed['items'] = [{'name': parsed.get('brand', 'Unknown item'), 'price': parsed.get('order_total') or 0.0, 'category': 'other'}]
            orders.append(parsed)

    return jsonify({'orders': orders})


@backfill.route('/backfill/confirm', methods=['POST'])
@login_required
def confirm_backfill():
    approved_orders = request.json.get('approved', [])

    added = 0
    for order in approved_orders:
        purchase_date = None
        if order.get('order_date'):
            try:
                purchase_date = datetime.datetime.strptime(order['order_date'], '%Y-%m-%d')
            except ValueError:
                pass
        purchase_date = purchase_date or datetime.datetime.now()

        for item in order.get('items', []):
            raw_price = float(item.get('price') or 0.0)
            taxed = _calc_tax(current_user.zipcode or '', raw_price)
            wish_item = WishItem(
                user_id=current_user.id,
                name=item.get('name') or 'Unknown item',
                brand=order.get('brand') or '',
                category=item.get('category') or 'other',
                price=raw_price,
                taxed_price=taxed,
                delivery_fee=0.0,
                total_price=taxed,
                purchased=True,
                purchase_date=purchase_date,
                wish_period=datetime.timedelta(0),
                backfilled=True,
                source_email_id=order.get('email_id'),
                description=f"Backfilled from: {order.get('email_subject', '')}",
            )
            db.session.add(wish_item)
            added += 1

    db.session.commit()
    return jsonify({'added': added})
