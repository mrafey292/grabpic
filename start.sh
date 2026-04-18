#!/bin/bash
# start.sh — runs on every Railway deploy before the app starts
# Handles DB migrations and pgvector setup automatically

set -e  # exit immediately if any command fails

# Skip DeepFace preload during DB setup commands (avoids TF/CUDA issues)
export SKIP_DEEPFACE_PRELOAD=1

# Check for DATABASE_URL before proceeding
if [ -z "$DATABASE_URL" ]; then
    echo "=========================================================="
    echo "ERROR: DATABASE_URL environment variable is missing!"
    echo "Did you provision a PostgreSQL database in Railway?"
    echo "Railway healthcheck will fail because the app cannot start."
    echo "=========================================================="
    # We still try to start gunicorn so the user can see the logs of it crashing,
    # or so the healthcheck might hit the server if we bypass DB (but app requires DB).
fi

echo "==> Enabling pgvector extension (must be before migrations)..."
python -c "
from app import create_app
from app.extensions import db
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

app = create_app()
with app.app_context():
    try:
        db.session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        db.session.commit()
        print('pgvector extension ready.')
    except OperationalError as e:
        print(f'Database connection failed: {e}')
" || true # Don't exit start.sh if DB connection fails, let gunicorn start to show errors

echo "==> Running DB migrations..."
flask --app run.py db upgrade || true

echo "==> Running manual extras (IVFFlat index, crawl_jobs table)..."
python -c "
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        with open('migrations/manual_extras.sql') as f:
            sql = f.read()
        for stmt in sql.split(';'):
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    db.session.execute(text(stmt))
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
        print('Manual extras applied.')
    except Exception as e:
        print(f'Skipping extras due to error: {e}')
"

# Unset so the actual server DOES preload DeepFace
unset SKIP_DEEPFACE_PRELOAD

echo "==> Starting gunicorn..."
exec gunicorn run:app \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 1 \
    --timeout 120 \
    --access-logfile -
