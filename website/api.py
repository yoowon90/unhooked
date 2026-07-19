import datetime
from typing import cast

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, WishItem, normalize_category, clean_text
from . import db
from . import ledger
from . import transfers
from .ledger import LedgerError
from .purchases import (mark_purchased, needs_savings_prompt,
                        record_savings_decision, savings_feature_enabled)
from .url_extraction import ItemDetails, scrape_item
from .statements import AccountKind, LedgerStatement, StatementError, build_statement
from .tax import taxed_price

api = Blueprint('api', __name__)


def _current_user():
    return User.query.get(int(get_jwt_identity()))


def _get_item(item_id):
    """Return WishItem if it belongs to the current user, else a 404 response tuple."""
    user = _current_user()
    item = WishItem.query.get(item_id)
    if not item or item.user_id != user.id:
        return None, (jsonify({'error': 'Item not found'}), 404)
    return item, None


def _calc_tax(zipcode, price):
    return taxed_price(zipcode, price)


# ── Auth ──────────────────────────────────────────────────────────────────────

@api.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    user = User.query.filter_by(email=data.get('email', '').strip()).first()
    if not user or not check_password_hash(user.password, data.get('password', '')):
        return jsonify({'error': 'Invalid email or password'}), 401
    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': _user_dict(user)})


