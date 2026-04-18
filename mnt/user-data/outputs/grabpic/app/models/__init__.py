import uuid
from datetime import datetime
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .extensions import db


class FaceIdentity(db.Model):
    """
    One row per unique face discovered during crawl.
    grab_id is the stable identifier users get back from selfie auth.
    embedding is a 512-d ArcFace vector stored natively by pgvector.
    """
    __tablename__ = "face_identities"

    grab_id    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    embedding  = db.Column(Vector(512), nullable=False)   # pgvector column
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # back-reference to all images this identity appears in
    image_faces = db.relationship("ImageFace", back_populates="face_identity",
                                  cascade="all, delete-orphan")


class Image(db.Model):
    """
    One row per raw image file ingested from storage.
    """
    __tablename__ = "images"

    image_id    = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_path   = db.Column(db.Text, nullable=False, unique=True)  # relative to STORAGE_PATH
    file_name   = db.Column(db.Text, nullable=False)
    ingested_at = db.Column(db.DateTime, default=datetime.utcnow)

    image_faces = db.relationship("ImageFace", back_populates="image",
                                  cascade="all, delete-orphan")

    def to_dict(self, face_entry=None):
        d = {
            "image_id":    str(self.image_id),
            "file_name":   self.file_name,
            "url":         f"/api/v1/images/{self.image_id}/file",
            "thumbnail_url": f"/api/v1/images/{self.image_id}/thumbnail",
            "ingested_at": self.ingested_at.isoformat(),
        }
        if face_entry:
            d["face_bbox"]   = face_entry.bbox
            d["confidence"]  = face_entry.confidence
        return d


class ImageFace(db.Model):
    """
    Join table: one image contains many faces (grab_ids),
    one grab_id appears in many images.
    Also stores the bounding box of this face in this specific image.
    """
    __tablename__ = "image_faces"

    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    image_id   = db.Column(UUID(as_uuid=True), db.ForeignKey("images.image_id",
                            ondelete="CASCADE"), nullable=False)
    grab_id    = db.Column(UUID(as_uuid=True), db.ForeignKey("face_identities.grab_id",
                            ondelete="CASCADE"), nullable=False)
    bbox       = db.Column(JSONB)    # {"x": 120, "y": 45, "w": 80, "h": 95}
    confidence = db.Column(db.Float)

    __table_args__ = (db.UniqueConstraint("image_id", "grab_id"),)

    image         = db.relationship("Image", back_populates="image_faces")
    face_identity = db.relationship("FaceIdentity", back_populates="image_faces")
