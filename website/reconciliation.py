"""Reconciliation — syncing what the bank ACTUALLY did back onto the ledger.

The ledger records intent (a pending checking -> savings transaction); Plaid
Transfer reports reality as a monotonically increasing event feed
(/transfer/event/sync). Reconciliation walks that feed from a persisted
cursor (SyncCursor) and converges ledger statuses onto rail reality:

    event               ledger action
    ------------------- --------------------------------------------------
    pending / posted    in-flight; no state change (we model both as 'pending')
    settled             settle_transaction  (pending -> settled)
    failed / cancelled  fail_transaction    (pending -> failed)
    returned            fail if still pending; if ALREADY SETTLED, post a
                        reversal + mark 'returned' (ACH returns can arrive
                        days after settlement — the classic recon edge)

Events whose transfer_id we have no ledger transaction for are counted as
`unmatched` — money moved that we have no record of, exactly the kind of
discrepancy a reconciliation report exists to surface.

The webhook-vs-poll note: in production Plaid pushes a TRANSFER_EVENTS_UPDATE
webhook and the handler just calls reconcile_transfers(). A self-hosted app
on localhost can't receive webhooks, so we poll instead: opportunistically on
purchased-list loads (guarded — only when a pending transfer is in flight)
and on demand from Settings / the API. Same reconciler either way.
"""
from . import db
from . import plaid_client
from .models import LedgerTransaction, SyncCursor
from . import ledger

CURSOR_NAME = 'plaid_transfer_events'

# Event types that end a transfer's life on the rail.
_FAIL_EVENTS = ('failed', 'cancelled')
_INFLIGHT_EVENTS = ('pending', 'posted', 'funds_available')


def _get_cursor():
    cursor = SyncCursor.query.filter_by(name=CURSOR_NAME).first()
    if cursor is None:
        cursor = SyncCursor(name=CURSOR_NAME, last_event_id=0)
        db.session.add(cursor)
        db.session.commit()
    return cursor


def should_sync():
    """Cheap guard for opportunistic syncs: only hit Plaid when a transfer
    we originated is still awaiting a terminal status."""
    if not plaid_client.is_configured():
        return False
    return db.session.query(
        LedgerTransaction.query
        .filter(LedgerTransaction.status == 'pending',
                LedgerTransaction.provider_transfer_id.isnot(None))
        .exists()
    ).scalar()


def reconcile_transfers():
    """Drain the event feed from the cursor and apply every event.

    Returns a summary dict:
      {events, settled, failed, returned, unmatched: [transfer_ids], cursor}
    Safe to call repeatedly — the cursor makes re-runs no-ops.
    """
    cursor = _get_cursor()
    summary = {'events': 0, 'settled': 0, 'failed': 0, 'returned': 0,
               'unmatched': []}

    while True:
        events = plaid_client.sync_transfer_events(after_id=cursor.last_event_id)
        if not events:
            break
        # Plaid documents ascending order; sort defensively — applying a
        # 'settled' before its 'pending' must not corrupt state.
        for event in sorted(events, key=lambda e: e['event_id']):
            _apply_event(event, summary)
            summary['events'] += 1
            cursor.last_event_id = max(cursor.last_event_id, event['event_id'])
        db.session.commit()

    summary['cursor'] = cursor.last_event_id
    return summary


def _apply_event(event, summary):
    event_type = event.get('event_type')
    transfer_id = event.get('transfer_id')
    if not transfer_id or event_type in _INFLIGHT_EVENTS:
        return  # sweep bookkeeping / in-flight noise — nothing to converge

    txn = LedgerTransaction.query.filter_by(provider_transfer_id=transfer_id).first()
    if txn is None:
        # The rail moved money we have no ledger record of. Surfacing this
        # (not silently skipping) is the point of reconciliation.
        if event_type in ('settled',) + _FAIL_EVENTS + ('returned',):
            summary['unmatched'].append(transfer_id)
        return

    if event_type == 'settled':
        if txn.status == 'pending':
            ledger.settle_transaction(txn)
            summary['settled'] += 1
    elif event_type in _FAIL_EVENTS:
        if txn.status == 'pending':
            _annotate_failure(txn, event)
            ledger.fail_transaction(txn)
            summary['failed'] += 1
    elif event_type == 'returned':
        if txn.status == 'pending':
            _annotate_failure(txn, event)
            ledger.fail_transaction(txn)
            summary['failed'] += 1
        elif txn.status == 'settled':
            reason = _failure_reason(event)
            ledger.return_settled_transaction(
                txn, memo=f'ACH return of txn #{txn.id}' + (f' ({reason})' if reason else ''))
            summary['returned'] += 1
    # unknown/new event types: deliberately ignored, cursor still advances


def _failure_reason(event):
    failure = event.get('failure_reason') or {}
    return failure.get('description') or failure.get('ach_return_code')


def _annotate_failure(txn, event):
    reason = _failure_reason(event)
    if reason:
        txn.memo = f'{txn.memo} [rail: {reason}]'.strip()
