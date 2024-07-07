# config.py

class Config:
    DEBUG = True # Seto True if want automatically rerun webserver after change
    TESTING = False
    SECRET_KEY = 'hjshjhdjah kjshkjdhjs'  # encrypt the cookie/session data in our website

class ProductionConfig(Config):
    GIT_BRANCH = 'main'
    FLASK_RUN_PORT = 5000
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database_prod.db'
    # encrypt the cookie/session data in our website

class DevelopmentConfig(Config):
    GIT_BRANCH = 'develop'
    FLASK_RUN_PORT = 5001
    SQLALCHEMY_DATABASE_URI = 'sqlite:///database_dev.db'
    DEBUG = True

# You can add more configurations as needed for different environments