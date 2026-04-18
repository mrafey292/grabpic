import os
from flask import Blueprint, request, current_app
from werkzeug.utils import secure_filename

from ..services import crawler
from ..utils.response import ok, err
from ..utils.auth import require_admin
from ..extensions import db
from ..models import Image, FaceIdentity, ImageFace

admin_bp = Blueprint("admin", __name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


@admin_bp.post("/crawl")
@require_admin
def start_crawl():
    """
    Trigger a crawl of the storage directory.
    ---
    tags: [Admin]
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

    if not os.path.exists(storage_path):
        return err(f"storage_path '{storage_path}' does not exist.")

    try:
        job_id = crawler.start_crawl(storage_path, force_reindex)
        return ok({
            "job_id": job_id,
            "status": "started",
            "message": f"Poll /api/v1/admin/crawl/status/{job_id} for progress.",
        })
    except Exception as e:
        import traceback
        return err(f"Crawler start failed: {str(e)}\n\n{traceback.format_exc()}", 500)


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
      - in: header
        name: X-Admin-Key
        required: true
        type: string
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
    parameters:
      - in: header
        name: X-Admin-Key
        required: true
        type: string
    responses:
      200:
        description: System statistics
    """
    return ok({
        "total_images":            db.session.query(Image).count(),
        "total_faces_detected":    db.session.query(ImageFace).count(),
        "total_unique_identities": db.session.query(FaceIdentity).count(),
        "storage_path":            current_app.config["STORAGE_PATH"],
    })


@admin_bp.post("/upload")
@require_admin
def upload_photos():
    """
    Upload one or more photos to the storage directory.
    ---
    tags: [Admin]
    consumes:
      - multipart/form-data
    parameters:
      - in: header
        name: X-Admin-Key
        required: true
        type: string
      - in: formData
        name: photos
        type: file
        required: true
        description: One or more image files (JPEG/PNG/WEBP/BMP)
    responses:
      200:
        description: Files saved successfully
      400:
        description: No files provided or invalid file types
    """
    if "photos" not in request.files:
        return err("No 'photos' file field in request.")

    files = request.files.getlist("photos")
    if not files or all(f.filename == "" for f in files):
        return err("No files selected for upload.")

    storage_path = current_app.config["STORAGE_PATH"]
    os.makedirs(storage_path, exist_ok=True)

    saved = []
    rejected = []

    for file in files:
        if not file.filename:
            continue

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            rejected.append({
                "filename": file.filename,
                "reason": f"Unsupported extension '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            })
            continue

        safe_name = secure_filename(file.filename)
        dest_path = os.path.join(storage_path, safe_name)

        # Avoid overwriting: append counter if file exists
        if os.path.exists(dest_path):
            base, extension = os.path.splitext(safe_name)
            counter = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(storage_path, f"{base}_{counter}{extension}")
                counter += 1

        file.save(dest_path)
        saved.append({
            "filename": os.path.basename(dest_path),
            "path": os.path.relpath(dest_path, storage_path),
            "size_bytes": os.path.getsize(dest_path),
        })

    return ok({
        "saved": saved,
        "rejected": rejected,
        "total_saved": len(saved),
        "total_rejected": len(rejected),
        "message": f"Upload complete. {len(saved)} saved, {len(rejected)} rejected."
               + " Run POST /api/v1/admin/crawl to index the new photos." if saved else "",
    })
