# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEBUG = True
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback-change-in-production')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-jwt-fallback-change-in-production')

class ProductionConfig(Config):
    GIT_BRANCH = 'main'
    FLASK_RUN_PORT = 5000
    DB_NAME = 'database_prod.db'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database_prod.db'
    DEBUG = False

class DevelopmentConfig(Config):
    GIT_BRANCH = 'develop'
    FLASK_RUN_PORT = 5001
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database_dev.db'
    SQLALCHEMY_BINDS = {'prod': 'sqlite:///database_prod.db'}
    DB_NAME = 'database_dev.db'
    DEBUG = True