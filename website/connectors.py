import os

from flask import Blueprint, render_template, redirect, url_for, session, request, flash
from flask_login import login_required, current_user
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from . import db

# Allow OAuth over HTTP in development
if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

connectors = Blueprint('connectors', __name__)

GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:5001/connectors/gmail/callback')


def _build_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv('GOOGLE_CLIENT_ID'),
                "client_secret": os.getenv('GOOGLE_CLIENT_SECRET'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=GMAIL_SCOPES,
        redirect_uri=REDIRECT_URI,
    )


@connectors.route('/settings')
@login_required
def settings():
    return render_template('settings.html', user=current_user)


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
    return redirect(auth_url)


@connectors.route('/connectors/gmail/callback')
@login_required
def gmail_callback():
    if request.args.get('state') != session.pop('gmail_oauth_state', None):
        flash('OAuth state mismatch — please try connecting again.', 'error')
        return redirect(url_for('connectors.settings'))

    flow = _build_flow()
    flow.fetch_token(authorization_response=request.url)
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


@connectors.route('/connectors/gmail/disconnect', methods=['POST'])
@login_required
def gmail_disconnect():
    current_user.gmail_access_token = None
    current_user.gmail_refresh_token = None
    current_user.gmail_token_expiry = None
    current_user.gmail_connected_email = None
    db.session.commit()
    flash('Gmail disconnected.', 'success')
    return redirect(url_for('connectors.settings'))
