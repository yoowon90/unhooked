"""Shared purchase flow — single home for what "mark as purchased" means.

Both entry points (web /toggle-wishitem in views.py and the mobile API
POST /wishitems/:id/status in api.py) call mark_purchased() so the two paths
can't drift, and both record the post-purchase savings decision through
record_savings_decision().
"""
import datetime

from flask import current_app

from . import db
from . import ledger
from .ledger import LedgerError

SAVINGS_DECISIONS = ('moved', 'declined')


def savings_feature_enabled():
    """Config-gated: True in dev, False in prod (dev-only feature for now).
    Defaults True so bare test apps that never load a config get the feature."""
    return bool(current_app.config.get('SAVINGS_FEATURE_ENABLED', True))


def mark_purchased(item, user):
    """Flip a WishItem to purchased. Stamps purchase_date, computes
    wish_period, and updates the user's last_purchase_date. Commits."""
    item.purchased = True
    item.unhooked = False
    item.purchase_date = datetime.datetime.now()
    if item.date:
        item.wish_period = item.purchase_date - item.date
    user.last_purchase_date = item.purchase_date
    db.session.commit()
    return item


def needs_savings_prompt(item):
    """The interstitial shows only for purchased items with no decision yet —
    and only where the savings feature is enabled at all."""
    if not savings_feature_enabled():
        return False
    return bool(item.purchased and not item.unhooked and item.savings_decision is None)


def record_savings_decision(item, user, decision, amount_cents=None):
    """Record the interstitial outcome on the item.

    'moved'    -> posts a pending checking -> savings ledger transaction for
                  amount_cents (must be a positive int) and links it.
    'declined' -> just records the choice.

    A decision is recorded once — re-deciding would double-post the transfer.
    Raises LedgerError on any violation; commits on success.
    """
    if not savings_feature_enabled():
        raise LedgerError('The savings feature is not enabled in this environment')
    if decision not in SAVINGS_DECISIONS:
        raise LedgerError(f"decision must be one of {SAVINGS_DECISIONS}, got {decision!r}")
    if not item.purchased or item.unhooked:
        raise LedgerError('Savings decision only applies to purchased items')
    if item.savings_decision is not None:
        raise LedgerError('A savings decision was already recorded for this item')

    if decision == 'moved':
        txn = ledger.transfer_to_savings(
            user.id,
            amount_cents,
            wishitem_id=item.id,
            memo=f'Savings match for "{item.name}"',
        )
        item.savings_decision = 'moved'
        item.savings_txn_id = txn.id
    else:
        item.savings_decision = 'declined'
    db.session.commit()
    return item
