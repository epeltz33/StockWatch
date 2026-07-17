from dotenv import load_dotenv
from flask import Flask, redirect, request, url_for
from flask_login import current_user

from app.extensions import cache, csrf, db, limiter, login, migrate
from app.models import User
from config import Config

load_dotenv()


def create_app(test_config=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    if test_config is None:
        app.config.from_object(Config)
    else:
        app.config.from_mapping(test_config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    login.login_view = "auth.login"
    cache.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @login.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints. These are core to the app: a failure here should
    # crash startup loudly rather than serve a partially working site.
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.route("/")
    def index():
        return redirect(url_for("main.landing"))

    # Health check endpoint for Render/DigitalOcean
    @app.route("/health")
    def health_check():
        return {"status": "healthy"}, 200

    # The Dash app has a large import surface (plotly, dash, pandas); keep it
    # isolated so a Dash-side failure degrades the dashboard instead of taking
    # down auth and the rest of the site.
    try:
        from frontend.dashboard import create_dash_app

        with app.app_context():
            create_dash_app(app)
        # Dash posts to /dash/_dash-update-component without a CSRF token, so
        # global CSRFProtect would break every callback. Access to /dash/ is
        # gated by the login check below instead.
        for rule in app.url_map.iter_rules():
            if rule.rule.startswith("/dash"):
                csrf.exempt(app.view_functions[rule.endpoint])
        app.logger.info("Dash app mounted at /dash/")
    except Exception:
        app.logger.exception("Failed to create Dash app; continuing without it")

    @app.before_request
    def protect_dash():
        # The Dash app registers its own routes that bypass @login_required on
        # /dashboard; gate them all here.
        if request.path.startswith("/dash") and not current_user.is_authenticated:
            return login.unauthorized()

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # SAMEORIGIN (not DENY): /dashboard iframes /dash/ on the same origin
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    from app.cli import delete_user, seed_demo_user

    app.cli.add_command(delete_user)
    app.cli.add_command(seed_demo_user)

    return app