@api.route('/auth/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    first_name = data.get('first_name', '').strip()
    password = data.get('password', '')
    zipcode = data.get('zipcode', '').strip()

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 409
    if len(email) < 4:
        return jsonify({'error': 'Email must be at least 4 characters'}), 400
    if len(first_name) < 2:
        return jsonify({'error': 'First name must be at least 2 characters'}), 400
    if len(password) < 7:
        return jsonify({'error': 'Password must be at least 7 characters'}), 400
    if len(zipcode) != 5:
        return jsonify({'error': 'Zipcode must be 5 digits'}), 400

    user = User(
        email=email,
        first_name=first_name,
        password=generate_password_hash(password, method='pbkdf2:sha256'),
        zipcode=zipcode,
    )
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify({'token': token, 'user': _user_dict(user)}), 201


@api.route('/auth/me', methods=['GET'])
@jwt_required()
def me():
    return jsonify(_user_dict(_current_user()))


def _user_dict(user):
    return {
        'id': user.id,
        'email': user.email,
        'first_name': user.first_name,
        'zipcode': user.zipcode,
        'last_purchase_date': user.last_purchase_date.isoformat() if user.last_purchase_date else None,
    }


# ── WishItems ─────────────────────────────────────────────────────────────────

@api.route('/wishitems', methods=['GET'])
@jwt_required()
def list_wishitems():
    user = _current_user()
    status = request.args.get('status')
    category = request.args.get('category')
    brand = request.args.get('brand')

    q = WishItem.query.filter_by(user_id=user.id)
    if status == 'wishlist':
        q = q.filter_by(unhooked=False, purchased=False)
    elif status == 'purchased':
        q = q.filter_by(purchased=True, unhooked=False)
    elif status == 'unhooked':
        q = q.filter_by(unhooked=True, purchased=False)
    if category:
        q = q.filter_by(category=category)
    if brand:
        q = q.filter_by(brand=brand)

    return jsonify([i.to_dict() for i in q.order_by(WishItem.date.desc()).all()])


@api.route('/wishitems', methods=['POST'])
@jwt_required()
def create_wishitem():
    user = _current_user()
    data = request.get_json() or {}

    name = clean_text(data.get('name', ''))
    brand = clean_text(data.get('brand', ''))
    category = normalize_category(data.get('category'))
    link = data.get('link', '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not brand:
        return jsonify({'error': 'Brand is required'}), 400
    if not category:
        return jsonify({'error': 'Category is required'}), 400
    if len(link) < 5:
        return jsonify({'error': 'Invalid link'}), 400

    try:
        price = float(data.get('price', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Price must be a number'}), 400
    if price < 0:
        return jsonify({'error': 'Price cannot be negative'}), 400

    try:
        delivery_fee = float(data.get('delivery_fee') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Delivery fee must be a number'}), 400
    if delivery_fee < 0:
        return jsonify({'error': 'Delivery fee cannot be negative'}), 400

    tag = clean_text(data.get('tag'))
    description = clean_text(data.get('description', ''))
    image_url = data.get('image_url')

    taxed_price = _calc_tax(user.zipcode, price)

    if not image_url:
        try:
            image_url = ItemDetails.google_search_image_fallback(brand, name, description, price)
        except Exception:
            pass

    name = ' '.join(word.capitalize() for word in name.split())

    item = WishItem(
        user_id=user.id,
        name=name,
        brand=brand,
        category=category,
        tag=tag,
        link=link,
        description=description,
        image_url=image_url,
        price=price,
        taxed_price=taxed_price,
        delivery_fee=delivery_fee,
        total_price=taxed_price + delivery_fee,
        wish_period=datetime.timedelta(seconds=0),
        date=datetime.datetime.now(),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict()), 201


@api.route('/wishitems/<int:item_id>', methods=['GET'])
@jwt_required()
def get_wishitem(item_id):
    item, err = _get_item(item_id)
    if err:
        return err
    return jsonify(item.to_dict())


@api.route('/wishitems/<int:item_id>', methods=['PATCH'])
@jwt_required()
def update_wishitem(item_id):
    item, err = _get_item(item_id)
    if err:
        return err

    data = request.get_json() or {}

    for field in ('name', 'brand', 'category', 'tag', 'description', 'link', 'image_url'):
        if field in data:
            raw = data[field]
            if field == 'category':
                value = normalize_category(raw)
            elif field in ('name', 'brand', 'tag', 'description'):
                value = clean_text(raw)
            else:
                value = raw
            setattr(item, field, value)

    if 'price' in data:
        try:
            new_price = float(data['price'])
            if new_price < 0:
                return jsonify({'error': 'Price cannot be negative'}), 400
            user = _current_user()
            item.price = new_price
            item.taxed_price = _calc_tax(user.zipcode, new_price)
            item.total_price = item.taxed_price + (item.delivery_fee or 0)
        except (TypeError, ValueError):
            return jsonify({'error': 'Price must be a number'}), 400

    if 'delivery_fee' in data:
        try:
            item.delivery_fee = float(data['delivery_fee'])
            item.total_price = item.taxed_price + item.delivery_fee
        except (TypeError, ValueError):
            return jsonify({'error': 'Delivery fee must be a number'}), 400

    db.session.commit()
    return jsonify(item.to_dict())


@api.route('/wishitems/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_wishitem(item_id):
    item, err = _get_item(item_id)
    if err:
        return err
    db.session.delete(item)
    db.session.commit()
    return jsonify({})


@api.route('/wishitems/<int:item_id>/status', methods=['POST'])
@jwt_required()
def set_status(item_id):
    item, err = _get_item(item_id)
    if err:
        return err

    status = (request.get_json() or {}).get('status')
    if status not in ('wishlist', 'purchased', 'unhooked'):
        return jsonify({'error': 'status must be wishlist, purchased, or unhooked'}), 400

    if status == 'wishlist':
        item.unhooked = False
        item.purchased = False
    elif status == 'purchased':
        # Shared service (same path as the web toggle) stamps purchase_date,
        # wish_period, and last_purchase_date.
        mark_purchased(item, _current_user())
        body = item.to_dict()
        # Hint for the mobile client to show its savings interstitial.
        body['savings_prompt'] = needs_savings_prompt(item)
        return jsonify(body)
    elif status == 'unhooked':
        item.unhooked = True
        item.purchased = False
        item.unhooked_date = datetime.datetime.now()
        if item.date:
            item.wish_period = datetime.datetime.now() - item.date

    db.session.commit()
    return jsonify(item.to_dict())


@api.route('/wishitems/<int:item_id>/savings-decision', methods=['POST'])
@jwt_required()
def savings_decision(item_id):
    """Record the post-purchase savings choice.

    Body: {"decision": "moved"|"declined", "amount": 79.99}
    `amount` (dollars, > 0) is required when decision is "moved"; it is the
    user-edited value from the interstitial, not necessarily the item price.
    """
    if not savings_feature_enabled():
        return jsonify({'error': 'Not available in this environment'}), 404
    item, err = _get_item(item_id)
    if err:
        return err

    data = request.get_json() or {}
    decision = data.get('decision')
    if decision not in ('moved', 'declined'):
        return jsonify({'error': 'decision must be moved or declined'}), 400

    amount_cents = None
    if decision == 'moved':
        try:
            amount_cents = ledger.dollars_to_cents(data.get('amount'))
        except LedgerError:
            return jsonify({'error': 'amount must be a number'}), 400
        if amount_cents <= 0:
            return jsonify({'error': 'amount must be greater than 0'}), 400

    user = _current_user()
    try:
        record_savings_decision(item, user, decision, amount_cents=amount_cents)
    except LedgerError as e:
        return jsonify({'error': str(e)}), 409

    body = item.to_dict()
    if item.savings_txn is not None:
        # Originate the real (sandbox) ACH debit; rail failure never undoes
        # the ledger posting.
        body['transfer'] = transfers.originate_savings_transfer(user, item.savings_txn)
        body['savings_txn'] = item.savings_txn.to_dict()
    return jsonify(body)


@api.route('/wishitems/<int:item_id>/favorite', methods=['POST'])
@jwt_required()
def toggle_favorite(item_id):
    item, err = _get_item(item_id)
    if err:
        return err
    item.favorited = not item.favorited
    db.session.commit()
    return jsonify(item.to_dict())


@api.route('/wishitems/<int:item_id>/image', methods=['DELETE'])
@jwt_required()
def remove_image(item_id):
    item, err = _get_item(item_id)
    if err:
        return err
    item.image_url = None
    db.session.commit()
    return jsonify({})


@api.route('/ledger/statement', methods=['GET'])
@jwt_required()
def ledger_statement() -> Response | tuple[Response, int]:
    """Return one user's derived ledger statement for a half-open date range."""
    if not savings_feature_enabled():
        return jsonify({'error': 'Not available in this environment'}), 404

    account_name: str = request.args.get('account', '')
    if account_name not in ('checking', 'savings'):
        return jsonify({'error': 'account must be checking or savings'}), 400

    start_raw: str = request.args.get('start_date', '')
    end_raw: str = request.args.get('end_date', '')
    try:
        start: datetime.datetime = datetime.datetime.strptime(start_raw, '%Y-%m-%d')
        end: datetime.datetime = datetime.datetime.strptime(end_raw, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'start_date and end_date required in YYYY-MM-DD format'}), 400

    account_kind: AccountKind = cast(AccountKind, account_name)
    user: User = _current_user()
    try:
        statement: LedgerStatement = build_statement(user.id, account_kind, start, end)
    except StatementError as error:
        return jsonify({'error': str(error)}), 400
    return jsonify(statement.to_dict())


@api.route('/transfers/reconcile', methods=['POST'])
@jwt_required()
def reconcile_transfers():
    """Push (originate ledger transactions still awaiting a rail transfer),
    then pull (drain Plaid's event feed onto ledger statuses)."""
    if not savings_feature_enabled():
        return jsonify({'error': 'Not available in this environment'}), 404
    from . import reconciliation
    try:
        push = transfers.originate_pending_transfers(_current_user())
        summary = reconciliation.reconcile_transfers()
        summary['origination'] = push
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 502


# ── URL Extraction ────────────────────────────────────────────────────────────

@api.route('/extract', methods=['POST'])
@jwt_required()
def extract_url():
    url = (request.get_json() or {}).get('url')
    if not url:
        return jsonify({'error': 'url is required'}), 400

    try:
        data = scrape_item(url)
        data['success'] = True
        return jsonify(data)
    except Exception as e:
        print(f"URL extraction error: {e}")
        return jsonify({'success': False, 'name': None, 'price': None, 'brand': None,
                        'description': None, 'currency': None, 'image_url': None})


# ── Reports ───────────────────────────────────────────────────────────────────

@api.route('/reports/summary', methods=['GET'])
@jwt_required()
def reports_summary():
    user = _current_user()

    spenditure = {}
    saves = {}
    for item in user.wishitems:
        if item.purchased and item.purchase_date:
            key = item.purchase_date.date().isoformat()
            spenditure[key] = round(spenditure.get(key, 0) + (item.price or 0), 2)
        if item.unhooked and item.unhooked_date:
            key = item.unhooked_date.date().isoformat()
            saves[key] = round(saves.get(key, 0) + (item.price or 0), 2)

    return jsonify({
        'last_purchase_date': user.last_purchase_date.isoformat() if user.last_purchase_date else None,
        'spenditure': spenditure,
        'saves': saves,
    })


@api.route('/reports/generate', methods=['POST'])
@jwt_required()
def reports_generate():
    user = _current_user()
    data = request.get_json() or {}

    try:
        start = datetime.datetime.strptime(data['start_date'], '%Y-%m-%d')
        # End bound is exclusive of the next day so items dated any time on the
        # end date are included.
        end = datetime.datetime.strptime(data['end_date'], '%Y-%m-%d') + datetime.timedelta(days=1)
    except (KeyError, ValueError):
        return jsonify({'error': 'start_date and end_date required in YYYY-MM-DD format'}), 400

    purchased = [i for i in user.wishitems
                 if i.purchased and i.purchase_date and start <= i.purchase_date < end]
    unhooked = [i for i in user.wishitems
                if i.unhooked and i.unhooked_date and start <= i.unhooked_date < end]
    wishlist = [i for i in user.wishitems
                if not i.purchased and not i.unhooked and i.date and start <= i.date < end]

    def count_by(items, field):
        counts = {}
        for item in items:
            key = getattr(item, field) or 'Unknown'
            counts[key] = counts.get(key, 0) + 1
        return [{'label': k, 'count': v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    return jsonify({
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'total_spent': round(sum(i.taxed_price or 0 for i in purchased), 2),
        'total_saved': round(sum(i.price or 0 for i in unhooked), 2),
        'purchased_by_category': count_by(purchased, 'category'),
        'purchased_by_brand': count_by(purchased, 'brand'),
        'unhooked_by_category': count_by(unhooked, 'category'),
        'unhooked_by_brand': count_by(unhooked, 'brand'),
        'wishlist_by_category': count_by(wishlist, 'category'),
        'wishlist_by_brand': count_by(wishlist, 'brand'),
    })
