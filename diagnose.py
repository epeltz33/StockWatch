
"""
Diagnostic script to check StockWatch deployment issues
"""
import os
import sys
from pathlib import Path

print("=" * 60)
print("StockWatch Deployment Diagnostics")
print("=" * 60)

# Check Python version
print(f"\n1. Python Version: {sys.version}")

# Check working directory
print(f"\n2. Working Directory: {os.getcwd()}")

# Check if app module exists
print("\n3. Checking app module...")
try:
    import app
    print("   ✓ app module found")
    print(f"   ✓ app module path: {app.__file__}")
except ImportError as e:
    print(f"   ✗ Failed to import app module: {e}")

# Check if app.py exists
app_py = Path("app.py")
if app_py.exists():
    print(f"   ✓ app.py exists at: {app_py.absolute()}")
else:
    print(f"   ✗ app.py not found")

# Check environment variables
print("\n4. Environment Variables:")
env_vars = ['DATABASE_URL', 'SECRET_KEY', 'POLYGON_API_KEY', 'PORT']
for var in env_vars:
    value = os.environ.get(var)
    if value:
        if var in ['DATABASE_URL', 'SECRET_KEY', 'POLYGON_API_KEY']:
            # Mask sensitive data
            print(f"   ✓ {var}: {'*' * 10} (set)")
        else:
            print(f"   ✓ {var}: {value}")
    else:
        print(f"   ✗ {var}: Not set")

# Try to create the app
print("\n5. Attempting to create Flask app...")
try:
    from app import create_app
    flask_app = create_app()
    print("   ✓ Flask app created successfully")

    # Check routes
    print("\n6. Registered routes:")
    for rule in flask_app.url_map.iter_rules():
        print(f"   - {rule}")

except Exception as e:
    print(f"   ✗ Failed to create Flask app: {e}")
    import traceback
    traceback.print_exc()

# Check if wsgi.py works
print("\n7. Testing wsgi.py import...")
try:
    import wsgi
    if hasattr(wsgi, 'app'):
        print("   ✓ wsgi.app found")
    else:
        print("   ✗ wsgi module has no 'app' attribute")
except Exception as e:
    print(f"   ✗ Failed to import wsgi: {e}")

# Check dependencies
print("\n8. Checking key dependencies...")
deps = ['flask', 'gunicorn', 'dash', 'flask_sqlalchemy', 'flask_login', 'polygon']
for dep in deps:
    try:
        __import__(dep)
        print(f"   ✓ {dep} installed")
    except ImportError:
        print(f"   ✗ {dep} NOT installed")

print("\n" + "=" * 60)
print("Diagnostics complete")
print("=" * 60)