#!/bin/bash

set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting the FastAPI server..."

exec "$@"