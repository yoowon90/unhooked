from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
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

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'brand': self.brand,
            'category': self.category,
            'price': self.price,
            'purchase_date': self.purchase_date.isoformat() if self.purchase_date is not None else None,
            # Convert datetime to ISO format string
            'unhooked_date': self.unhooked_date.isoformat() if self.unhooked_date is not None else None

        }

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))
    zipcode = db.Column(db.String(5))
    notes = db.relationship('Note')
    wishitems = db.relationship('WishItem')
    last_purchase_date = db.Column(db.DateTime(timezone=True), default=None)
    # report_start = db.Column(db.DateTime(timezone=True), default=get_default_report_start())
    # report_end = db.Column(db.DateTime(timezone=True), default=datetime.datetime.now())
