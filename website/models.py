from . import db
from flask_login import UserMixin
import datetime
from pytz import timezone


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime(timezone=True), default=datetime.datetime.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # allow associate (relationship) note to user


class WishItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True),default=datetime.datetime.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # referencing another column in the db. one to many relationship.
    category = db.Column(db.String(10000))  # dress, bag, skirt, jeans, non-denim pants, shoes, accessories, etc.
    brand = db.Column(db.String(10000))
    name = db.Column(db.String(10000))
    price = db.Column(db.Float(1000000.00))
    taxed_price = db.Column(db.Float(1000000.00))
    link = db.Column(db.String(10000))
    heightened_interest = db.Column(db.String(10000), default=False)
    unhooked = db.Column(db.Boolean, default=False)
    ineligible = db.Column(db.Boolean, default=True)
    purchased = db.Column(db.Boolean, default=False)
    purchase_date = db.Column(db.DateTime(timezone=True), default=None, nullable=True)
    delivery_fee = db.Column(db.Float(100.00), default=0.00, nullable=True)  # adding nullable to avoid migration error
    total_price = db.Column(db.Float(100.00), default=0.00)
    description = db.Column(db.String(10000), default="")  # free note to store promo code, sale, etc
    wish_period = db.Column(db.Interval)
    tag = db.Column(db.String(10000), nullable=True)
    favorited = db.Column(db.Boolean, default=False)
    unhooked_date = db.Column(db.DateTime(timezone=True), default=None)
    image_url = db.Column(db.String(10000), nullable=True)
    backfilled = db.Column(db.Boolean, default=False)
    source_email_id = db.Column(db.String(200), nullable=True)

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
    reviewed_at = db.Column(db.DateTime(timezone=True), default=datetime.datetime.now)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'source_email_id', name='uq_backfill_review_user_email'),
    )


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))
    zipcode = db.Column(db.String(5))
    notes = db.relationship('Note')
    wishitems = db.relationship('WishItem')
    last_purchase_date = db.Column(db.DateTime(timezone=True), default=None)
    gmail_access_token = db.Column(db.Text, nullable=True)
    gmail_refresh_token = db.Column(db.Text, nullable=True)
    gmail_token_expiry = db.Column(db.DateTime(timezone=True), nullable=True)
    gmail_connected_email = db.Column(db.String(150), nullable=True)
