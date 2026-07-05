from . import db
from flask_login import UserMixin
import datetime
import html
from pytz import timezone


def clean_text(s):
    """Decode HTML entities (e.g. '&amp;' -> '&') and strip whitespace.
    Safe to apply to any text field stored in the DB. Some scraping/backfill
    paths leave entities encoded; this brings them back to display form."""
    if s is None:
        return s
    return html.unescape(s).strip()


# Words that should pass through normalize_category unchanged.
# Two flavors:
#   1. Plural-only fashion staples that don't have a sensible singular form.
#   2. Uncountable nouns where a forced plural reads awkwardly.
# Compared lowercased; only the trailing word is checked for multi-word categories.
PROTECTED_CATEGORIES = {
    # plural-only fashion staples
    'pants', 'jeans', 'shorts', 'leggings', 'tights', 'bottoms',
    'glasses', 'sunglasses', 'pajamas', 'pyjamas', 'overalls',
    # uncountable shopping categories
    'beauty', 'outerwear', 'footwear', 'underwear', 'swimwear',
    'sleepwear', 'loungewear', 'activewear', 'athleisure',
    'jewelry', 'makeup', 'skincare', 'haircare', 'fragrance',
    'lingerie',
}


def _pluralize_word(word):
    """Pluralize a word to its canonical plural form. Already-plural words and
    PROTECTED_CATEGORIES pass through unchanged."""
    if not word:
        return word
    lower = word.lower()
    if lower in PROTECTED_CATEGORIES:
        return word

    # Already-plural detection.
    # accessories, batteries
    if lower.endswith('ies'):
        return word
    # dresses, watches, boxes, dishes, buzzes
    if (lower.endswith('sses') or lower.endswith('shes') or lower.endswith('ches')
            or lower.endswith('xes') or lower.endswith('zes')):
        return word
    # tops, rings — bare trailing -s on a stem that isn't a typical singular ending
    if (lower.endswith('s') and not lower.endswith('ss')
            and not lower.endswith('us') and not lower.endswith('is')):
        return word

    # Singular -> pluralize
    # consonant + y -> -ies (Accessory -> Accessories, Berry -> Berries)
    if len(word) > 1 and lower.endswith('y') and word[-2].lower() not in 'aeiou':
        return word[:-1] + ('IES' if word[-1].isupper() else 'ies')
    # sibilant endings -> -es (Dress -> Dresses, Watch -> Watches, Box -> Boxes)
    if (lower.endswith('s') or lower.endswith('x') or lower.endswith('z')
            or lower.endswith('ch') or lower.endswith('sh')):
        return word + ('ES' if word[-1].isupper() else 'es')
    # default -> -s (Top -> Tops, Shoe -> Shoes, Earring -> Earrings)
    return word + ('S' if word[-1].isupper() else 's')


def normalize_category(s):
    """Normalize a category for storage and grouping.
    - All-caps inputs are downcased to title case ('TOPS' -> 'Tops').
    - Otherwise the first character is capitalized; the rest is left as-is
      (so 'iPhone', 'T-shirt' survive).
    - The trailing word is pluralized so casing and singular/plural variants
      converge ('Top'/'tops'/'TOPS' -> 'Tops', 'Accessory' -> 'Accessories').
      PROTECTED_CATEGORIES (Pants, Beauty, Outerwear, ...) pass through.
    Returns None / empty for None / blank input."""
    s = clean_text(s)
    if not s:
        return s
    if s.isupper():
        s = s[0] + s[1:].lower()
    else:
        s = s[0].upper() + s[1:]
    if ' ' in s:
        prefix, last = s.rsplit(' ', 1)
        return prefix + ' ' + _pluralize_word(last)
    return _pluralize_word(s)


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime, default=datetime.datetime.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # allow associate (relationship) note to user


class WishItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime,default=datetime.datetime.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # referencing another column in the db. one to many relationship.
    category = db.Column(db.String(10000))  # dress, bag, skirt, jeans, non-denim pants, shoes, accessories, etc.
    brand = db.Column(db.String(10000))
    name = db.Column(db.String(10000))
    price = db.Column(db.Float)
    taxed_price = db.Column(db.Float)
    link = db.Column(db.String(10000))
    heightened_interest = db.Column(db.String(10000), default=False)
    unhooked = db.Column(db.Boolean, default=False)
    ineligible = db.Column(db.Boolean, default=True)
    purchased = db.Column(db.Boolean, default=False)
    purchase_date = db.Column(db.DateTime, default=None, nullable=True)
    delivery_fee = db.Column(db.Float, default=0.00, nullable=True)  # adding nullable to avoid migration error
    total_price = db.Column(db.Float, default=0.00)
    description = db.Column(db.String(10000), default="")  # free note to store promo code, sale, etc
    wish_period = db.Column(db.Interval)
    tag = db.Column(db.String(10000), nullable=True)
    favorited = db.Column(db.Boolean, default=False)
    unhooked_date = db.Column(db.DateTime, default=None)
    image_url = db.Column(db.String(10000), nullable=True)
    backfilled = db.Column(db.Boolean, default=False)
    source_email_id = db.Column(db.String(200), nullable=True)
    # Savings-match decision, recorded at the post-purchase interstitial:
    #   None       -> never prompted (all purchases predating the feature)
    #   'moved'    -> user moved money to savings (savings_txn_id set)
    #   'declined' -> user chose "Not at this time"
    savings_decision = db.Column(db.String(20), nullable=True)
    # Soft reference (no DB FK): ledger_transaction.wishitem_id already points
    # back at wish_item, and a second real FK would make the two tables
    # circularly dependent (breaks create_all ordering / SQLite alters).
    savings_txn_id = db.Column(db.Integer, nullable=True)
    savings_txn = db.relationship(
        'LedgerTransaction',
        primaryjoin='foreign(WishItem.savings_txn_id) == LedgerTransaction.id',
        viewonly=True,
        uselist=False,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'brand': self.brand,
            'category': self.category,
            'tag': self.tag,
            'description': self.description,
            'link': self.link,
            'image_url': self.image_url,
            'price': self.price,
            'taxed_price': self.taxed_price,
            'delivery_fee': self.delivery_fee,
            'total_price': self.total_price,
            'favorited': self.favorited,
            'unhooked': self.unhooked,
            'purchased': self.purchased,
            'ineligible': self.ineligible,
            'date': self.date.isoformat() if self.date is not None else None,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date is not None else None,
            'unhooked_date': self.unhooked_date.isoformat() if self.unhooked_date is not None else None,
            'wish_period_seconds': int(self.wish_period.total_seconds()) if self.wish_period is not None else None,
            'savings_decision': self.savings_decision,
            'savings_txn_id': self.savings_txn_id,
        }

