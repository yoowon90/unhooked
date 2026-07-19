"""Shareable read-only wishlist links.

A user can mint a token that exposes their *wishlist* — the items still under
consideration (not purchased, not unhooked) — at a public URL, so they can
send it to a friend for a second opinion.

A link can carry an expiry (``expires_at``); a link with no expiry never
expires. A link can also be revoked, which stops the URL from resolving
without deleting the row.
"""
import datetime
import random
import string

from .tax import NYC_ZIPCODES, NYC_TAX_RATE, NYC_CLOTHING_EXEMPTION


def generate_token(length=6):
    """Return a token to put in a share URL."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(random.choices(alphabet, k=length))


def link_is_valid(link):
    """True while a share link should still resolve to its wishlist."""
    if link.expires_at is None:
        return False
    return datetime.datetime.now() < link.expires_at


def wishlist_tax_estimate(items, zipcode):
    """Estimated grand total for a wishlist, including estimated sales tax,
    so the share page can show a friend roughly what the list would cost."""
    total = 0.0
    for item in items:
        price = item.price or 0
        if zipcode in NYC_ZIPCODES and price <= NYC_CLOTHING_EXEMPTION:
            rate = 0.0
        elif zipcode in NYC_ZIPCODES:
            rate = NYC_TAX_RATE
        else:
            rate = 0.0
        total += price * (1 + rate)
    return round(total, 2)
