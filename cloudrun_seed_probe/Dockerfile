# Dockerfile for ConspiracyComments Seed Claim Probe Service
FROM python:3.11-slim

# Avoid writing pyc files to disk and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install system dependencies (build-essential needed for some C extensions if any, but slim keeps it minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download and cache the ONNX embedding model inside the image.
# This prevents downloading it on container startup, drastically reducing cold start time!
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

# Copy application code
COPY main.py .

# Run the application with uvicorn
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1
