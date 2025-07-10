from flask import Flask, redirect, url_for
from config import Config
from app.extensions import db, migrate, login
from app.models import User
import os
from dotenv import load_dotenv

load_dotenv()


def create_app(test_config=None):
    app = Flask(__name__, template_folder='templates', static_folder='static')

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

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

    @app.route('/')
    def index():
        return redirect(url_for('main.landing'))

    # Health check endpoint for DigitalOcean
    @app.route('/health')
    def health_check():
        return {'status': 'healthy'}, 200

    # Import create_dash_app
    from frontend.dashboard import create_dash_app

    with app.app_context():
        # Create Dash app within app_context
        create_dash_app(app)

    return app