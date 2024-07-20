from app import models
from flask import Flask
from config import Config
from app.extensions import db, migrate, login
from app.models import User
import os


def create_app(test_config=None):
    app = Flask(__name__, template_folder='templates')

    if test_config is None:
        app.config.from_object(Config)
        app.secret_key = os.environ.get('SECRET_KEY', 'fallback_secret_key')
    else:
        app.config.from_mapping(test_config)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    login.login_view = 'auth.login'

    @login.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.blueprints.stock import bp as stock_bp
    app.register_blueprint(stock_bp, url_prefix='/stock')

    from app.blueprints.user import bp as user_bp
    app.register_blueprint(user_bp, url_prefix='/user')

    from app.blueprints.main import bp as main_bp
    app.register_blueprint(main_bp)

    return app


# Initialize the Flask app
server = create_app()

# Import models at the bottom to avoid circular imports
