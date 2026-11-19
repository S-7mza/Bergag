# ==========================================
# Multi-stage Dockerfile for Procurement Ingestion
# Base: Debian-based Python 3.12 Slim
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies needed for compiling C-extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*

# Build wheels in virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# Final Runtime Stage
# ==========================================
FROM python:3.12-slim

# Install runtime system packages:
# - libpq5: PostgreSQL async client library
# - tesseract-ocr + fra + ara: OCR for scanned Moroccan commune dossiers
# - poppler-utils: PDF rendering utilities
# - antiword: Instant legacy Word (.doc) text extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    tesseract-ocr \
    tesseract-ocr-fra \
    tesseract-ocr-ara \
    poppler-utils \
    antiword \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV TZ=Africa/Casablanca

# Create isolated application user
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

USER appuser

COPY --chown=appuser:appuser . .

# Default command
CMD ["python", "-m", "src.scheduler.jobs"]

