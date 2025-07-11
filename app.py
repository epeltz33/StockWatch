import os
import sys
from pathlib import Path

# Add the project root to Python path to ensure imports work correctly
sys.path.insert(0, str(Path(__file__).parent))

try:
    from app import create_app

    # Create the Flask application
    app = create_app()
    print(f"Flask app created successfully. Debug mode: {app.debug}")

except Exception as e:
    print(f"ERROR: Failed to create Flask app: {str(e)}")
    import traceback
    traceback.print_exc()
    # Create a minimal app for debugging
    from flask import Flask
    app = Flask(__name__)

    @app.route('/')
    def error():
        return f"App failed to initialize properly: {str(e)}", 500

    @app.route('/health')
    def health():
        return {"status": "unhealthy", "error": str(e)}, 503

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Starting app on port {port}")
    app.run(host='0.0.0.0', port=port)