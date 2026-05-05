import base64
import datetime
import json
import os
from difflib import SequenceMatcher

import anthropic
from bs4 import BeautifulSoup
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import db, limiter
from .models import BackfillReview, WishItem
from .security import same_origin_required
from .tax import taxed_price

backfill = Blueprint('backfill', __name__)

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

ORDER_QUERY = (
    'subject:("order confirmation" OR "order placed" OR "order received" OR '
    '"thank you for your order" OR "order shipped" OR "purchase confirmation" OR '
    '"your order" OR "order summary")'
)

ALLOWED_DAYS = {30, 60, 90}
DUP_NAME_THRESHOLD = 0.85
DUP_BRAND_THRESHOLD = 0.85
DUP_PRICE_TOLERANCE = 0.10  # 10%
DUP_DATE_WINDOW_DAYS = 7


def _get_gmail_service():
    """Build Gmail API service, refreshing the access token if expired."""
    creds = Credentials(
        token=current_user.gmail_access_token,
        refresh_token=current_user.gmail_refresh_token,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        scopes=GMAIL_SCOPES,
        expiry=current_user.gmail_token_expiry,
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
        if not data:
            return ''
        html = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        # Strip tags to keep the prompt small and focused on visible text
        try:
            return BeautifulSoup(html, 'html.parser').get_text(separator=' ', strip=True)
        except Exception:
            return html
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/plain':
                result = _extract_body(part)
                if result:
                    return result
        for part in payload['parts']:
            result = _extract_body(part)
            if result:
                return result
    return ''


def _parse_order_with_claude(client, body, subject, sender, date_str):
    """Call Claude Haiku to parse an email into structured order data."""
    prompt = f"""You are extracting structured purchase data from a shopping email so it can be added to the user's purchase history.

Multiple emails for the same order (confirmation, shipped, delivered, forwarded) are common — extract data from ALL of them. Downstream code will dedupe related emails by order number and item fingerprint.

Subject: {subject}
From: {sender}
Date: {date_str}
Body (first 8000 chars):
{body[:8000]}

Return ONLY valid JSON — no explanation, no markdown. Use null for unknown fields.

Schema:
{{
  "is_order_confirmation": true,
  "brand": "store or brand name (use the retailer/storefront name, not the email sender domain)",
  "order_number": "order or receipt number, or null",
  "order_date": "YYYY-MM-DD or null",
  "items": [
    {{
      "name": "item name (strip ™/®/©, no truncation, no marketing copy)",
      "price": 0.00,
      "quantity": 1,
      "category": "one of: tops, bottoms, dress, outerwear, shoes, bag, accessories, beauty, home, other"
    }}
  ],
  "order_total": 0.00
}}

Rules for `items`:
- `quantity` MUST come from an explicit label in the email — \"Quantity: N\", \"Qty: N\", \"x N\", or similar. Default to 1 if no explicit label is present.
- DO NOT infer quantity from line repetition. Many emails show the same item twice (item list + receipt recap section); those are the SAME line, not two purchases. Return ONE entry with the labeled quantity.
- Exclude items with price = $0 UNLESS the entire order total is $0. These are promotional samples, gift-with-purchase, or freebies — not purchases worth tracking.
- Ignore "you might also like" / recommendation / cross-sell sections, even if they show prices.
- Ignore shipping, tax, discount, and gift-card line items.
- Do not invent items. If the email lists a single item, return a single entry.

Rules for `is_order_confirmation` (informational — used for dedup tiebreaking, NOT for gating):
- TRUE if this email is the original purchase confirmation
- FALSE if it is a shipping update, delivery update, cancellation, refund, status email, or any post-confirmation message
- Always extract whatever data you can regardless of this value. Shipping/delivery emails that include the full receipt should still have `items` populated.

If you cannot find any items, brand, or order number — and the email is clearly something unrelated to a purchase (account email, marketing, password reset) — return just {{"is_order_confirmation": false, "brand": null, "items": []}}."""

    try:
        message = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            messages=[{'role': 'user', 'content': prompt}],
        )
    except Exception as exc:
        current_app.logger.warning(f'Claude parse failed: {exc}')
        return None

    text = message.content[0].text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize(s):
    return ''.join(c.lower() for c in (s or '') if c.isalnum())


