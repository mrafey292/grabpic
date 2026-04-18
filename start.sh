#!/bin/bash
# start.sh — runs on every Railway deploy before the app starts
# Handles DB migrations and pgvector setup automatically

set -e  # exit immediately if any command fails

echo "==> Running DB migrations..."
flask --app run.py db upgrade

echo "==> Enabling pgvector extension..."
python -c "
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    db.session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
    db.session.commit()
    print('pgvector extension ready.')
"

echo "==> Running manual extras (IVFFlat index, crawl_jobs table)..."
python -c "
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    with open('migrations/manual_extras.sql') as f:
        sql = f.read()
    # Run each statement separately
    for stmt in sql.split(';'):
        stmt = stmt.strip()
        if stmt and not stmt.startswith('--'):
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f'  Skipped (likely already exists): {e}')
    print('Manual extras applied.')
"

echo "==> Starting gunicorn..."
exec gunicorn run:app \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 2 \
    --timeout 120 \
    --access-logfile -
