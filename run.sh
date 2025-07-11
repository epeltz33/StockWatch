

echo "Starting StockWatch application..."

# Set default port if not provided
export PORT=${PORT:-8080}

# Run diagnostics first (optional - remove in production)
# python diagnose.py

# Try different startup methods
echo "Attempting to start with wsgi.py..."
gunicorn --bind 0.0.0.0:$PORT wsgi:app --log-level info --timeout 120 --workers 1

# If that fails, try app.py
if [ $? -ne 0 ]; then
    echo "wsgi.py failed, trying app.py..."
    gunicorn --bind 0.0.0.0:$PORT app:app --log-level info --timeout 120 --workers 1
fi

# If both fail, run a simple test
if [ $? -ne 0 ]; then
    echo "Both methods failed. Running diagnostics..."
    python diagnose.py
    exit 1
fi