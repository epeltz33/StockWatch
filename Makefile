# Phony targets are targets that don't represent files
.PHONY: run test lint format migrate clean help

# Default target
all: help

# Run the development server
run:
	python dev_server.py

# Run tests
test:
	pytest tests/

# Run linter
lint:
	flake8 .

# Format code
format:
	black .

# Type checking
type-check:
	mypy .

# Database migrations
migrate:
	flask db migrate
	flask db upgrade

# Comprehensive check: format, lint, type-check, and test
check: format lint type-check test

# Install dependencies
install:
	pipenv install --dev

# Clean up pyc files and cache directories
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache

# Generate or update requirements.txt
requirements:
	pipenv lock -r > requirements.txt

# Run the Flask shell
shell:
	flask shell

# Display help information
help:
	@echo "Available commands:"
	@echo "  make run              - Run the development server"
	@echo "  make test             - Run tests"
	@echo "  make lint             - Run the linter"
	@echo "  make format           - Format the code"
	@echo "  make type-check       - Run type checking"
	@echo "  make migrate          - Run database migrations"
	@echo "  make check            - Run format, lint, type-check, and test"
	@echo "  make install          - Install dependencies"
	@echo "  make clean            - Clean up pyc files and cache directories"
	@echo "  make requirements     - Generate requirements.txt"
	@echo "  make shell            - Run Flask shell"
	@echo "  make help             - Display this help message"