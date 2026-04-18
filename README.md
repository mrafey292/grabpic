# Grabpic

Intelligent facial recognition backend for large-scale event photo retrieval.  
Stack: **Flask · DeepFace (ArcFace) · PostgreSQL + pgvector**

---

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Git

---

## Setup

### 1. Clone & enter the repo
```bash
git clone <your-repo-url>
cd grabpic
```

### 2. Start PostgreSQL with pgvector
```bash
docker compose up -d
```
This spins up Postgres 16 with pgvector pre-installed. No extra setup needed.

### 3. Create and activate virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```
> Note: DeepFace will download ArcFace model weights (~500MB) on first run.

### 5. Configure environment
```bash
cp .env.example .env
# Edit .env if needed — defaults work out of the box with docker compose
```

### 6. Initialize the database
```bash
flask --app run.py db init      # only first time
flask --app run.py db migrate -m "initial"
flask --app run.py db upgrade
```

### 7. Enable pgvector extension
```bash
docker exec -it grabpic_db psql -U grabpic -d grabpic -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 8. Run the server
```bash
python run.py
```
API is live at `http://localhost:5000`  
Swagger docs at `http://localhost:5000/apidocs`

---

## Add Event Photos

Drop your event images into the `./storage/` directory:
```bash
cp /path/to/marathon/photos/* ./storage/
```

---

## API Usage (cURLs)

### Crawl & Index Storage
```bash
curl -X POST http://localhost:5000/api/v1/admin/crawl \
  -H "X-Admin-Key: admin-secret" \
  -H "Content-Type: application/json" \
  -d '{"force_reindex": false}'
```

### Poll Crawl Status
```bash
curl http://localhost:5000/api/v1/admin/crawl/status/<job_id> \
  -H "X-Admin-Key: admin-secret"
```

### Get System Stats
```bash
curl http://localhost:5000/api/v1/admin/stats \
  -H "X-Admin-Key: admin-secret"
```

### Authenticate with Selfie
```bash
curl -X POST http://localhost:5000/api/v1/auth/selfie \
  -F "selfie=@/path/to/your/selfie.jpg"
```
Response includes a `token` (JWT) and your `grab_id`.

### Get Your Photos
```bash
curl http://localhost:5000/api/v1/images \
  -H "Authorization: Bearer <token>"
```

### Get a Specific Image (metadata)
```bash
curl http://localhost:5000/api/v1/images/<image_id> \
  -H "Authorization: Bearer <token>"
```

### Download a Photo
```bash
curl http://localhost:5000/api/v1/images/<image_id>/file \
  -H "Authorization: Bearer <token>" \
  --output photo.jpg
```

### Download a Thumbnail
```bash
curl http://localhost:5000/api/v1/images/<image_id>/thumbnail \
  -H "Authorization: Bearer <token>" \
  --output thumb.jpg
```

---

## How pgvector Works

pgvector is a PostgreSQL extension that adds a native `vector` column type and fast similarity search operators. No external vector database needed.

```sql
-- Store an embedding
INSERT INTO face_identities (embedding) VALUES ('[0.12, -0.34, ...]'::vector);

-- Find closest match using cosine distance (<=>)
SELECT grab_id, embedding <=> '[0.11, -0.33, ...]'::vector AS distance
FROM face_identities
ORDER BY distance
LIMIT 1;
```

Distance of `0` = identical faces. We treat anything below `0.40` as the same person.

---

## Project Structure

```
grabpic/
├── app/
│   ├── __init__.py         # Flask app factory
│   ├── config.py
│   ├── extensions.py       # db, jwt, migrate
│   ├── models/             # SQLAlchemy models
│   ├── routes/             # Blueprints: admin, auth, images
│   ├── services/           # face_engine.py, crawler.py
│   └── utils/              # response helpers, auth decorators
├── storage/                # Drop event photos here
├── tests/
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── run.py
└── PRD.md
```
