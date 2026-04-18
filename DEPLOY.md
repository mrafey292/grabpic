# Deployment Guide — Railway

## Why Railway

- Supports PostgreSQL with pgvector natively (most free platforms don't)
- No sleep on inactivity (unlike Render free tier — bad for demos)
- Deploys directly from GitHub
- $5 free credit/month — plenty for a hackathon

---

## Step 1 — Push your code to GitHub

```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/<you>/grabpic.git
git push -u origin main
```

---

## Step 2 — Create a Railway account

Go to https://railway.app and sign up with GitHub. No credit card needed for the free tier.

---

## Step 3 — Create a new project

1. Click **New Project**
2. Select **Deploy from GitHub repo**
3. Choose your `grabpic` repo
4. Railway detects the Dockerfile automatically — click **Deploy**

It will start building. The first build takes ~10 minutes (downloading ArcFace weights into the image). Subsequent deploys are fast because Docker caches the weight layer.

---

## Step 4 — Add PostgreSQL with pgvector

In your Railway project dashboard:

1. Click **+ New** → **Database** → **Add PostgreSQL**
2. Once it provisions, click the Postgres service
3. Go to **Variables** tab — copy the `DATABASE_URL` value

---

## Step 5 — Set environment variables

In your Flask service on Railway, go to **Variables** and add:

| Variable | Value |
|---|---|
| `DATABASE_URL` | *(paste from Postgres service — Railway may auto-inject this)* |
| `SECRET_KEY` | any long random string |
| `JWT_SECRET_KEY` | any different long random string |
| `ADMIN_API_KEY` | your chosen admin password |
| `FLASK_ENV` | `production` |
| `STORAGE_PATH` | `/app/storage` |
| `FACE_MODEL` | `ArcFace` |
| `FACE_DETECTOR` | `retinaface` |
| `FACE_SIMILARITY_THRESHOLD` | `0.40` |

> **Tip:** Railway auto-injects `DATABASE_URL` from the linked Postgres service.
> Check if it's already there before adding it manually.

---

## Step 6 — Add a persistent volume for image storage

Without a volume, your uploaded images are wiped on every redeploy.

1. In your Flask service, go to **Volumes**
2. Click **Add Volume**
3. Mount path: `/app/storage`
4. This volume persists across deploys and restarts

---

## Step 7 — Redeploy

After setting variables, click **Redeploy**. The `start.sh` script runs automatically and:
- Applies DB migrations
- Enables pgvector extension
- Creates the IVFFlat index and crawl_jobs table
- Starts gunicorn

---

## Step 8 — Get your public URL

Railway assigns a URL like `https://grabpic-production.up.railway.app`.  
Find it under your service → **Settings** → **Networking** → **Public URL**.

---

## Step 9 — Verify it's working

```bash
# Health check
curl https://your-app.up.railway.app/health
# Expected: {"status": "ok"}

# Swagger docs
open https://your-app.up.railway.app/apidocs
```

---

## Step 10 — Upload images and test end-to-end

```bash
BASE=https://your-app.up.railway.app

# 1. Trigger crawl (images must be in /app/storage volume)
curl -X POST $BASE/api/v1/admin/crawl \
  -H "X-Admin-Key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{}'

# 2. Poll crawl status
curl $BASE/api/v1/admin/crawl/status/<job_id> \
  -H "X-Admin-Key: your-admin-key"

# 3. Auth with selfie
curl -X POST $BASE/api/v1/auth/selfie \
  -F "selfie=@/path/to/selfie.jpg"

# 4. Get your photos
curl $BASE/api/v1/images \
  -H "Authorization: Bearer <token_from_step_3>"
```

---

## Uploading images to the Railway volume

Railway volumes don't have a file browser UI. Options:

**Option A — Upload via a temporary endpoint (easiest for demo)**

Add a quick admin endpoint that accepts multipart image uploads and saves them to `STORAGE_PATH`. Then call `/admin/crawl` after uploading.

**Option B — Railway CLI**

```bash
npm install -g @railway/cli
railway login
railway shell   # opens a shell into your running container
# then use scp or curl to move files in
```

**Option C — Put test images in the repo**

For a hackathon demo, the simplest approach: add a small set of test photos to `storage/` in your repo and remove `storage/*` from `.gitignore`. They'll be baked into the image and available at `/app/storage` immediately.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build times out | Normal on first build (downloading ArcFace). Wait 15 min. |
| `CREATE EXTENSION vector` fails | Make sure you added the Railway PostgreSQL plugin, not a custom Postgres |
| `/auth/selfie` returns 500 | Check logs — usually a missing env var or DB not migrated yet |
| Images return 404 after redeploy | Volume not mounted — confirm `/app/storage` has a Railway volume attached |
| `grab_id` never matches | Threshold too strict — try setting `FACE_SIMILARITY_THRESHOLD=0.50` |
