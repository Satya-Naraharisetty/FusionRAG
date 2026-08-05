# Deployment Manual - Hybrid RAG Chatbot

This manual provides setup, operation, backup, and release guides for running the **Hybrid RAG Chatbot** in production.

---

## 1. Supported Software Versions

For optimal security and stability, target the following backing versions:
*   **PostgreSQL**: `16.x` (Alpine-based)
*   **Redis**: `7.2.x` (Alpine-based)
*   **Qdrant**: `1.9.x`
*   **Nginx**: `1.27.x` (Alpine-based)
*   **Python**: `3.12.x`
*   **NodeJS**: `18.x` or `20.x`

---

## 2. Production Environment Configurations

The production environment is configured using `.env.production`. Ensure these keys are populated before launching:

| Configuration Variable | Description | Example Value |
| :--- | :--- | :--- |
| `ENV` | Environment identifier | `production` |
| `POSTGRES_PASSWORD` | Strong password for PostgreSQL | `(Generated Secret)` |
| `JWT_SECRET` | 32+ bytes signing key for JWT tokens | `(Generated Hex Secret)` |
| `GEMINI_API_KEY` | Primary LLM Provider API Key | `AIzaSy...` |
| `OPENAI_API_KEY` | Backup LLM & Embeddings API Key | `sk-proj-...` |
| `STORAGE_PROVIDER` | Ingestion storage engine (`database`, `local`, `s3`) | `s3` |
| `S3_BUCKET` | Destination S3 Bucket Name | `my-production-rag-bucket` |
| `COOKIE_SECURE` | Forces secure HTTPS-only session cookies | `True` |

---

## 3. Initial Setup & Launch Instructions

### A. Clone & Configure Secrets
1.  Copy the example variables:
    ```bash
    cp .env.production.example .env.production
    ```
2.  Populate `.env.production` with secure keys.

### B. Provision SSL Certificates (Let's Encrypt)
To obtain certificates for your domain (e.g. `example.com`), mount a certbot container or use local certbot commands:
```bash
# Obtain dry-run certificates first
docker run -it --rm --name certbot \
  -v "$(pwd)/nginx-ssl:/etc/letsencrypt" \
  -v "$(pwd)/var/www/certbot:/var/www/certbot" \
  certbot/certbot certonly --webroot \
  -w /var/www/certbot -d example.com --dry-run
```
For local testing, place self-signed certificates in:
*   `nginx-ssl/live/localhost/fullchain.pem`
*   `nginx-ssl/live/localhost/privkey.pem`

### C. Spin Up Production Stack
Run Docker Compose using the production template:
```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

---

## 4. Database Migrations

Database migrations must run before accepting user traffic. Run the migration script inside the backend container:
```bash
docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head
```

---

## 5. Programmatic Backups & Restores

Backup shell scripts are located in `backend/scripts/`.

### A. PostgreSQL Metadata Database
*   **Backup**:
    ```bash
    docker compose -f docker-compose.prod.yml exec -T backend sh scripts/backup_postgres.sh
    ```
*   **Restore**:
    ```bash
    docker compose -f docker-compose.prod.yml exec -T backend sh scripts/restore_postgres.sh ./data/backups/postgres_hybrid_rag_xxxxxxxx.dump
    ```

### B. Qdrant Vector Indices
*   **Backup**:
    ```bash
    docker compose -f docker-compose.prod.yml exec -T backend sh scripts/backup_qdrant.sh
    ```
*   **Restore**:
    ```bash
    docker compose -f docker-compose.prod.yml exec -T backend sh scripts/restore_qdrant.sh ./data/backups/qdrant_documents_xxxxxxxx.snapshot
    ```

---

## 6. Logs & Auditing

Structured JSON logs are outputted to `stdout` inside the containers.
*   **Access Backend Logs**:
    ```bash
    docker compose -f docker-compose.prod.yml logs -f backend
    ```

### Log Rotation Guidance
For production hosts, configure a logrotate script in `/etc/logrotate.d/docker-containers`:
```text
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    missingok
    delaycompress
    copytruncate
    maxsize 100M
}
```

---

## 7. Production Release Checklist

Prior to launching user traffic, confirm that all items are checked:

*   [ ] **Build & Tests**: GitHub Actions build passes and local unit tests succeed.
*   [ ] **Healthchecks**: Liveness (`/health/live`) and Readiness (`/health/ready`) endpoints return HTTP 200.
*   [ ] **DB Migrations**: Alembic version matches the latest script head.
*   [ ] **Deep Health**: `/health/deep` returns all backing systems (Postgres, Redis, Qdrant, S3) as "healthy".
*   [ ] **Smoke Test**: `python scripts/smoke_test.py --full` succeeds without warnings.
*   [ ] **HTTPS / TLS**: Redirects from HTTP to HTTPS function correctly, and certificates are valid.
*   [ ] **Secrets Hardening**: `COOKIE_SECURE` is set to `True` and `DEBUG` options are disabled.
*   [ ] **Backups**: Backup scripts have been tested and restore capability is validated.
*   [ ] **Admin Seeding**: Initial admin accounts are established; default testing users are purged.
*   [ ] **Resource Constraints**: Docker limits memory and CPU usage configurations correctly.
*   [ ] **Git Tagging**: Released version is tagged in Git history.