def _similar(a, b, threshold):
    a_norm = _normalize(a)
    b_norm = _normalize(b)
    if not a_norm or not b_norm:
        return False
    return SequenceMatcher(None, a_norm, b_norm).ratio() >= threshold


def _price_close(a, b):
    a = float(a or 0)
    b = float(b or 0)
    if a == 0 and b == 0:
        return True
    if a == 0 or b == 0:
        return False
    return abs(a - b) / max(a, b) <= DUP_PRICE_TOLERANCE


def _existing_purchases_window(order_date_str, brand):
    """Return purchased items for current_user that could plausibly be duplicates of this order."""
    if not order_date_str:
        # No date — search all purchased items for the user
        return WishItem.query.filter_by(user_id=current_user.id, purchased=True).all()
    try:
        order_date = datetime.datetime.strptime(order_date_str, '%Y-%m-%d')
    except ValueError:
        return WishItem.query.filter_by(user_id=current_user.id, purchased=True).all()
    start = order_date - datetime.timedelta(days=DUP_DATE_WINDOW_DAYS)
    end = order_date + datetime.timedelta(days=DUP_DATE_WINDOW_DAYS)
    return (WishItem.query
            .filter_by(user_id=current_user.id, purchased=True)
            .filter(WishItem.purchase_date.between(start, end))
            .all())


def _find_duplicate_item(item, brand, candidates):
    """Return the existing WishItem that fuzzy-matches the given item, or None."""
    name = item.get('name') or ''
    price = float(item.get('price') or 0)
    for existing in candidates:
        if not _similar(brand, existing.brand or '', DUP_BRAND_THRESHOLD):
            continue
        if not _similar(name, existing.name or '', DUP_NAME_THRESHOLD):
            continue
        if not _price_close(price, existing.price or 0):
            continue
        return existing
    return None


def _item_fingerprint(items):
    """Sorted tuple of (normalized_name, rounded_price) — stable across emails
    that show the same items in different order or formatting."""
    return tuple(sorted(
        (_normalize(it.get('name')), round(float(it.get('price') or 0), 2))
        for it in (items or [])
        if it.get('name')
    ))


def _order_grouping_key(order):
    """Return a tuple identifying the underlying purchase across related emails.

    Three keys, in priority order:
      1. (brand, order_number) — most reliable
      2. (brand, item_fingerprint) — handles cases where order_number is
         missing or differs in formatting between emails
      3. (brand, rounded_total, date) — last-resort fallback when neither
         order_number nor item names are extractable
    """
    brand = _normalize(order.get('brand'))
    order_number = (order.get('order_number') or '').strip()
    if order_number:
        return ('num', brand, order_number)
    fingerprint = _item_fingerprint(order.get('items'))
    if fingerprint:
        return ('fp', brand, fingerprint)
    total = round(float(order.get('order_total') or 0), 2)
    date = order.get('order_date') or ''
    return ('total', brand, total, date)


def _is_better_kept(candidate, current_kept):
    """When two emails group to the same key, decide which to surface as the
    primary card. Prefer: more items > is_order_confirmation=true > more body."""
    cand_items = len(candidate.get('items') or [])
    kept_items = len(current_kept.get('items') or [])
    if cand_items != kept_items:
        return cand_items > kept_items
    # Tiebreak: prefer the email Claude classified as the original confirmation
    cand_is_conf = bool(candidate.get('is_order_confirmation'))
    kept_is_conf = bool(current_kept.get('is_order_confirmation'))
    if cand_is_conf != kept_is_conf:
        return cand_is_conf
    return False


def _dedupe_orders_within_scan(orders):
    """Collapse related emails (e.g. order + shipping + delivery for the same
    purchase) into a single review card. Keeps the highest-quality email and
    stitches the dropped emails' IDs onto `also_email_ids` so the confirm step
    can record reviews for all of them."""
    groups = {}
    for order in orders:
        order.setdefault('also_email_ids', [])
        key = _order_grouping_key(order)
        if key not in groups:
            groups[key] = order
            continue
        kept = groups[key]
        if _is_better_kept(order, kept):
            # Promote `order`; demote `kept` into also_email_ids
            order['also_email_ids'] = (kept.get('also_email_ids') or []) + [kept.get('email_id')]
            order['also_email_ids'] = [eid for eid in order['also_email_ids'] if eid]
            groups[key] = order
        else:
            kept['also_email_ids'].append(order.get('email_id'))
            kept['also_email_ids'] = [eid for eid in kept['also_email_ids'] if eid]

    deduped = list(groups.values())
    merged_count = sum(len(o.get('also_email_ids') or []) for o in deduped)
    return deduped, merged_count


