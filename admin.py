from flask import Blueprint, request, current_app
from ..services import crawler
from ..utils.response import ok, err
from ..utils.auth import require_admin
from ..extensions import db
from ..models import Image, FaceIdentity, ImageFace

admin_bp = Blueprint("admin", __name__)


@admin_bp.post("/crawl")
@require_admin
def start_crawl():
    """
    Trigger a crawl of the storage directory.
    ---
    tags: [Admin]
    security:
      - Bearer: []
    parameters:
      - in: header
        name: X-Admin-Key
        required: true
        type: string
    requestBody:
      content:
        application/json:
          schema:
            properties:
              storage_path: {type: string}
              force_reindex: {type: boolean, default: false}
    responses:
      200:
        description: Crawl job started
    """
    body          = request.get_json(silent=True) or {}
    storage_path  = body.get("storage_path", current_app.config["STORAGE_PATH"])
    force_reindex = body.get("force_reindex", False)

    if not __import__("os").path.exists(storage_path):
        return err(f"storage_path '{storage_path}' does not exist.")

    job_id = crawler.start_crawl(storage_path, force_reindex)
    return ok({
        "job_id": job_id,
        "status": "started",
        "message": f"Poll /api/v1/admin/crawl/status/{job_id} for progress.",
    })


@admin_bp.get("/crawl/status/<job_id>")
@require_admin
def crawl_status(job_id):
    """
    Get crawl job progress.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: job_id
        type: string
        required: true
    responses:
      200:
        description: Job status
    """
    job = crawler.get_job_status(job_id)
    if not job:
        return err("Job not found.", 404)
    return ok({"job_id": job_id, **job})


@admin_bp.get("/stats")
@require_admin
def stats():
    """
    Get overall system stats.
    ---
    tags: [Admin]
    responses:
      200:
        description: System statistics
    """
    return ok({
        "total_images":           db.session.query(Image).count(),
        "total_faces_detected":   db.session.query(ImageFace).count(),
        "total_unique_identities": db.session.query(FaceIdentity).count(),
        "storage_path":           current_app.config["STORAGE_PATH"],
    })
