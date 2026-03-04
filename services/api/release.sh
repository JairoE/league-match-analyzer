#!/bin/bash
set -e

echo "Running database migrations (release step)..."
cd /workspace/services/api
alembic upgrade head
echo "Database migrations complete."