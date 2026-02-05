#!/bin/bash
set -e

echo "Running database migrations..."
cd /workspace/services/api
alembic upgrade head

echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
