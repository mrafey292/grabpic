# Grabpic

Intelligent facial recognition backend for large-scale event photo retrieval.

**Live Demo (Railway):** [https://grabpic-production-4904.up.railway.app/](https://grabpic-production-4904.up.railway.app/)

Stack: **Flask · DeepFace (ArcFace) · PostgreSQL + pgvector**

> [!TIP]
> **Default Admin API Key**: When testing endpoints in the Swagger UI (at `/apidocs` or the root URL), click the "Authorize" button and enter `admin-secret` to authenticate admin routes like `/upload` and `/crawl`.

---

## Features

- **Fast & Accurate Face Matching:** Uses DeepFace (ArcFace) for extracting highly accurate facial embeddings.
- **Vector Database Native:** Embeddings are stored directly in PostgreSQL using pgvector, enabling blazing-fast similarity searches using cosine distance.
- **Event Photo Crawling:** Crawl storage directories to automatically detect, extract, and index all faces in photos.
- **Admin Upload Endpoint:** Allows you to upload event photos via API.
- **Selfie Authentication:** Users upload a selfie, which grants them a JWT to fetch exclusively their photos.

---

## Prerequisites

- Python 3.11+
- Git
- Docker + Docker Compose (for running the PostgreSQL + pgvector instance)

---

## Setup & Local Development

### 1. Clone & Enter the Repo
```bash
git clone <your-repo-url>
cd grabpic
```

### 2. Start PostgreSQL with pgvector
```bash
docker compose up -d
```
This spins up Postgres 16 with pgvector pre-installed and exposes it on port 5432.

### 3. Create & Activate Virtual Environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```
> **Note:** DeepFace will download the ArcFace model weights (~500MB) on the very first run.

### 5. Configure Environment Variables
```bash
cp .env.example .env
```
_Edit `.env` if needed — the defaults work out of the box with the docker-compose DB._

### 6. Initialize Database & Run Server
To apply migrations, set up pgvector, and start the application locally:
```bash
bash start.sh
```
Or to run the local Flask dev server (after `start.sh` has run once for migrations):
```bash
python run.py
```

The API will be live at: `http://localhost:5000`
Swagger documentation is available at: `http://localhost:5000/apidocs`

---

## Project Structure

```
grabpic/
├── app/
│   ├── __init__.py         # Flask app factory
│   ├── config.py           # Settings and Environment Variables
│   ├── extensions.py       # db, jwt, migrate
│   ├── models/             # SQLAlchemy Models (schema definitions)
│   ├── routes/             # Blueprints: admin, auth, images
│   ├── services/           # Business logic: crawler, face_engine
│   └── utils/              # Helpers for response formatting and auth decorators
├── migrations/             # Alembic database migrations & manual db setup scripts 
├── storage/                # Drop event photos here
├── Dockerfile              # Docker image declaration
├── docker-compose.yml      # Local Postgres + pgvector setup
├── railway.toml            # Railway CI/CD builder configuration
├── start.sh                # Startup script (handles migrations and pgvector indexing)
└── run.py                  # Local entrypoint wrapper
```

---

## API Usage (cURLs)

### 1. Upload Event Photos (Admin)
Upload images to the server dynamically:
```bash
curl -X POST http://localhost:5000/api/v1/admin/upload \
  -H "X-Admin-Key: admin-secret" \
  -F "photos=@/path/to/group_photo1.jpg" \
  -F "photos=@/path/to/group_photo2.png"
```

### 2. Crawl & Index Photos (Admin)
Processes new images uploaded to the `storage/` directory, extracts faces, and creates vector embeddings:
```bash
curl -X POST http://localhost:5000/api/v1/admin/crawl \
  -H "X-Admin-Key: admin-secret" \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": false}'
```

### 3. Check Crawl Status (Admin)
```bash
curl http://localhost:5000/api/v1/admin/crawl/status/<job_id> \
  -H "X-Admin-Key: admin-secret"
```

### 4. Authenticate with Selfie (User)
```bash
curl -X POST http://localhost:5000/api/v1/auth/selfie \
  -F "selfie=@/path/to/your/selfie.jpg"
```
_Response includes a `token` (JWT) and your `grab_id`._

### 5. Get Your Photos (User)
```bash
curl http://localhost:5000/api/v1/images \
  -H "Authorization: Bearer <token>"
```

### 6. Download a Found Photo (User)
```bash
curl http://localhost:5000/api/v1/images/<image_id>/file \
  -H "Authorization: Bearer <token>" \
  --output my_awesome_photo.jpg
```

---

## How pgvector Works

`pgvector` is a robust PostgreSQL extension adding a native `vector` column type and extremely fast similarity search operators natively in the relational DB. No external vector database needed!

```sql
-- Example: Store an embedding
INSERT INTO face_identities (embedding) VALUES ('[0.12, -0.34, ...]'::vector);

-- Example: Find closest match using cosine distance (<=>)
SELECT grab_id, embedding <=> '[0.11, -0.33, ...]'::vector AS distance
FROM face_identities
ORDER BY distance
LIMIT 1;
```
> **Note:** A distance of `0` means identical faces. In the application, we treat any distance below `0.40` (configurable via `FACE_SIMILARITY_THRESHOLD`) as a match for the same person.

---

## Deployment 

See [DEPLOY.md](DEPLOY.md) for detailed instructions on deploying the application to Railway automatically from GitHub.
