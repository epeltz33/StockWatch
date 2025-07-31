from flask import Flask, redirect, url_for
from config import Config
from app.extensions import db, migrate, login, cache
from app.models import User
import os
from dotenv import load_dotenv

load_dotenv()


def create_app(test_config=None):
    print("Creating Flask application...")

    app = Flask(__name__, template_folder='templates', static_folder='static')

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    # Initialize extensions
    print("Initializing database...")
    db.init_app(app)

    print("Initializing migrations...")
    migrate.init_app(app, db)

    print("Initializing login manager...")
    login.init_app(app)
    login.login_view = 'auth.login'

    # Initialize caching
    print("Initializing cache...")
    cache.init_app(app)

    @login.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    print("Registering blueprints...")
    try:
        from app.blueprints.auth import auth_bp
        app.register_blueprint(auth_bp)
        print("✓ Auth blueprint registered")
    except Exception as e:
        print(f"✗ Failed to register auth blueprint: {e}")

    try:
        from app.blueprints.stock import bp as stock_bp
        app.register_blueprint(stock_bp, url_prefix='/stock')
        print("✓ Stock blueprint registered")
    except Exception as e:
        print(f"✗ Failed to register stock blueprint: {e}")

    try:
        from app.blueprints.user import bp as user_bp
        app.register_blueprint(user_bp, url_prefix='/user')
        print("✓ User blueprint registered")
    except Exception as e:
        print(f"✗ Failed to register user blueprint: {e}")

    try:
        from app.blueprints.main import bp as main_bp
        app.register_blueprint(main_bp)
        print("✓ Main blueprint registered")
    except Exception as e:
        print(f"✗ Failed to register main blueprint: {e}")

    @app.route('/')
    def index():
        return redirect(url_for('main.landing'))

    # Health check endpoint for DigitalOcean
    @app.route('/health')
    def health_check():
        return {'status': 'healthy'}, 200

    # Import create_dash_app with error handling
    try:
        print("Creating Dash app...")
        from frontend.dashboard import create_dash_app
        with app.app_context():
            create_dash_app(app)
        print("✓ Dash app created")
    except Exception as e:
        print(f"✗ Failed to create Dash app: {e}")
        # Continue without Dash if it fails
        import traceback
        traceback.print_exc()

    print("✓ Flask application created successfully")
    return app