def _filter_already_purchased(orders):
    """Drop orders whose every item already exists in the user's purchase list,
    and record BackfillReview rows so those emails never reappear.

    Returns (kept_orders, auto_skipped_count)."""
    if not orders:
        return orders, 0

    existing_review_ids = {
        row[0] for row in db.session.query(BackfillReview.source_email_id)
        .filter_by(user_id=current_user.id)
        .all()
    }

    kept = []
    auto_skipped = 0
    for order in orders:
        items = order.get('items') or []
        if not items:
            kept.append(order)
            continue
        brand = order.get('brand') or ''
        candidates = _existing_purchases_window(order.get('order_date'), brand)
        all_match = all(_find_duplicate_item(item, brand, candidates) for item in items)
        if not all_match:
            kept.append(order)
            continue

        # Every item already exists — auto-skip the whole order
        auto_skipped += 1
        for email_id in [order.get('email_id')] + (order.get('also_email_ids') or []):
            if not email_id or email_id in existing_review_ids:
                continue
            db.session.add(BackfillReview(
                user_id=current_user.id,
                source_email_id=email_id,
                decision='auto_skipped',
            ))
            existing_review_ids.add(email_id)

    if auto_skipped:
        db.session.commit()
    return kept, auto_skipped


@backfill.route('/backfill')
@login_required
def backfill_page():
    if not current_user.gmail_connected_email:
        flash('Connect Gmail first to backfill orders from your inbox.', 'error')
        return redirect(url_for('connectors.settings'))
    return render_template('backfill.html', user=current_user)


@backfill.route('/backfill/scan', methods=['POST'])
@login_required
@same_origin_required
@limiter.limit('5 per day')
def scan_emails():
    if not current_user.gmail_access_token:
        return jsonify({'error': 'Gmail not connected'}), 401

    days = (request.json or {}).get('days', 30)
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 30
    if days not in ALLOWED_DAYS:
        days = 30

    try:
        service = _get_gmail_service()
    except Exception as exc:
        current_app.logger.warning(f'Gmail auth failed: {exc}')
        return jsonify({'error': 'Gmail authentication failed — try reconnecting.'}), 401

    # Skip emails already imported (approved + confirmed) AND emails already
    # reviewed in any prior session (approved or denied) — denial persistence
    # is what stops the same emails from reappearing across scans.
    already_imported = {
        row[0] for row in db.session.query(WishItem.source_email_id)
        .filter_by(user_id=current_user.id)
        .filter(WishItem.source_email_id.isnot(None))
        .all()
    }
    already_reviewed = {
        row[0] for row in db.session.query(BackfillReview.source_email_id)
        .filter_by(user_id=current_user.id)
        .all()
    }
    already_seen = already_imported | already_reviewed

    query = f'{ORDER_QUERY} newer_than:{days}d'
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=60).execute()
    except HttpError as exc:
        current_app.logger.warning(f'Gmail list failed: {exc}')
        return jsonify({'error': 'Gmail API request failed.'}), 502
    messages = results.get('messages', [])

    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    orders = []
    for msg in messages:
        if msg['id'] in already_seen:
            continue
        try:
            full = service.users().messages().get(
                userId='me', id=msg['id'], format='full'
            ).execute()
        except HttpError as exc:
            current_app.logger.warning(f'Gmail fetch failed for {msg["id"]}: {exc}')
            continue

        headers = {h['name']: h['value'] for h in full['payload'].get('headers', [])}
        subject = headers.get('Subject', '')
        sender = headers.get('From', '')
        date_str = headers.get('Date', '')

        body = _extract_body(full['payload'])
        parsed = _parse_order_with_claude(client, body, subject, sender, date_str)

        if not parsed:
            continue

        # Drop the "is_order_confirmation" gate. Include any email with real
        # purchase signal (items, order_number, or order_total). Downstream
        # dedup will collapse related emails for the same purchase.
        items = parsed.get('items') or []
        has_priced_items = any((it.get('price') or 0) > 0 for it in items)
        has_signal = bool(parsed.get('order_number')) or has_priced_items or bool(parsed.get('order_total'))
        if not has_signal:
            continue

        parsed['email_id'] = msg['id']
        parsed['email_subject'] = subject
        parsed['email_sender'] = sender

        if not items:
            parsed['items'] = [{
                'name': parsed.get('brand') or 'Unknown item',
                'price': parsed.get('order_total') or 0.0,
                'quantity': 1,
                'category': 'other',
            }]

        # Layer 2 dedup hint: flag possible duplicates against existing purchases
        brand = parsed.get('brand') or ''
        candidates = _existing_purchases_window(parsed.get('order_date'), brand)
        dup_count = 0
        for item in parsed['items']:
            if _find_duplicate_item(item, brand, candidates):
                item['_possible_duplicate'] = True
                dup_count += 1
        parsed['possible_duplicate'] = dup_count > 0
        parsed['duplicate_item_count'] = dup_count

        orders.append(parsed)

    deduped, merged_count = _dedupe_orders_within_scan(orders)
    kept, auto_skipped_count = _filter_already_purchased(deduped)
    return jsonify({
        'orders': kept,
        'merged_email_count': merged_count,
        'auto_skipped_count': auto_skipped_count,
    })


