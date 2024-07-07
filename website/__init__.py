import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import ProductionConfig, DevelopmentConfig

db = SQLAlchemy()  # not sure if this is right if want to use migrate

def create_app():
    # initialize the Flask app
    app = Flask(__name__)
    app.config.from_object('config')  # from config.py

    # Load configuration based on FLASK_ENV
    print(f'flask env: {os.getenv('FLASK_ENV')}')
    if os.getenv('FLASK_ENV') == 'production':
        app.config.from_object(ProductionConfig)
    elif os.getenv('FLASK_ENV') == 'development':
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
    if not os.path.exists('website/' + DB_NAME):
        with app.app_context():  # https://stackoverflow.com/questions/44941757/sqlalchemy-exc-operationalerror-sqlite3-operationalerror-no-such-table
            db.create_all()
        print('Created Database!')
