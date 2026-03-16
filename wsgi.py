"""
WSGI entry point for the StockWatch application.
This file is specifically designed to work with Gunicorn.
"""
import os
import sys
from pathlib import Path
import json

# Ensure the app directory is in the Python path
root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))

# #region agent log
def _agent_debug_log(hypothesis_id: str, message: str, data: dict | None = None, run_id: str = "initial"):
    """
    Minimal debug logger for this debug session.
    Writes NDJSON lines to the session-specific log file.
    """
    log_path = Path(__file__).parent / ".cursor" / "debug-f06670.log"
    payload = {
        "sessionId": "f06670",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": f"wsgi.py",
        "message": message,
        "data": data or {},
        "timestamp": __import__("time").time() * 1000,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        # Never let logging break the app path
        pass
# #endregion agent log

# Set default environment variables if not present
if 'DATABASE_URL' not in os.environ:
    print("WARNING: DATABASE_URL not set, using SQLite")
    os.environ['DATABASE_URL'] = 'sqlite:///app.db'

if 'SECRET_KEY' not in os.environ:
    print("WARNING: SECRET_KEY not set, using development key")
    os.environ['SECRET_KEY'] = 'dev-secret-key-change-this-in-production'

# Import and create the application
try:
    _agent_debug_log(
        hypothesis_id="H1",
        message="Attempting to import and create Flask application",
        data={},
    )
    from app import create_app
    application = create_app()

    # Also export as 'app' for compatibility
    app = application

    _agent_debug_log(
        hypothesis_id="H1",
        message="Flask application created successfully",
        data={"database_url_present": "DATABASE_URL" in os.environ},
    )
    print("✓ Flask application created successfully")
    print(f"✓ Database URL: {os.environ.get('DATABASE_URL', 'Not set')[:50]}...")
    print(f"✓ Polygon API Key: {'Set' if os.environ.get('POLYGON_API_KEY') else 'Not set'}")

except Exception as e:
    error_text = str(e)
    _agent_debug_log(
        hypothesis_id="H1",
        message="Failed to create Flask application",
        data={"error_type": type(e).__name__, "error_message": error_text},
    )
    print(f"✗ ERROR: Failed to create Flask application: {str(e)}")
    import traceback
    traceback.print_exc()

    # Create a minimal error app
    from flask import Flask, jsonify
    app = Flask(__name__)
    application = app

    @app.route('/')
    def index():
        _agent_debug_log(
            hypothesis_id="H2",
            message="Error app index route hit",
            data={"error_message": error_text},
        )
        return jsonify({
            "error": "Application failed to initialize",
            "details": error_text,
            "status": "error"
        }), 500

    @app.route('/health')
    def health():
        return jsonify({
            "status": "unhealthy",
            "error": error_text
        }), 503

# Ensure we're binding to the correct port
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting development server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)