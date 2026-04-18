"""
crawler.py  —  scalable version

Key improvements over naive version:
  - Job state stored in DB (works across multiple gunicorn workers, survives restarts)
  - ThreadPoolExecutor processes images in parallel (configurable workers)
  - Batch DB commits every BATCH_SIZE images (avoids one giant transaction)
  - Face extraction runs in threads; DB writes happen in main thread (session-safe)
"""

import os
import uuid
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import text

from ..extensions import db
from ..models import Image, ImageFace
from .face_engine import extract_faces, find_or_create_identity

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
BATCH_SIZE  = 50   # commit to DB every N images
MAX_WORKERS = 4    # parallel DeepFace threads — tune to your CPU core count


# ── Public API ────────────────────────────────────────────────────────────────

def start_crawl(storage_path: str = None, force_reindex: bool = False, app=None) -> str:
    job_id       = str(uuid.uuid4())
    storage_path = storage_path or current_app.config["STORAGE_PATH"]
    app          = app or current_app._get_current_object()

    # Persist job row immediately — any worker can now read it
    db.session.execute(text("""
        INSERT INTO crawl_jobs
            (job_id, status, storage_path, images_processed,
             images_total, faces_discovered, unique_identities,
             errors, started_at)
        VALUES
            (:job_id, 'running', :path, 0, 0, 0, 0, '[]'::jsonb, NOW())
    """), {"job_id": job_id, "path": storage_path})
    db.session.commit()

    thread = threading.Thread(
        target=_run_crawl,
        args=(job_id, storage_path, force_reindex, app),
        daemon=True,
    )
    thread.start()
    return job_id


def get_job_status(job_id: str) -> dict | None:
    row = db.session.execute(
        text("SELECT * FROM crawl_jobs WHERE job_id = :id"),
        {"id": job_id}
    ).fetchone()
    return dict(row._mapping) if row else None


# ── Internal ──────────────────────────────────────────────────────────────────

def _run_crawl(job_id: str, storage_path: str, force_reindex: bool, app):
    with app.app_context():
        try:
            all_files = _discover_images(storage_path)
            _update_job(job_id, images_total=len(all_files))

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures = {
                    pool.submit(_extract_one, fp, storage_path): fp
                    for fp in all_files
                }
                batch = []
                for future in as_completed(futures):
                    batch.append(future.result())
                    if len(batch) >= BATCH_SIZE:
                        _flush_batch(job_id, batch)
                        batch = []
                if batch:
                    _flush_batch(job_id, batch)

            _update_job(job_id, status="completed", completed_at=_now())

        except Exception as e:
            _update_job(job_id, status="failed", completed_at=_now())
            _append_error(job_id, str(e))


def _extract_one(abs_path: str, storage_root: str) -> dict:
    """
    Runs in a thread pool. Only does CPU work (DeepFace).
    Does NOT touch the DB — SQLAlchemy sessions are not thread-safe.
    """
    try:
        rel_path = os.path.relpath(abs_path, storage_root)
        faces    = extract_faces(abs_path)
        return {"rel_path": rel_path, "faces": faces, "error": None}
    except Exception as e:
        return {"rel_path": abs_path, "faces": [], "error": str(e)}


def _flush_batch(job_id: str, results: list[dict]):
    """Commit a batch to DB. Runs in the main thread (session-safe)."""
    faces_count = new_ids = 0
    errors = []

    for r in results:
        if r["error"]:
            errors.append(r["error"])
            continue

        rel_path  = r["rel_path"]
        file_name = os.path.basename(rel_path)

        existing = db.session.query(Image).filter_by(file_path=rel_path).first()
        if existing:
            image_row = existing
            db.session.query(ImageFace).filter_by(image_id=image_row.image_id).delete()
        else:
            image_row = Image(file_path=rel_path, file_name=file_name)
            db.session.add(image_row)
            db.session.flush()

        for face in r["faces"]:
            identity, is_new = find_or_create_identity(face["embedding"])
            if is_new:
                new_ids += 1
            db.session.add(ImageFace(
                image_id=image_row.image_id,
                grab_id=identity.grab_id,
                bbox=face["bbox"],
                confidence=face["confidence"],
            ))
            faces_count += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        errors.append(f"Batch commit failed: {e}")

    db.session.execute(text("""
        UPDATE crawl_jobs SET
            images_processed  = images_processed  + :n,
            faces_discovered  = faces_discovered  + :f,
            unique_identities = unique_identities + :u,
            errors            = errors || :e::jsonb
        WHERE job_id = :id
    """), {"id": job_id, "n": len(results), "f": faces_count,
           "u": new_ids, "e": json.dumps(errors)})
    db.session.commit()


def _update_job(job_id, **kwargs):
    sets = ", ".join(f"{k} = :{k}" for k in kwargs)
    kwargs["job_id"] = job_id
    db.session.execute(
        text(f"UPDATE crawl_jobs SET {sets} WHERE job_id = :job_id"), kwargs
    )
    db.session.commit()


def _append_error(job_id, error_msg):
    db.session.execute(text("""
        UPDATE crawl_jobs SET errors = errors || :e::jsonb WHERE job_id = :id
    """), {"id": job_id, "e": json.dumps([error_msg])})
    db.session.commit()


def _discover_images(storage_path: str) -> list[str]:
    found = []
    for root, _, files in os.walk(storage_path):
        for f in files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(root, f))
    return found


def _now():
    return datetime.now(timezone.utc)
