-- Run this AFTER flask db upgrade
-- It adds two things the auto-migration won't generate:
--   1. crawl_jobs table (for DB-backed job tracking)
--   2. IVFFlat index on face embeddings (critical for fast similarity search at scale)

-- Job tracking table (replaces in-memory dict)
CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id            TEXT PRIMARY KEY,
    status            TEXT NOT NULL DEFAULT 'running',   -- running | completed | failed
    storage_path      TEXT,
    images_processed  INTEGER DEFAULT 0,
    images_total      INTEGER DEFAULT 0,
    faces_discovered  INTEGER DEFAULT 0,
    unique_identities INTEGER DEFAULT 0,
    errors            JSONB DEFAULT '[]'::jsonb,
    started_at        TIMESTAMP WITH TIME ZONE,
    completed_at      TIMESTAMP WITH TIME ZONE
);

-- IVFFlat index for fast approximate nearest-neighbor search on embeddings.
-- Without this, every selfie auth does a full sequential scan of ALL embeddings.
-- With it, search is O(sqrt(n)) instead of O(n).
--
-- lists = 100 is a good starting point for up to ~1M vectors.
-- Rule of thumb: lists ≈ sqrt(total_rows). Re-create and tune as data grows.
--
-- NOTE: The index must be created AFTER data is loaded for best quality.
-- It can be created on an empty table but will be less effective.
CREATE INDEX IF NOT EXISTS face_identities_embedding_idx
    ON face_identities
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Also index the join table for fast "give me all images for this grab_id" queries
CREATE INDEX IF NOT EXISTS image_faces_grab_id_idx ON image_faces (grab_id);
CREATE INDEX IF NOT EXISTS image_faces_image_id_idx ON image_faces (image_id);
