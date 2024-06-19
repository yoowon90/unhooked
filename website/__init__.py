from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_login import LoginManager

db = SQLAlchemy()
DB_NAME = "database.db"


def create_app():
    app = Flask(__name__)  # initialize the Flask app
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'  # encrypt the cookie/session data in our website
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'  # 
    db.init_app(app)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')  # how to access all of the urls inside blueprint files
    app.register_blueprint(auth, url_prefix='/')  # '/' means no prefix
    # TODO: register and adjust prefix whatever you want

    from .models import User, Note, Wishlist
    
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
    if not path.exists('website/' + DB_NAME):
        db.create_all(app=app)
        print('Created Database!')
