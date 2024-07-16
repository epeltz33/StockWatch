from app import models
from flask import Flask
from config import Config
from app.extensions import db, migrate, login


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    login.login_view = 'auth.login'

    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.blueprints.stock import bp as stock_bp
    app.register_blueprint(stock_bp, url_prefix='/stock')

    from app.blueprints.user import bp as user_bp
    app.register_blueprint(user_bp, url_prefix='/user')

    # Register other blueprints here

    return app


# Initialize the Flask app
server = create_app()

# Import models at the bottom to avoid circular imports
