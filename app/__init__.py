from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
from app.extensions import db, migrate, login


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    login.login_view = 'auth.login'

    from app.blueprints.stock import bp as stock_bp
    app.register_blueprint(stock_bp, url_prefix='/stock')

    # Register other blueprints here

    return app


# Import models at the bottom to avoid circular imports
from app import models