@backfill.route('/backfill/confirm', methods=['POST'])
@login_required
@same_origin_required
def confirm_backfill():
    payload = request.json or {}
    approved_orders = payload.get('approved', [])
    denied_orders = payload.get('denied', [])

    added = 0
    skipped_orders = 0
    skipped_items = 0

    # Existing review rows for this user — used to keep this endpoint idempotent
    # under double-submit (the unique constraint enforces it at the DB level too).
    existing_reviews = {
        row[0] for row in db.session.query(BackfillReview.source_email_id)
        .filter_by(user_id=current_user.id)
        .all()
    }

    def record_review(email_id, decision):
        if not email_id or email_id in existing_reviews:
            return
        db.session.add(BackfillReview(
            user_id=current_user.id,
            source_email_id=email_id,
            decision=decision,
        ))
        existing_reviews.add(email_id)

    for order in approved_orders:
        email_id = order.get('email_id')

        # Layer 1: skip whole order if this email was already imported
        if email_id:
            already = (WishItem.query
                       .filter_by(user_id=current_user.id, source_email_id=email_id)
                       .first())
            if already:
                skipped_orders += 1
                record_review(email_id, 'approved')
                continue

        purchase_date = None
        if order.get('order_date'):
            try:
                purchase_date = datetime.datetime.strptime(order['order_date'], '%Y-%m-%d')
            except ValueError:
                pass
        purchase_date = purchase_date or datetime.datetime.now()

        brand = order.get('brand') or ''
        candidates = _existing_purchases_window(order.get('order_date'), brand)

        for item in order.get('items', []):
            # Layer 2: skip individual item if it fuzzy-matches an existing purchase
            if _find_duplicate_item(item, brand, candidates):
                skipped_items += 1
                continue

            raw_price = float(item.get('price') or 0.0)
            taxed = taxed_price(current_user.zipcode or '', raw_price)
            try:
                quantity = max(1, int(item.get('quantity') or 1))
            except (TypeError, ValueError):
                quantity = 1

            for _ in range(quantity):
                wish_item = WishItem(
                    user_id=current_user.id,
                    name=item.get('name') or 'Unknown item',
                    brand=brand,
                    category=item.get('category') or 'other',
                    price=raw_price,
                    taxed_price=taxed,
                    delivery_fee=0.0,
                    total_price=taxed,
                    purchased=True,
                    purchase_date=purchase_date,
                    wish_period=datetime.timedelta(0),
                    backfilled=True,
                    source_email_id=email_id,
                    description=f"Backfilled from: {order.get('email_subject', '')}",
                )
                db.session.add(wish_item)
                added += 1

        record_review(email_id, 'approved')
        # Mark related emails (shipping/delivery for the same order) as reviewed
        # so they won't reappear in the next scan.
        for related_email_id in order.get('also_email_ids') or []:
            record_review(related_email_id, 'approved')

    for order in denied_orders:
        record_review(order.get('email_id'), 'denied')
        for related_email_id in order.get('also_email_ids') or []:
            record_review(related_email_id, 'denied')

    db.session.commit()
    return jsonify({
        'added': added,
        'skipped_orders': skipped_orders,
        'skipped_items': skipped_items,
        'denied_recorded': len(denied_orders),
    })
