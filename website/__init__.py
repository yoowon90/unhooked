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
    
    print(app.config)

    
    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate

    from .views import views
    from .auth import auth
    from .reports import reports
    # TODO: ADD MORE

    app.register_blueprint(views, url_prefix='/')  # how to access all of the urls inside blueprint files
    app.register_blueprint(auth, url_prefix='/')  # '/' means no prefix
    app.register_blueprint(reports, url_prefix='/')  # '/' means no prefix
    # TODO: ADD MORE

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

class Format:

    def __init__(self):
        pass

    def format_time(self, timedelta: datetime.timedelta):
        if timedelta is None:
            return ""
        else:
            if timedelta.days > 0:
                leftover_seconds = timedelta - datetime.timedelta(days=timedelta.days)
                leftover_hours = leftover_seconds // 3600
                return f"{timedelta.days} day ago" if timedelta.days == 1 else f"{timedelta.days} days ago"
            
            elif timedelta.seconds > 3600:  # 1 hour
                return f"{timedelta.seconds // 3600} hrs ago"
            
            elif timedelta.seconds > 60:
                return f"{timedelta.seconds // 60} mins ago"

            else:
                return f"{timedelta.seconds} secs ago"

    def format_tag(self, tag):
        if tag is None or tag.strip() == "":
            return ""
        else:
            return "#" + tag
    
    def format_description(self, description):
        if description is None or description.strip() == "":
            return ""
        else:
            return "\n" + description
    