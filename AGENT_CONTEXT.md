# Grabpic — Agent Context Document

> Full implementation context for continuity across agents.  
> Read this entirely before writing or modifying any code.

---

## 1. What This Project Is

**Grabpic** is a Python/Flask REST API backend for a facial recognition photo retrieval system built for Vyrothon 2026. The concept: at a large event (e.g. a marathon with 50,000 photos), an admin crawls a photo directory, every unique face is automatically assigned a UUID called a `grab_id`, and attendees can retrieve all their photos by submitting a selfie ("Selfie as a Key").

There is **no frontend**. This is a pure backend API.

---

## 2. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Web framework | **Flask 3.x** | Lightweight, fast to build pure REST APIs, no template overhead |
| ORM | **Flask-SQLAlchemy** + Flask-Migrate (Alembic) | Standard SQLAlchemy with migration support |
| Database | **PostgreSQL 16** with **pgvector** extension | Native vector similarity search, no external vector DB needed |
| Face recognition | **DeepFace** library, **ArcFace** model, **RetinaFace** detector | ArcFace produces 512-d embeddings with state-of-the-art accuracy; RetinaFace handles varied angles |
| Auth | **Flask-JWT-Extended** | Stateless JWT tokens, 24h expiry by default |
| API docs | **Flasgger** (Swagger UI at `/apidocs`) | Free, inline docstring-based, zero config |
| Image processing | **Pillow** | Thumbnail generation |
| Production server | **Gunicorn** | 2 workers, 120s timeout |
| Deployment | **Railway** | Free $5/month credit, supports pgvector Postgres natively, no sleep on inactivity |
| Local dev DB | **Docker Compose** using `pgvector/pgvector:pg16` image | pgvector pre-installed, no manual extension compilation |

---

## 3. Complete File Structure

```
grabpic/
├── run.py                          # App entry point + /health endpoint
├── start.sh                        # Production startup: migrations → pgvector → gunicorn
├── Dockerfile                      # Two-stage: downloads ArcFace weights, then builds app
├── docker-compose.yml              # Local dev: PostgreSQL 16 + pgvector only
├── railway.toml                    # Railway deployment config
├── requirements.txt
├── .env.example
├── .gitignore
├── .dockerignore
├── PRD.md                          # Product requirements document
├── DEPLOY.md                       # Step-by-step Railway deployment guide
│
├── storage/                        # Event photos go here (mounted as Railway volume in prod)
│   └── .gitkeep
│
├── migrations/
│   └── manual_extras.sql           # Run AFTER flask db upgrade: IVFFlat index + crawl_jobs table
│
└── app/
    ├── __init__.py                 # Flask app factory
    ├── config.py                   # DevelopmentConfig / ProductionConfig
    ├── extensions.py               # db, migrate, jwt — initialized here to avoid circular imports
    │
    ├── models/
    │   └── __init__.py             # FaceIdentity, Image, ImageFace models
    │
    ├── routes/
    │   ├── __init__.py
    │   ├── admin.py                # Blueprint: /api/v1/admin/*
    │   ├── auth.py                 # Blueprint: /api/v1/auth/*
    │   └── images.py               # Blueprint: /api/v1/images/*
    │
    ├── services/
    │   ├── __init__.py
    │   ├── face_engine.py          # DeepFace wrapper: extract, match, find_or_create
    │   └── crawler.py              # Storage crawl: parallel extraction, DB-backed jobs
    │
    └── utils/
        ├── __init__.py
        ├── response.py             # ok() / err() — standardized JSON response helpers
        └── auth.py                 # @require_admin decorator
```

---

## 4. Database Schema

### Tables managed by Flask-Migrate (SQLAlchemy models)

**`face_identities`**
```sql
grab_id    UUID  PRIMARY KEY  DEFAULT gen_random_uuid()
embedding  vector(512)        NOT NULL      -- pgvector column, ArcFace 512-d
created_at TIMESTAMP          DEFAULT NOW()
```

**`images`**
```sql
image_id    UUID  PRIMARY KEY  DEFAULT gen_random_uuid()
file_path   TEXT  UNIQUE  NOT NULL    -- relative path from STORAGE_PATH root
file_name   TEXT  NOT NULL
ingested_at TIMESTAMP  DEFAULT NOW()
```

**`image_faces`** (many-to-many join)
```sql
id          SERIAL  PRIMARY KEY
image_id    UUID  REFERENCES images(image_id)          ON DELETE CASCADE
grab_id     UUID  REFERENCES face_identities(grab_id)  ON DELETE CASCADE
bbox        JSONB       -- {"x": int, "y": int, "w": int, "h": int}
confidence  FLOAT
UNIQUE(image_id, grab_id)
```

### Tables created by `migrations/manual_extras.sql`

