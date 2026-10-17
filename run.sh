#!/bin/sh
# Start StockWatch locally with Gunicorn (Render uses render.yaml instead).
set -e

export PORT=${PORT:-8080}

echo "Starting StockWatch application on port $PORT..."
exec gunicorn --bind 0.0.0.0:$PORT wsgi:app --log-level info --timeout 120 --workers 1
