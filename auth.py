import tempfile
import os
from flask import Blueprint, request
from flask_jwt_extended import create_access_token

from ..services.face_engine import extract_faces, match_selfie
from ..utils.response import ok, err

auth_bp = Blueprint("auth", __name__)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@auth_bp.post("/selfie")
def selfie_auth():
    """
    Authenticate with a selfie. Returns grab_id + JWT if a match is found.
    ---
    tags: [Auth]
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: selfie
        type: file
        required: true
        description: Clear solo selfie (JPEG/PNG/WEBP)
    responses:
      200:
        description: Match result with optional JWT token
      400:
        description: No face detected, or multiple faces
    """
    if "selfie" not in request.files:
        return err("No 'selfie' file in request.")

    file = request.files["selfie"]
    if file.content_type not in ALLOWED_TYPES:
        return err("Unsupported file type. Use JPEG, PNG, or WEBP.")

    # Save to a temp file so DeepFace can read it by path
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        faces = extract_faces(tmp_path)
    finally:
        os.unlink(tmp_path)   # clean up regardless

    if len(faces) == 0:
        return ok({"matched": False, "grab_id": None,
                   "message": "No face detected in the uploaded image."})

    if len(faces) > 1:
        return err("Multiple faces detected. Please upload a clear solo selfie.")

    result = match_selfie(faces[0]["embedding"])

    if result is None:
        return ok({"matched": False, "grab_id": None,
                   "message": "No matching identity found. You may not be in the indexed photos."})

    token = create_access_token(identity=result["grab_id"])
    return ok({
        "matched":    True,
        "grab_id":    result["grab_id"],
        "confidence": result["confidence"],
        "token":      token,
    })