**`crawl_jobs`** — DB-backed job tracking (replaces in-memory dict for multi-worker safety)
```sql
job_id            TEXT  PRIMARY KEY
status            TEXT  DEFAULT 'running'   -- 'running' | 'completed' | 'failed'
storage_path      TEXT
images_processed  INTEGER  DEFAULT 0
images_total      INTEGER  DEFAULT 0
faces_discovered  INTEGER  DEFAULT 0
unique_identities INTEGER  DEFAULT 0
errors            JSONB    DEFAULT '[]'
started_at        TIMESTAMP WITH TIME ZONE
completed_at      TIMESTAMP WITH TIME ZONE
```

### Indexes created by `manual_extras.sql`
```sql
-- Critical for fast ANN similarity search. Without this, every selfie auth is O(n) full scan.
CREATE INDEX face_identities_embedding_idx
    ON face_identities USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Fast lookup: "all images for this grab_id"
CREATE INDEX image_faces_grab_id_idx ON image_faces (grab_id);
CREATE INDEX image_faces_image_id_idx ON image_faces (image_id);
```

---

## 5. Environment Variables

```env
FLASK_ENV=development              # or 'production'
SECRET_KEY=                        # Flask secret key
JWT_SECRET_KEY=                    # separate key for JWT signing
JWT_EXPIRY_HOURS=24

DATABASE_URL=postgresql://grabpic:grabpic@localhost:5432/grabpic

STORAGE_PATH=./storage             # root dir for event images; /app/storage in prod
ADMIN_API_KEY=admin-secret         # passed as X-Admin-Key header to admin endpoints

FACE_MODEL=ArcFace                 # DeepFace model name
FACE_DETECTOR=retinaface           # DeepFace detector backend
FACE_SIMILARITY_THRESHOLD=0.40     # cosine distance threshold; lower = stricter matching
```

In production on Railway, `DATABASE_URL` is auto-injected from the linked PostgreSQL service.

---

## 6. API Endpoints

Base path: `/api/v1`

All endpoints return:
```json
{ "success": bool, "data": { ... } | null, "error": "string" | null }
```

### Health (no auth)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok"}`. Used by Railway to confirm app is alive. |

### Admin (requires `X-Admin-Key` header)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/admin/crawl` | Triggers crawl of storage directory. Returns `job_id`. Non-blocking. |
| GET | `/api/v1/admin/crawl/status/<job_id>` | Polls crawl job progress from DB. |
| GET | `/api/v1/admin/stats` | Total images, faces, unique identities in system. |

**POST /admin/crawl body:**
```json
{ "storage_path": "/optional/override", "force_reindex": false }
```

**GET /admin/crawl/status response:**
```json
{
  "job_id": "uuid",
  "status": "running",
  "images_processed": 1200, "images_total": 50000,
  "faces_discovered": 3400, "unique_identities": 487,
  "errors": [], "started_at": "...", "completed_at": null
}
```

### Auth (no auth required)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/selfie` | `multipart/form-data` with `selfie` file field. Returns `grab_id` + JWT `token`. |

**POST /auth/selfie success response:**
```json
{ "matched": true, "grab_id": "uuid", "confidence": 0.92, "token": "eyJ..." }
```

**POST /auth/selfie no match:**
```json
{ "matched": false, "grab_id": null, "message": "No matching identity found..." }
```

**POST /auth/selfie errors (400):** no face detected, multiple faces detected, unsupported file type.

### Images (requires `Authorization: Bearer <token>` header)