class BackfillReview(db.Model):
    """Audit row for every Gmail email reviewed in the backfill flow.

    Persisting denials (not just approvals) prevents the same emails from
    reappearing in subsequent scans after the user has already swiped ✕ on them.
    Approvals are also recorded here as defense-in-depth; the WishItem.source_email_id
    filter still applies for the import dedup itself.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    source_email_id = db.Column(db.String(200), nullable=False)
    decision = db.Column(db.String(20), nullable=False)  # 'approved' | 'denied'
    reviewed_at = db.Column(db.DateTime, default=datetime.datetime.now)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'source_email_id', name='uq_backfill_review_user_email'),
    )


# ── Ledger core (double-entry) ────────────────────────────────────────────────
# All ledger amounts are INTEGER CENTS, never floats — floats round differently
# across SQLite (dev) and Postgres (prod) and silently lose pennies; a ledger
# that doesn't balance to the cent is worthless. Convert at the boundary with
# ledger.dollars_to_cents(). The sum-to-zero invariant is enforced in Python
# (ledger.post_transaction), not as a DB constraint — SQLite's constraint
# enforcement is laxer than Postgres, so a DB-only guard would pass on dev
# and only fail in prod.

LEDGER_ACCOUNT_KINDS = ('checking', 'savings')
LEDGER_TXN_STATUSES = ('pending', 'settled', 'failed')


class LedgerAccount(db.Model):
    """A bucket in the internal ledger (NOT a real bank account).

    Each user gets one 'checking' and one 'savings' bucket. Balances are
    always derived by summing this account's entries — there is deliberately
    no balance column (a mutable balance field is the classic lost-update bug).
    `provider_account_id` links the bucket to a real Plaid account in step 4.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)  # one of LEDGER_ACCOUNT_KINDS
    display_name = db.Column(db.String(150), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    provider_account_id = db.Column(db.String(200), nullable=True)  # Plaid account id (step 4)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    entries = db.relationship('LedgerEntry', back_populates='account')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'kind', name='uq_ledger_account_user_kind'),
    )


class LedgerTransaction(db.Model):
    """One money movement, made of >= 2 LedgerEntry rows that sum to zero.

    Lifecycle: pending -> settled | failed. `pending` means our ledger has
    recorded the intent; `settled` means the outside world (Plaid Transfer,
    step 5 reconciliation) confirmed it. `provider_transfer_id` holds the
    Plaid transfer id once a real (sandbox) ACH transfer is originated.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wishitem_id = db.Column(db.Integer, db.ForeignKey('wish_item.id'), nullable=True)
    amount_cents = db.Column(db.Integer, nullable=False)  # sum of the positive legs
    status = db.Column(db.String(20), nullable=False, default='pending')  # one of LEDGER_TXN_STATUSES
    memo = db.Column(db.String(500), default='')
    provider_transfer_id = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    settled_at = db.Column(db.DateTime, nullable=True)
    entries = db.relationship('LedgerEntry', back_populates='transaction')

    def to_dict(self):
        return {
            'id': self.id,
            'wishitem_id': self.wishitem_id,
            'amount_cents': self.amount_cents,
            'status': self.status,
            'memo': self.memo,
            'provider_transfer_id': self.provider_transfer_id,
            'created_at': self.created_at.isoformat() if self.created_at is not None else None,
            'settled_at': self.settled_at.isoformat() if self.settled_at is not None else None,
            'entries': [e.to_dict() for e in self.entries],
        }


class LedgerEntry(db.Model):
    """One signed leg of a transaction. IMMUTABLE once posted — a mistake is
    fixed by posting a reversing transaction, never by editing an entry.
    Negative = money leaves the account, positive = money arrives.
    """
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('ledger_transaction.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('ledger_account.id'), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)  # signed
    created_at = db.Column(db.DateTime, default=datetime.datetime.now)
    transaction = db.relationship('LedgerTransaction', back_populates='entries')
    account = db.relationship('LedgerAccount', back_populates='entries')

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'amount_cents': self.amount_cents,
        }


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))
    zipcode = db.Column(db.String(5))
    notes = db.relationship('Note')
    wishitems = db.relationship('WishItem')
    last_purchase_date = db.Column(db.DateTime, default=None)
    gmail_access_token = db.Column(db.Text, nullable=True)
    gmail_refresh_token = db.Column(db.Text, nullable=True)
    gmail_token_expiry = db.Column(db.DateTime, nullable=True)
    gmail_connected_email = db.Column(db.String(150), nullable=True)
