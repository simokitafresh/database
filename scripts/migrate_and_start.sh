#!/bin/bash
# Render.com deployment script for database migration

echo "Starting database migration..."

# Install dependencies if needed
pip install --upgrade pip
pip install -r requirements.txt

# Run database migration
echo "Running alembic upgrade head..."
alembic upgrade head

echo "Migration completed successfully!"

# Start the application
echo "Starting application..."
exec gunicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2 --worker-class uvicorn.workers.UvicornWorker --timeout 60