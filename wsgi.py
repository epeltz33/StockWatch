"""
WSGI entry point for the StockWatch application.
This file is specifically designed to work with Gunicorn.
"""
import os
import sys
from pathlib import Path

root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))


def _is_production() -> bool:
    return (
        os.environ.get("FLASK_ENV") == "production"
        or os.environ.get("RENDER") == "true"
        or os.environ.get("DIGITALOCEAN_APP_ID") is not None
    )


def _configure_environment() -> None:
    if _is_production():
        missing = [
            name
            for name in ("DATABASE_URL", "SECRET_KEY", "POLYGON_API_KEY")
            if not os.environ.get(name)
        ]
        if missing:
            raise RuntimeError(
                "Missing required production environment variables: "
                + ", ".join(missing)
            )
        return

    if "DATABASE_URL" not in os.environ:
        print("WARNING: DATABASE_URL not set, using SQLite")
        os.environ["DATABASE_URL"] = "sqlite:///app.db"

    if "SECRET_KEY" not in os.environ:
        print("WARNING: SECRET_KEY not set, using development key")
        os.environ["SECRET_KEY"] = "dev-secret-key-change-this-in-production"


try:
    _configure_environment()
    from app import create_app

    application = create_app()
    app = application

    print("✓ Flask application created successfully")
    print(f"✓ Database URL: {os.environ.get('DATABASE_URL', 'Not set')[:50]}...")
    print(
        f"✓ Polygon API Key: {'Set' if os.environ.get('POLYGON_API_KEY') else 'Not set'}"
    )

except Exception as e:
    error_text = str(e)
    print(f"✗ ERROR: Failed to create Flask application: {error_text}")
    import traceback

    traceback.print_exc()

    from flask import Flask, jsonify

    app = Flask(__name__)
    application = app

    @app.route("/")
    def index():
        return jsonify(
            {
                "error": "Application failed to initialize",
                "details": error_text,
                "status": "error",
            }
        ), 500

    @app.route("/health")
    def health():
        return jsonify({"status": "unhealthy", "error": error_text}), 503


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting development server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
