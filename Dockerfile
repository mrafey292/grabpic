# ── Stage 1: Download DeepFace model weights ─────────────────────────────────
# We do this in a separate stage so the weights are baked into the image.
# Without this, the first /auth/selfie request would hang for 2+ minutes
# downloading 500MB of ArcFace weights on the live server.
FROM python:3.11-slim AS model-downloader

RUN pip install --no-cache-dir deepface tf-keras

# Pre-download ArcFace weights into the default DeepFace cache dir (~/.deepface)
RUN python -c "\
from deepface import DeepFace; \
import numpy as np; \
dummy = np.zeros((112, 112, 3), dtype=np.uint8); \
DeepFace.represent(dummy, model_name='ArcFace', enforce_detection=False); \
print('ArcFace weights downloaded.')"

# ── Stage 2: Production app ───────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for DeepFace (OpenCV needs these)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-downloaded model weights from stage 1
COPY --from=model-downloader /root/.deepface /root/.deepface

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Create storage dir (Railway volume will mount here)
RUN mkdir -p /app/storage

EXPOSE 8000

# start.sh runs DB migrations + pgvector setup before starting gunicorn
RUN chmod +x start.sh
CMD ["./start.sh"]
