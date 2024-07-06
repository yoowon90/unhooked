from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # allow associate (relationship) note to user

class WishItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # referencing another column in the db. one to many relationship.
    category = db.Column(db.String(10000))  # dress, bag, skirt, jeans, non-denim pants, shoes, accessories, etc.
    brand = db.Column(db.String(10000))
    name = db.Column(db.String(10000))
    price = db.Column(db.String(10000))
    link = db.Column(db.String(10000))
    heightened_interest = db.Column(db.String(10000), default=False)
    unhooked = db.Column(db.Boolean, default=False)
    # ineligible = db.Column(db.Boolean, default=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))
    notes = db.relationship('Note')
    wishitems = db.relationship('WishItem')


