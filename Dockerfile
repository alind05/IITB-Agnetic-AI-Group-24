# Use official Python 3.11 slim image (avoids bleeding-edge 3.14 wheel compilation issues)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system build essentials & curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy entire application codebase (backend, static, main.py, etc.)
COPY . .

# Create persistent directories for portal notes and SEC EDGAR cache
RUN mkdir -p /app/.data /app/.cache

# Expose Uvicorn port
EXPOSE 8000

# Environment settings
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Healthcheck to verify FastAPI server is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Run FastAPI application via Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
