# Build stage: install dependencies with uv
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN if [ -f pyproject.toml ]; then \
        uv sync --frozen --no-install-workspace --no-dev; \
    else \
        echo "Error: pyproject.toml not found"; \
        exit 1; \
    fi

# Production stage: minimal runtime image
FROM python:3.12-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Set up PATH to use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Create huggingface cache directory
RUN mkdir -p /cache/huggingface

# Copy backend application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Run migrations and start the application
CMD sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"