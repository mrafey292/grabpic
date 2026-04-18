"""
face_engine.py

Wraps DeepFace for:
  1. Extracting 512-d ArcFace embeddings from an image (one per face detected)
  2. Finding or creating a FaceIdentity via pgvector cosine similarity
  3. Matching a selfie against all known grab_ids

NOTE: DeepFace and numpy are imported lazily inside functions to avoid
loading TensorFlow at module import time (which segfaults on systems
without CUDA when running CLI commands like flask db init).
"""

from flask import current_app
from sqlalchemy import text

from ..extensions import db
from ..models import FaceIdentity


# ── Helpers ──────────────────────────────────────────────────────────────────

def _model():
    return current_app.config["FACE_MODEL"]       # "ArcFace"

def _detector():
    return current_app.config["FACE_DETECTOR"]    # "retinaface"

def _threshold():
    return current_app.config["FACE_SIMILARITY_THRESHOLD"]  # 0.40


# ── Core functions ────────────────────────────────────────────────────────────

def extract_faces(image_path: str) -> list[dict]:
    """
    Detect all faces in an image and return their embeddings + bounding boxes.

    Returns list of:
      {
        "embedding": [float, ...],   # 512-d ArcFace vector
        "bbox": {"x": int, "y": int, "w": int, "h": int},
        "confidence": float
      }

    Returns [] if no faces are detected (won't raise).
    """
    try:
        from deepface import DeepFace
        results = DeepFace.represent(
            img_path=image_path,
            model_name=_model(),
            detector_backend=_detector(),
            enforce_detection=True,   # raises if no face — we catch it
            align=True,
        )
    except ValueError:
        # DeepFace raises ValueError when no face is detected
        return []

    faces = []
    for r in results:
        region = r.get("facial_area", {})
        faces.append({
            "embedding":  r["embedding"],          # list of 512 floats
            "bbox": {
                "x": region.get("x", 0),
                "y": region.get("y", 0),
                "w": region.get("w", 0),
                "h": region.get("h", 0),
            },
            "confidence": r.get("face_confidence", 1.0),
        })
    return faces


def find_or_create_identity(embedding: list[float]) -> tuple[FaceIdentity, bool]:
    """
    Given a 512-d embedding, search pgvector for the nearest existing identity.

    - If cosine distance < threshold  →  return that identity (is_new=False)
    - Otherwise                       →  create new FaceIdentity (is_new=True)

    Uses pgvector's <=> operator (cosine distance) directly in SQL for speed.
    """
    threshold = _threshold()
    vec_str   = _to_pgvector_literal(embedding)

    # pgvector cosine distance: 0 = identical, 2 = opposite
    row = db.session.execute(
        text(f"""
            SELECT grab_id,
                   embedding <=> '{vec_str}'::vector AS distance
            FROM   face_identities
            ORDER  BY distance
            LIMIT  1
        """)
    ).fetchone()

    if row and row.distance < threshold:
        identity = db.session.get(FaceIdentity, row.grab_id)
        return identity, False

    # No close match → new identity
    identity = FaceIdentity(embedding=embedding)
    db.session.add(identity)
    db.session.flush()   # get grab_id assigned without committing yet
    return identity, True


def match_selfie(embedding: list[float]) -> dict | None:
    """
    Search all known grab_ids for the closest match to the selfie embedding.

    Returns { "grab_id": str, "confidence": float } or None if no match.
    confidence is mapped from distance: 1.0 = perfect match, 0.0 = no match.
    """
    threshold = _threshold()
    vec_str   = _to_pgvector_literal(embedding)

    row = db.session.execute(
        text(f"""
            SELECT grab_id,
                   embedding <=> '{vec_str}'::vector AS distance
            FROM   face_identities
            ORDER  BY distance
            LIMIT  1
        """)
    ).fetchone()

    if row is None or row.distance >= threshold:
        return None

    # Convert distance (0–2 range for cosine) to a 0–1 confidence score
    confidence = round(1 - (row.distance / 2), 4)
    return {"grab_id": str(row.grab_id), "confidence": confidence}


# ── Internal ──────────────────────────────────────────────────────────────────

def _to_pgvector_literal(embedding: list[float]) -> str:
    """Converts a Python list of floats to the '[0.1,0.2,...]' string pgvector expects."""
    return "[" + ",".join(str(round(v, 8)) for v in embedding) + "]"
