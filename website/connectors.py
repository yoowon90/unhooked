import os
import re
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
from flask_login import login_required, current_user
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from . import db
from . import plaid_client
from . import transfers
from .models import WishItem, LedgerAccount
from .plaid_client import PlaidError
from .security import same_origin_required
from .tax import state_for_zip, taxed_price

connectors = Blueprint('connectors', __name__)

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}


def _redirect_uri():
    """Build redirect URI from the current request so it always matches the running server."""
    return url_for('connectors.gmail_callback', _external=True)


def _maybe_allow_insecure_oauth(redirect_uri):
    """Allow the OAuth lib to accept HTTP redirect URIs when we're targeting
    localhost. Self-hosted personal deployments don't have TLS; real public
    deployments behind a domain will have https URIs and this is a no-op.

    Setting this per-request (as opposed to once at module import) means the
    behavior follows the actual server binding, not FLASK_ENV.
    """
    parsed = urlparse(redirect_uri)
    if parsed.scheme == 'http' and parsed.hostname in LOCAL_HOSTS:
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'


def _build_flow():
    redirect_uri = _redirect_uri()
    _maybe_allow_insecure_oauth(redirect_uri)
    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv('GOOGLE_CLIENT_ID'),
                "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri],
            }
        },
        scopes=GMAIL_SCOPES,
        redirect_uri=redirect_uri,
    )


@connectors.route('/settings')
@login_required
def settings():
    linked_accounts = []
    if transfers.bank_connected(current_user):
        linked_accounts = (LedgerAccount.query
                           .filter_by(user_id=current_user.id)
                           .filter(LedgerAccount.provider_account_id.isnot(None))
                           .all())
    return render_template('settings.html', user=current_user,
                           plaid_configured=plaid_client.is_configured(),
                           linked_accounts=linked_accounts)


# ── Plaid (bank) connector ────────────────────────────────────────────────────

def _plaid_routes_enabled():
    from .purchases import savings_feature_enabled
    return savings_feature_enabled()


@connectors.route('/connectors/plaid/link-token', methods=['POST'])
@login_required
@same_origin_required
def plaid_link_token():
    """Mint a short-lived link_token to initialize Plaid Link in the browser."""
    if not _plaid_routes_enabled():
        return jsonify({'error': 'Not available in this environment'}), 404
    try:
        return jsonify({'link_token': plaid_client.create_link_token(current_user.id)})
    except PlaidError as e:
        return jsonify({'error': str(e)}), 502


@connectors.route('/connectors/plaid/exchange', methods=['POST'])
@login_required
@same_origin_required
def plaid_exchange():
    """Link onSuccess handler: exchange the public_token, store the encrypted
    access token, and map bank accounts onto the ledger buckets."""
    if not _plaid_routes_enabled():
        return jsonify({'error': 'Not available in this environment'}), 404
    public_token = (request.get_json() or {}).get('public_token')
    if not public_token:
        return jsonify({'error': 'public_token is required'}), 400
    try:
        transfers.connect_bank(current_user, public_token)
    except PlaidError as e:
        return jsonify({'error': str(e)}), 502
    flash(f'Bank connected: {current_user.plaid_institution_name or "linked"} (sandbox).', 'success')
    return jsonify({'success': True})


@connectors.route('/connectors/plaid/disconnect', methods=['POST'])
@login_required
@same_origin_required
def plaid_disconnect():
    if not _plaid_routes_enabled():
        return redirect(url_for('connectors.settings'))
    transfers.disconnect_bank(current_user)
    flash('Bank disconnected. Ledger history is preserved.', 'success')
    return redirect(url_for('connectors.settings'))


@connectors.route('/connectors/plaid/reconcile', methods=['POST'])
@login_required
@same_origin_required
def plaid_reconcile():
    """On-demand reconciliation from the Settings page: push (originate any
    ledger transactions still awaiting a rail transfer), then pull (drain
    Plaid's event feed onto ledger statuses)."""
    if not _plaid_routes_enabled():
        return redirect(url_for('connectors.settings'))
    from . import reconciliation
    push = transfers.originate_pending_transfers(current_user)
    try:
        summary = reconciliation.reconcile_transfers()
    except PlaidError as e:
        flash(f'Reconciliation failed: {e}', 'error')
        return redirect(url_for('connectors.settings'))
    parts = [f"{summary['events']} event(s) processed"]
    if push['originated']:
        parts.append(f"{push['originated']} transfer(s) originated")
    for key in ('settled', 'failed', 'returned'):
        if summary[key]:
            parts.append(f"{summary[key]} {key}")
    if summary['unmatched']:
        parts.append(f"⚠️ {len(summary['unmatched'])} unmatched transfer(s)")
    flash('Reconciliation: ' + ', '.join(parts) + '.', 'success')
    for detail in push['failures']:
        flash(f'Transfer not originated: {detail}', 'error')
    return redirect(url_for('connectors.settings'))