The JWT encodes the user's `grab_id`. All image endpoints enforce that the authenticated `grab_id` must appear in the requested image.

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/images` | Paginated list of all images containing the user's face. |
| GET | `/api/v1/images/<image_id>` | Metadata for one image including all `grab_id`s in it. |
| GET | `/api/v1/images/<image_id>/file` | Streams raw image binary (`image/jpeg`). |
| GET | `/api/v1/images/<image_id>/thumbnail` | Streams 300×300 JPEG thumbnail. Cached to disk on first call. |

**GET /images query params:** `page` (default 1), `per_page` (default 20, max 100)

**GET /images response:**
```json
{
  "grab_id": "uuid", "total": 47, "page": 1, "per_page": 20,
  "images": [
    {
      "image_id": "uuid", "file_name": "DSC_0421.jpg",
      "url": "/api/v1/images/uuid/file",
      "thumbnail_url": "/api/v1/images/uuid/thumbnail",
      "face_bbox": {"x": 120, "y": 45, "w": 80, "h": 95},
      "confidence": 0.94, "ingested_at": "2026-04-18T09:30:00"
    }
  ]
}
```

---

## 7. How the Face Engine Works

**File:** `app/services/face_engine.py`

Three public functions:

### `extract_faces(image_path) → list[dict]`
Calls `DeepFace.represent()` with ArcFace model and RetinaFace detector. Returns one dict per face found in the image:
```python
{ "embedding": [float * 512], "bbox": {"x", "y", "w", "h"}, "confidence": float }
```
Returns `[]` (empty list, no raise) if no faces detected. DeepFace raises `ValueError` on no-face which is caught internally.

### `find_or_create_identity(embedding) → (FaceIdentity, is_new: bool)`
Used during crawl. Runs a pgvector cosine distance query against all existing embeddings:
```sql
SELECT grab_id, embedding <=> '[...]'::vector AS distance
FROM face_identities ORDER BY distance LIMIT 1
```
If `distance < FACE_SIMILARITY_THRESHOLD` (default 0.40) → returns existing identity.
Otherwise → creates and flushes a new `FaceIdentity` row.

### `match_selfie(embedding) → dict | None`
Used during selfie auth. Same pgvector query. Returns `{"grab_id": str, "confidence": float}` or `None`. Confidence is derived as `1 - (distance / 2)` to map from cosine distance range (0–2) to a 0–1 scale.

**pgvector distance note:** The `<=>` operator returns cosine *distance* (not similarity). Range is 0 (identical) to 2 (opposite). A threshold of 0.40 means faces must be at least 80% similar (as cosine similarity).

---

## 8. How the Crawler Works

**File:** `app/services/crawler.py`

**Design constraints:**
- Must not block the HTTP request — runs in a background thread
- Must work across multiple gunicorn workers — job state is in the DB (`crawl_jobs` table), not in memory
- DeepFace is CPU-heavy — face extraction runs in a `ThreadPoolExecutor` (4 workers by default)
- SQLAlchemy sessions are not thread-safe — DB writes happen only in the main thread

**Flow:**
1. `start_crawl()` inserts a row into `crawl_jobs`, starts a daemon thread, returns `job_id`
2. Thread discovers all images in `STORAGE_PATH` (recursively, matching extensions)
3. `ThreadPoolExecutor` runs `_extract_one()` in parallel — this only calls DeepFace, no DB
4. Results accumulate in a batch list. Every 50 images (`BATCH_SIZE`), `_flush_batch()` runs in the main thread, writes to DB, and does atomic `UPDATE` on `crawl_jobs` counters
5. On completion, sets `status = 'completed'`

**Supported extensions:** `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`

---

## 9. Auth Flow

1. Admin crawls storage → `face_identities` table populated with `grab_id` + `embedding` pairs
2. User POSTs selfie to `/auth/selfie`
3. Server saves selfie to a temp file (DeepFace needs a file path, not bytes)
4. `extract_faces()` extracts embedding from selfie
5. If 0 faces → return `matched: false`. If >1 faces → return 400 error
6. `match_selfie()` queries pgvector → returns nearest `grab_id`
7. `create_access_token(identity=grab_id)` issues JWT
8. All subsequent requests carry this JWT; `get_jwt_identity()` extracts the `grab_id`
9. Image endpoints verify the `grab_id` from JWT matches an `ImageFace` row for the requested image

---

## 10. Deployment (Railway)

**Platform:** Railway — chosen because it supports pgvector on managed PostgreSQL (most free platforms don't), has no sleep-on-inactivity (unlike Render free tier), and deploys directly from GitHub.

### Dockerfile (two-stage build)
- **Stage 1 (`model-downloader`):** Installs DeepFace and pre-downloads ArcFace weights (~500MB) into `/root/.deepface`. This bakes the weights into the image layer so the live server never hits a cold-start download.
- **Stage 2:** Production image. Copies weights from Stage 1, installs system deps for OpenCV (`libgl1`, `libglib2.0-0`, `libgomp1`), installs Python deps, copies app code.
- **CMD:** Runs `start.sh`

### start.sh (runs on every deploy before gunicorn)
```
flask db upgrade
→ CREATE EXTENSION IF NOT EXISTS vector
→ Run migrations/manual_extras.sql (IVFFlat index, crawl_jobs table — idempotent)
→ exec gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

### Railway services needed
1. **Flask app service** — deploy from GitHub repo, uses Dockerfile
2. **PostgreSQL service** — add via Railway dashboard (includes pgvector). `DATABASE_URL` is auto-injected.
3. **Volume** — mount at `/app/storage` for persistent image storage across deploys

### Environment variables to set on Railway
```
SECRET_KEY, JWT_SECRET_KEY, ADMIN_API_KEY, FLASK_ENV=production,
STORAGE_PATH=/app/storage, FACE_MODEL=ArcFace,
FACE_DETECTOR=retinaface, FACE_SIMILARITY_THRESHOLD=0.40
```
`DATABASE_URL` and `PORT` are auto-injected by Railway — do not set manually.

