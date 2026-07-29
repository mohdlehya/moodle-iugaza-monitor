#!/bin/sh
set -e

echo "🔄 [1/2] Running Alembic database migrations..."
alembic upgrade head
echo "✅ Migrations completed successfully."

echo "🚀 [2/2] Launching Moodle Monitor Bot & Web Server..."
exec python bot_runner.py
