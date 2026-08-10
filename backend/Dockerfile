# Build stage: install dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy dependency files
COPY requirements.txt requirements.cpu.txt ./

# Install dependencies using pip
# requirements.cpu.txt adds the PyTorch CPU index so torch resolves to the
# +cpu wheel instead of the multi-GB CUDA build (keeps the image ~3x smaller).
RUN pip install --no-cache-dir -r requirements.cpu.txt

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

# Create huggingface cache directory
RUN mkdir -p /cache/huggingface

# Copy backend application code
COPY . .

# Expose port 8000
EXPOSE 8000

# Run migrations and start the application
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
