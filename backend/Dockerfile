# Build stage: install dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy dependency files
COPY requirements.txt ./

# Install dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code after installing dependencies
COPY . .

# Production stage: minimal runtime image
FROM python:3.12-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set up PATH to include installed binaries
ENV PATH="/usr/local/bin:$PATH"

# Create a non-root user and group
RUN groupadd -g 999 appuser && \
    useradd -r -u 999 -g appuser appuser

# Set up huggingface cache and application data folder, and set permissions
RUN mkdir -p /cache/huggingface /app/data && \
    chown -R appuser:appuser /cache/huggingface /app/data

# Copy backend application code with correct ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port 8000
EXPOSE 8000

# Run migrations and start the application
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
