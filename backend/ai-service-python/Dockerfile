# Build context = repo root (see fly.ai.toml)
FROM python:3.12-slim
WORKDIR /app
COPY backend/ai-service-python/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ai-service-python/ .
# /data is normally the Fly volume mount; create it so the image also runs
# standalone (local docker run, CI) without crash-looping on cache init.
RUN mkdir -p /data
ENV TRANSLATION_DB_PATH=/data/translations.db
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