### Public URL
Railway provides: `https://<project>.up.railway.app`  
Swagger UI at: `https://<project>.up.railway.app/apidocs`

---

## 11. Local Development Setup

```bash
# 1. Start PostgreSQL with pgvector
docker compose up -d

# 2. Python environment
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env

# 4. Initialize DB (run once)
flask --app run.py db init
flask --app run.py db migrate -m "initial"
flask --app run.py db upgrade

# 5. Enable pgvector + run manual extras (run once)
docker exec -it grabpic_db psql -U grabpic -d grabpic -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec -it grabpic_db psql -U grabpic -d grabpic -f /dev/stdin < migrations/manual_extras.sql

# 6. Run
python run.py
# → http://localhost:5000
# → http://localhost:5000/apidocs
```

---

## 12. Known Issues & Things to Fix

### Bug: Duplicate page/per_page computation in `images.py`
In `app/routes/images.py`, the `list_images()` function computes `page` and `per_page` twice — once with dead code and once correctly. Lines 37–43 should be cleaned up to just:
```python
page     = _int_arg("page", 1)
per_page = min(_int_arg("per_page", 20), 100)
```

### Bug: Wrong relative import in `app/models/__init__.py`
The models file has:
```python
from .extensions import db
```
This looks for `app/models/extensions.py` which does not exist. It must be:
```python
from ..extensions import db
```

### Not yet implemented
- **Image upload endpoint** — there is no endpoint to upload photos to `/storage`. For a demo, either: (a) put test images in `storage/` in the repo and remove the `.gitignore` exclusion, or (b) add a `POST /api/v1/admin/upload` endpoint that accepts `multipart/form-data` and saves files to `STORAGE_PATH`.
- **Rate limiting** on `/auth/selfie` — no protection against brute-force face submission.
- **Unit tests** — `tests/` directory exists but is empty.
- **Thumbnail cache invalidation** — thumbnails in `storage/.thumbnails/` are never purged.

---

## 13. Key Design Decisions (Rationale)

| Decision | Why |
|---|---|
| Flask over Django | Pure REST API, no templates needed; Flask + SQLAlchemy is less overhead and faster to build |
| ArcFace over `face_recognition` (dlib) | 512-d embeddings, state-of-the-art accuracy, GPU-capable; dlib is CPU-only and less accurate |
| RetinaFace detector | Best detection quality at varied angles and lighting vs alternatives (mtcnn, opencv) |
| pgvector over external vector DB | No extra service to manage; `<=>` cosine operator in SQL is fast enough for hackathon scale |
| IVFFlat index (lists=100) | Approximate nearest neighbor search, O(√n) instead of O(n); required for >1k faces |
| DB-backed crawl jobs | In-memory dict breaks with multiple gunicorn workers; DB row is visible to all workers |
| ThreadPoolExecutor for crawl | DeepFace is CPU-bound; parallel threads speed up large photo sets significantly |
| DB writes in main thread only | SQLAlchemy sessions are not thread-safe; only CPU work runs in threads |
| Two-stage Dockerfile | Baking ArcFace weights (~500MB) into the image layer avoids 2-minute cold start on live server |
| Thumbnails cached to disk | Avoids re-decoding and re-encoding original images on every thumbnail request |
| Cosine distance threshold 0.40 | Means faces must have cosine similarity ≥ 0.80 to be considered the same person; adjustable via env var |
| JWT identity = grab_id | Stateless; server doesn't need a session store; grab_id is extracted directly from token on every request |

---

## 14. requirements.txt (exact)

```
flask>=3.0
flask-sqlalchemy>=3.1
flask-migrate>=4.0
flask-jwt-extended>=4.6
flasgger>=0.9.7
psycopg2-binary>=2.9
pgvector>=0.3.0
deepface>=0.0.93
pillow>=10.0
python-dotenv>=1.0
gunicorn>=21.0
pytest>=8.0
pytest-flask>=1.3
```

---

## 15. Judging Criteria Coverage

| Criterion | Weight | How it's covered |
|---|---|---|
| Working APIs | 25% | All endpoints functional with proper HTTP status codes |
| Face-to-ID transformation | 20% | DeepFace ArcFace embeddings → pgvector dedup → `grab_id` |
| Selfie Auth | 15% | `POST /auth/selfie` → pgvector nearest neighbor → JWT |
| API Structure & Error Handling | 15% | Consistent `{success, data, error}` envelope on all responses |
| Multiple faces per image | 10% | `image_faces` join table — one image maps to many `grab_id`s |
| Problem Judgement | 10% | IVFFlat index, batch commits, parallel crawl, threshold tuning |
| Docs & Design | 5% | Swagger UI at `/apidocs`, PRD.md, README.md, DEPLOY.md |