@connectors.route('/connectors/gmail/connect')
@login_required
def gmail_connect():
    if not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'):
        flash('GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env', 'error')
        return redirect(url_for('connectors.settings'))
    flow = _build_flow()
    auth_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
    )
    session['gmail_oauth_state'] = state
    # Persist PKCE code_verifier across the redirect if the library generated one
    cv = getattr(flow, 'code_verifier', None)
    if cv is None:
        oauth_session = getattr(flow, 'oauth2session', None) or getattr(flow, '_oauth2session', None)
        if oauth_session:
            cv = getattr(oauth_session, 'code_verifier', None)
    if cv:
        session['gmail_code_verifier'] = cv
    return redirect(auth_url)


@connectors.route('/connectors/gmail/callback')
@login_required
def gmail_callback():
    expected_state = session.pop('gmail_oauth_state', None)
    provided_state = request.args.get('state')
    # Both must be present and equal — guards against session-fixation where
    # neither side has a state and the comparison would otherwise pass.
    if not expected_state or not provided_state or expected_state != provided_state:
        session.pop('gmail_code_verifier', None)
        flash('OAuth state mismatch — please try connecting again.', 'error')
        return redirect(url_for('connectors.settings'))

    flow = _build_flow()
    code_verifier = session.pop('gmail_code_verifier', None)
    fetch_kwargs = dict(authorization_response=request.url)
    if code_verifier:
        fetch_kwargs['code_verifier'] = code_verifier
    flow.fetch_token(**fetch_kwargs)
    credentials = flow.credentials

    service = build('gmail', 'v1', credentials=credentials)
    profile = service.users().getProfile(userId='me').execute()

    current_user.gmail_access_token = credentials.token
    current_user.gmail_refresh_token = credentials.refresh_token or current_user.gmail_refresh_token
    current_user.gmail_token_expiry = credentials.expiry
    current_user.gmail_connected_email = profile.get('emailAddress')
    db.session.commit()

    flash(f"Gmail connected as {current_user.gmail_connected_email}.", 'success')
    return redirect(url_for('connectors.settings'))


@connectors.route('/settings/display-name', methods=['POST'])
@login_required
@same_origin_required
def update_display_name():
    new_name = (request.form.get('first_name') or '').strip()
    if not new_name:
        flash('Display name cannot be empty.', 'error')
        return redirect(url_for('connectors.settings'))
    if len(new_name) > 150:
        flash('Display name is too long (max 150 characters).', 'error')
        return redirect(url_for('connectors.settings'))
    if new_name == current_user.first_name:
        flash('Display name unchanged.', 'success')
        return redirect(url_for('connectors.settings'))

    current_user.first_name = new_name
    db.session.commit()
    flash(f'Display name updated to {new_name}.', 'success')
    return redirect(url_for('connectors.settings'))


@connectors.route('/settings/zipcode', methods=['POST'])
@login_required
@same_origin_required
def update_zipcode():
    new_zip = (request.form.get('zipcode') or '').strip()
    if not re.fullmatch(r'\d{5}', new_zip):
        flash('Zipcode must be exactly 5 digits.', 'error')
        return redirect(url_for('connectors.settings'))

    if new_zip == current_user.zipcode:
        flash('Zipcode unchanged.', 'success')
        return redirect(url_for('connectors.settings'))

    current_user.zipcode = new_zip

    # Recalculate taxes for ACTIVE WISHLIST items only — never touch purchased
    # or unhooked items, since those represent decisions already made at the
    # tax rate that was in effect at the time.
    wishlist_items = (WishItem.query
                      .filter_by(user_id=current_user.id, purchased=False, unhooked=False)
                      .all())
    recalculated = 0
    for item in wishlist_items:
        new_taxed = taxed_price(new_zip, item.price or 0.0)
        new_total = round(new_taxed + (item.delivery_fee or 0.0), 2)
        if item.taxed_price != new_taxed or item.total_price != new_total:
            item.taxed_price = new_taxed
            item.total_price = new_total
            recalculated += 1

    db.session.commit()

    state = state_for_zip(new_zip) or 'unknown region'
    if recalculated:
        flash(f'Zipcode updated to {new_zip} ({state}). Recalculated tax on {recalculated} wishlist item(s).', 'success')
    else:
        flash(f'Zipcode updated to {new_zip} ({state}).', 'success')
    return redirect(url_for('connectors.settings'))


@connectors.route('/connectors/gmail/disconnect', methods=['POST'])
@login_required
@same_origin_required
def gmail_disconnect():
    current_user.gmail_access_token = None
    current_user.gmail_refresh_token = None
    current_user.gmail_token_expiry = None
    current_user.gmail_connected_email = None
    db.session.commit()
    flash('Gmail disconnected.', 'success')
    return redirect(url_for('connectors.settings'))
