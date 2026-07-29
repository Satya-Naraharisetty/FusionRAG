# Use official slim Python runtime
FROM python:3.12-slim

# Set environment system variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    UV_SYSTEM_PYTHON=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv package installer
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Create non-root application user
RUN groupadd -g 1000 appuser && \
    useradd -r -u 1000 -g appuser -d /app -s /sbin/nologin appuser

# Copy dependency configs
COPY pyproject.toml /app/

# Install application dependencies using uv
RUN uv pip install --system .

# Copy application source
COPY . /app

# Grant execution rights to our non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose API service port
EXPOSE 8000

# Start server launcher
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
