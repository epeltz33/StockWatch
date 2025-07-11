
# Build script for DigitalOcean deployment

echo "Building StockWatch application..."

# Ensure pip is up to date
pip install --upgrade pip

# Install all requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Run any database migrations if needed
  echo "Running database migrations..."
  flask db upgrade

echo "Build complete!"