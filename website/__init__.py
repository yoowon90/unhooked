import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import ProductionConfig, DevelopmentConfig
import datetime

db = SQLAlchemy()  # not sure if this is right if want to use migrate

def create_app():
    # initialize the Flask app
    app = Flask(__name__)
    app.config.from_object('config')  # from config.py

    # Load configuration based on FLASK_ENV
    flask_env = os.getenv('FLASK_ENV')
    print(f'Flask env: {flask_env}')
    if flask_env == 'production':
        app.config.from_object(ProductionConfig)
    elif flask_env == 'development':
        app.config.from_object(DevelopmentConfig)

    
    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')  # how to access all of the urls inside blueprint files
    app.register_blueprint(auth, url_prefix='/')  # '/' means no prefix
    # TODO: register and adjust prefix whatever you want

    from .models import User, Note, WishItem
    
    with app.app_context():
        db.create_all()

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    return app

def create_database(app):
    db_name = app.config['DB_NAME']
    if not os.path.exists('website/' + db_name):
        with app.app_context():  # https://stackoverflow.com/questions/44941757/sqlalchemy-exc-operationalerror-sqlite3-operationalerror-no-such-table
            db.create_all()
        print('Created Database!')

def format_time(timedelta: datetime.timedelta):
    if timedelta is None:
        return ""
    else:
        if timedelta.days > 0:
            leftover_seconds = timedelta - datetime.timedelta(days=timedelta.days)
            leftover_hours = leftover_seconds // 3600
            return f"{timedelta.days} day ago" if timedelta.days == 1 else f"{timedelta.days} days ago"
        
        elif timedelta.seconds > 3600:
            return f"{timedelta.seconds // 3600} hrs ago"
        else: 
            return f"{timedelta.seconds} secs ago"
