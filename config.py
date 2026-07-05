# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-jwt-fallback-change-in-production')
    # Savings-ledger feature (post-purchase interstitial, Plaid bank link,
    # ACH transfers, reconciliation). Dev-only for now: the schema exists in
    # both DBs, but the feature is invisible unless a config enables it.
    SAVINGS_FEATURE_ENABLED = False

def _resolve_prod_db_uri():
    url = os.environ.get('DATABASE_URL')
    if not url:
        return 'sqlite:///database_prod.db'
    # SQLAlchemy needs the driver suffix to pick psycopg2 unambiguously.
    if url.startswith('postgresql://'):
        url = 'postgresql+psycopg2://' + url[len('postgresql://'):]
    return url


class ProductionConfig(Config):
    GIT_BRANCH = 'main'
    FLASK_RUN_PORT = 5000
    DB_NAME = 'database_prod.db'
    SQLALCHEMY_DATABASE_URI = _resolve_prod_db_uri()
    DEBUG = False
    SAVINGS_FEATURE_ENABLED = False  # explicit: dev-only feature

class DevelopmentConfig(Config):
    GIT_BRANCH = 'develop'
    FLASK_RUN_PORT = 5001
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database_dev.db'
    SQLALCHEMY_BINDS = {'prod': 'sqlite:///database_prod.db'}
    DB_NAME = 'database_dev.db'
    DEBUG = True
    SAVINGS_FEATURE_ENABLED = True