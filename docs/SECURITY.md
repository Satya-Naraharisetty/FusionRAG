# Security Policy and Secrets Management

## 1. Secret Management Policy
We take security seriously. Hardcoding secrets or committing them to the repository in any form (including defaults, tests, configuration scripts, or Dockerfiles) is strictly prohibited.
All secrets, credentials, API keys, and certificates must be handled dynamically through:
- Local environment files (`.env`, ignored by Git)
- Secret manager services (e.g., AWS Secrets Manager, HashiCorp Vault, Doppler)
- Deployment platform environment configurations (e.g., Render, Vercel, Supabase, Upstash)
- GitHub Repository Secrets for CI/CD pipelines

---

## 2. Required Environment Variables
The application requires the following environment variables. Refer to [backend/.env.example](file:///d:/fun/fusion_rag/backend/.env.example) for the complete up-to-date template.

### Core LLM & Inference Providers
- `GEMINI_API_KEY`: API Key for Google Gemini LLM chat completion (`gemini-3.5-flash-lite`), vision OCR parsing, and query rewriting.
- `JINA_API_KEY`: API Key for Jina AI dense embeddings (`jina-embeddings-v3`, 768-dim) and cross-encoder reranking (`jina-reranker-v2-base-multilingual`).
- `RESEND_API_KEY`: API Key for transactional email verification and magic link authentication.

### Security, Cryptography & Encryption
- `JWT_SECRET`: High-entropy string ($\ge 32$ characters) used for signing HS256 authentication tokens.
- `ENCRYPTION_MASTER_KEY`: Master encryption key ($\ge 32$ characters) used to wrap per-user data encryption keys.

### Databases & Ephemeral Cache
- `DATABASE_URL`: Full PostgreSQL connection URL (e.g., Supabase transaction pooler port 6543, local PostgreSQL).
- `REDIS_URL`: Connection string for Redis 7 cache, rate limiters, and stream task queues (e.g., Upstash, local Redis).
- `QDRANT_URL` / `QDRANT_API_KEY`: Connection endpoint and API key for Qdrant Vector database.

### OAuth Providers (Optional)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Credentials for Google OAuth 2.0 social login.
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`: Credentials for GitHub OAuth 2.0 social login.

---

## 3. Local Development Setup
1. Copy `backend/.env.example` to `backend/.env`.
2. Populate the variables with your local or development credentials.
3. Copy `frontend/.env.example` to `frontend/.env` and verify `VITE_API_BASE_URL`.
4. Ensure all `.env` files remain untracked (they are automatically ignored by our root and subproject `.gitignore` rules).

---

## 4. Production Secret Requirements
When `ENV=production` is set, the application enforces fail-fast validations during startup via `validate_production_secrets` in `backend/app/core/config.py`:
- `JWT_SECRET` is mandatory, must be at least 32 characters long, and must not match any development or testing placeholder (e.g., `super_secure_random_development_signing_key_32_bytes_at_least`, `testing_secret`, `mock_secret`, or contain words like `development`, `testing`, or `mock`).
- `ENCRYPTION_MASTER_KEY` is mandatory, must be at least 32 characters long, and must not match known test placeholders.
- `GEMINI_API_KEY` (or fallback keys) is required if Gemini LLM or embedding provider is active.
- `JINA_API_KEY` is required if Jina embeddings or cross-encoder reranker is enabled.
- OAuth Client Secrets (`GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_SECRET`) are strictly required if the corresponding OAuth Client IDs are configured.

---

## 5. Credential Rotation Procedure
If any credentials need to be rotated, follow these platform-specific guidelines:
1. **Gemini API Key**: Revoke the compromised key in [Google AI Studio](https://aistudio.google.com/) or GCP Console and generate a new key. Update it in your production deployment's environment variables.
2. **Jina API Key**: Revoke and regenerate the key in the [Jina AI Developer Console](https://jina.ai/).
3. **Database Credentials**: Change the password in the Supabase Database Settings. Update `DATABASE_URL` in the deployment platform env config.
4. **Redis Credentials**: Regenerate the REST / Connection token in the Upstash console.
5. **Qdrant API Key**: Regenerate API keys in Qdrant Cloud or your self-hosted instance.
6. **Resend API Key**: Regenerate API keys in the Resend Dashboard.
7. **Google/GitHub OAuth Secrets**: Regenerate client secrets in GCP Credentials or GitHub Developer Settings and update the corresponding provider env variables.

---

## 6. What to do if a Secret is Accidentally Committed
If a secret is committed to the repository:
1. **Rotate the Secret Immediately**: Treat the secret as fully compromised. Do not wait for git history deletion to rotate it.
2. **Purge Git History**: Use `git-filter-repo` (recommended) or BFG Repo-Cleaner to strip the secret from the repository's history before pushing changes to any public or shared remote.
   ```bash
   pip install git-filter-repo
   git filter-repo --invert-paths --path backend/.env
   ```
3. **Notify the Team**: Communicate the compromise to the team so they can update their local configurations with rotated keys.

---

## 7. GitHub Actions Secret Handling
- Never hardcode credentials in workflow files.
- Store sensitive values in **GitHub Settings -> Secrets and variables -> Actions**.
- Access secrets using `${{ secrets.SECRET_NAME }}` syntax.
- **Do not use command substitution** directly inside the workflow `env:` block. Instead, generate ephemeral secrets dynamically inside a step and write them to `$GITHUB_ENV` (e.g. `echo "JWT_SECRET=$(openssl rand -hex 32)" >> "$GITHUB_ENV"`).
- Ensure secrets are not printed or echoed to stdout during workflows.

---

## 8. Docker Secret / Environment Handling
- **Do not COPY `.env` files** into Docker images.
- **Do not use `ARG`** for passing private credentials, as they are baked into image metadata and layers.
- Inject secrets as runtime environment variables at container startup (`docker run -e ...` or using `env_file` in `docker-compose.yml`).
- Use multi-stage builds and run containers under a non-root user (like `appuser`) as configured in our `Dockerfile`.

---

## 9. Frontend Environment Variable Rules
- Vite exposes variables prefixed with `VITE_` to the client bundle (e.g., `VITE_API_BASE_URL`).
- **Never put private keys, secrets, or passwords in frontend environment variables.** Since they are bundled into client-side JS, they are visible to anyone inspecting the network tab or source files.
- The frontend should only consume public configurations.

---

## 10. Security Reporting Guidance
If you discover a security vulnerability in this project, please do not open a public issue. Instead, report it privately to the security team or project maintainers.

