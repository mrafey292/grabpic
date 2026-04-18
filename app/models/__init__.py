"""
ORM models for Grabpic.

Tables:
  - face_identities  — one row per unique person (grab_id + 512-d embedding)
  - images           — one row per photo file crawled from storage
  - image_faces      — many-to-many join: which grab_ids appear in which images
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector

from ..extensions import db


class FaceIdentity(db.Model):
    __tablename__ = "face_identities"

    grab_id = db.Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    embedding = db.Column(Vector(512), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # relationship back to image_faces
    image_faces = db.relationship(
        "ImageFace", back_populates="identity", lazy="dynamic"
    )

    def __repr__(self):
        return f"<FaceIdentity {self.grab_id}>"


class Image(db.Model):
    __tablename__ = "images"

    image_id = db.Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_path = db.Column(db.Text, unique=True, nullable=False)
    file_name = db.Column(db.Text, nullable=False)
    ingested_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # relationship back to image_faces
    image_faces = db.relationship(
        "ImageFace", back_populates="image", lazy="dynamic"
    )

    def to_dict(self, face_entry=None):
        d = {
            "image_id": str(self.image_id),
            "file_name": self.file_name,
            "url": f"/api/v1/images/{self.image_id}/file",
            "thumbnail_url": f"/api/v1/images/{self.image_id}/thumbnail",
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
        }
        if face_entry:
            d["face_bbox"] = face_entry.bbox
            d["confidence"] = face_entry.confidence
        return d

    def __repr__(self):
        return f"<Image {self.file_name}>"


class ImageFace(db.Model):
    __tablename__ = "image_faces"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    image_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("images.image_id", ondelete="CASCADE"),
        nullable=False,
    )
    grab_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("face_identities.grab_id", ondelete="CASCADE"),
        nullable=False,
    )
    bbox = db.Column(JSONB)
    confidence = db.Column(db.Float)

    __table_args__ = (
        db.UniqueConstraint("image_id", "grab_id", name="uq_image_face"),
    )

    # relationships
    image = db.relationship("Image", back_populates="image_faces")
    identity = db.relationship("FaceIdentity", back_populates="image_faces")

    def __repr__(self):
        return f"<ImageFace image={self.image_id} grab={self.grab_id}>"
