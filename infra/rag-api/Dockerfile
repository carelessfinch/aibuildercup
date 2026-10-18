FROM mirror.gcr.io/library/python:3.13-slim-trixie

# MediaPipe (which runs EmbeddingGemma for query embeddings) and the OpenCV it pulls in need these libraries.
# Without them search still works, but keyword-only (GET /healthz shows search_mode and dense_error).
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgles2 libgl1 libxcb1 libglib2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# EmbeddingGemma 300M query encoder, from Google's public MediaPipe bucket (Gemma terms of use).
# It must match the model the index was embedded with (index/meta.json -> embedding).
ADD https://storage.googleapis.com/mediapipe-models/text_embedder/embedding_gemma/int4int8/latest/embedding_gemma.task /models/embedding_gemma.task
ENV LITRAG_GEMMA_TASK=/models/embedding_gemma.task

COPY litrag ./litrag
COPY app ./app

# The index is NOT in the image: it is copied from the private bucket at startup (LITRAG_INDEX_URI).
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
