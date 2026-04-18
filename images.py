import os
import io
from flask import Blueprint, current_app, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from PIL import Image as PILImage

from ..extensions import db
from ..models import Image, ImageFace
from ..utils.response import ok, err

images_bp = Blueprint("images", __name__)


@images_bp.get("")
@jwt_required()
def list_images():
    """
    Get all images containing the authenticated user's face.
    ---
    tags: [Images]
    security:
      - Bearer: []
    parameters:
      - in: query
        name: page
        type: integer
        default: 1
      - in: query
        name: per_page
        type: integer
        default: 20
    responses:
      200:
        description: Paginated list of images
    """
    grab_id  = get_jwt_identity()
    page     = int(current_app.request.args.get("page", 1)) if False else \
               _int_arg("page", 1)
    per_page = min(_int_arg("per_page", 20), 100)

    from flask import request
    page     = _int_arg("page", 1)
    per_page = min(_int_arg("per_page", 20), 100)

    query = (
        db.session.query(Image, ImageFace)
        .join(ImageFace, Image.image_id == ImageFace.image_id)
        .filter(ImageFace.grab_id == grab_id)
        .order_by(Image.ingested_at.desc())
    )

    total    = query.count()
    results  = query.offset((page - 1) * per_page).limit(per_page).all()

    return ok({
        "grab_id":  grab_id,
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "images":   [img.to_dict(face) for img, face in results],
    })


@images_bp.get("/<image_id>")
@jwt_required()
def get_image(image_id):
    """
    Get metadata for a single image (must contain your face).
    ---
    tags: [Images]
    security:
      - Bearer: []
    parameters:
      - in: path
        name: image_id
        type: string
        required: true
    responses:
      200:
        description: Image metadata
      403:
        description: Your face is not in this image
      404:
        description: Image not found
    """
    grab_id = get_jwt_identity()
    image   = db.session.get(Image, image_id)
    if not image:
        return err("Image not found.", 404)

    face_entry = (
        db.session.query(ImageFace)
        .filter_by(image_id=image_id, grab_id=grab_id)
        .first()
    )
    if not face_entry:
        return err("This image does not contain your face.", 403)

    all_grab_ids = [
        str(f.grab_id)
        for f in db.session.query(ImageFace).filter_by(image_id=image_id).all()
    ]

    return ok({**image.to_dict(face_entry), "all_grab_ids": all_grab_ids})


@images_bp.get("/<image_id>/file")
@jwt_required()
def serve_file(image_id):
    """
    Stream the raw image file.
    ---
    tags: [Images]
    security:
      - Bearer: []
    responses:
      200:
        description: Raw image binary
    """
    grab_id, image, _ = _get_authorized_image(image_id)
    if image is None:
        return grab_id   # grab_id is the error response here

    abs_path = os.path.join(current_app.config["STORAGE_PATH"], image.file_path)
    if not os.path.exists(abs_path):
        return err("Image file not found on disk.", 404)

    return send_file(abs_path, mimetype="image/jpeg")


@images_bp.get("/<image_id>/thumbnail")
@jwt_required()
def serve_thumbnail(image_id):
    """
    Stream a 300x300 thumbnail of the image.
    ---
    tags: [Images]
    security:
      - Bearer: []
    responses:
      200:
        description: Thumbnail image binary
    """
    grab_id, image, _ = _get_authorized_image(image_id)
    if image is None:
        return grab_id

    storage_path = current_app.config["STORAGE_PATH"]
    abs_path     = os.path.join(storage_path, image.file_path)
    thumb_dir    = os.path.join(storage_path, ".thumbnails")
    thumb_path   = os.path.join(thumb_dir, f"{image_id}.jpg")

    os.makedirs(thumb_dir, exist_ok=True)

    # Generate once, serve from disk cache on every subsequent request
    if not os.path.exists(thumb_path):
        if not os.path.exists(abs_path):
            return err("Image file not found on disk.", 404)
        img = PILImage.open(abs_path)
        img.thumbnail((300, 300))
        img.save(thumb_path, format="JPEG", quality=85)

    return send_file(thumb_path, mimetype="image/jpeg")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_authorized_image(image_id):
    """Returns (grab_id, image, face_entry) or (error_response, None, None)."""
    grab_id = get_jwt_identity()
    image   = db.session.get(Image, image_id)
    if not image:
        return err("Image not found.", 404), None, None

    face_entry = (
        db.session.query(ImageFace)
        .filter_by(image_id=image_id, grab_id=grab_id)
        .first()
    )
    if not face_entry:
        return err("This image does not contain your face.", 403), None, None

    return grab_id, image, face_entry


def _int_arg(name, default):
    from flask import request
    try:
        return max(1, int(request.args.get(name, default)))
    except (ValueError, TypeError):
        return default
