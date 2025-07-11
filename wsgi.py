"""
WSGI entry point for the StockWatch application.
This file is specifically designed to work with Gunicorn.
"""
import os
import sys
from pathlib import Path

# Ensure the app directory is in the Python path
root_path = Path(__file__).parent
sys.path.insert(0, str(root_path))

# Set default environment variables if not present
if 'DATABASE_URL' not in os.environ:
    print("WARNING: DATABASE_URL not set, using SQLite")
    os.environ['DATABASE_URL'] = 'sqlite:///app.db'

if 'SECRET_KEY' not in os.environ:
    print("WARNING: SECRET_KEY not set, using development key")
    os.environ['SECRET_KEY'] = 'dev-secret-key-change-this-in-production'

# Import and create the application
try:
    from app import create_app
    application = create_app()

    # Also export as 'app' for compatibility
    app = application

    print("✓ Flask application created successfully")
    print(f"✓ Database URL: {os.environ.get('DATABASE_URL', 'Not set')[:50]}...")
    print(f"✓ Polygon API Key: {'Set' if os.environ.get('POLYGON_API_KEY') else 'Not set'}")

except Exception as e:
    print(f"✗ ERROR: Failed to create Flask application: {str(e)}")
    import traceback
    traceback.print_exc()

    # Create a minimal error app
    from flask import Flask, jsonify
    app = Flask(__name__)
    application = app

    @app.route('/')
    def index():
        return jsonify({
            "error": "Application failed to initialize",
            "details": str(e),
            "status": "error"
        }), 500

    @app.route('/health')
    def health():
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503

# Ensure we're binding to the correct port
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting development server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)