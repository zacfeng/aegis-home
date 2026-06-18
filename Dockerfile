# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Security: run as non-root
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /srv

# Install dependencies in a separate layer for better cache reuse
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Railway injects PORT at runtime; default to 8000 locally
ENV PORT=8000

USER app

# Load .env only when present (development); Railway injects vars directly
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
