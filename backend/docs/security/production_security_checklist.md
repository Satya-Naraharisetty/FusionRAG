# Production Security Checklist & WAF Deployment Blueprint

This document specifies the security controls for the Fusion RAG platform, explicitly distinguishing **[APPLICATION COMPLETE]** controls (implemented in codebase and verified via automated tests) from **[DEPLOYMENT REQUIRED]** controls (to be configured in infrastructure/cloud environments).

---

## 1. Security Architecture & Threat Model

```text
Internet Client (Adversary / Legitimate User)
  │
  ▼ [DEPLOYMENT REQUIRED: Edge Protection]
Cloudflare / AWS WAF & Shield (Volumetric DDoS, TLS Termination, IP Reputation)
  │
  ▼ [DEPLOYMENT REQUIRED: Ingress Proxy]
Reverse Proxy / Load Balancer (Rate Limit Shunting, Timeout Enforcement)
  │
  ▼ [APPLICATION COMPLETE: Backend Core]
FastAPI Application Pipeline:
  ├── ProductionMiddleware (CSP, X-Frame-Options, Nosniff, Permissions-Policy, HSTS)
  ├── RateLimiter (Sliding Window Redis + In-Memory Fallback, Lockout Defense)
  ├── Auth Guard (NIST Password Validation, HS256 Token Auth, Refresh Replay Revocation)
  ├── PromptInjectionScanner (Adversarial Heuristics + PROMPT_INJECTION_BLOCKED Audit Log)
  ├── MagicByteValidator (File signature checking, zip-bomb ratio checks < 100x)
  ├── ClamAVScanner Adapter (Fail-closed virus scanning before persistence)
  ├── Tenant Boundary (PostgreSQL parameterized queries + Qdrant user_id filters)
  ├── ContextSelector (Strict allowed_doc_ids scoping before parent/window resolution)
  ├── PromptBuilder (<retrieved_context> untrusted data framing + policy prompt)
  └── SafeCalculator & ToolExecutor (AST sandbox + arithmetic limits, bounded timeouts)
```

---

## 2. Comprehensive Security Checklist

| Domain | Control Description | Enforcement Mechanism | Status |
|---|---|---|---|
| **Authentication** | NIST-compliant password strength | `AuthService.register_user` | ✅ **APPLICATION COMPLETE** |
| **Authentication** | Generic 401 error message to block account enumeration | `AuthService.authenticate_user` | ✅ **APPLICATION COMPLETE** |
| **Authentication** | Single-use refresh token rotation with replay revocation | `AuthService.refresh_session` | ✅ **APPLICATION COMPLETE** |
| **Authentication** | Consecutive failed login attempt lockout (5 tries -> 5 min) | `LoginAttemptTracker` (Redis/Memory) | ✅ **APPLICATION COMPLETE** |
| **Authorization** | Strict tenant ID / ownership checks on all document CRUD | `DocumentService` | ✅ **APPLICATION COMPLETE** |
| **Authorization** | Strict tenant ID / ownership checks on all conversation operations | `ConversationManager` | ✅ **APPLICATION COMPLETE** |
| **Authorization** | Immutable authenticated user context injected into tool execution | `ToolContext`, `ToolExecutor` | ✅ **APPLICATION COMPLETE** |
| **Retrieval Isolation** | Parameterized SQL queries scoped to `user_id` | SQLAlchemy ORM Repositories | ✅ **APPLICATION COMPLETE** |
| **Retrieval Isolation** | Vector store filter injection on all similarity queries | `QdrantVectorStore.search` | ✅ **APPLICATION COMPLETE** |
| **Retrieval Isolation** | Document scope filtering on parent-child & sentence-window resolution | `ContextSelector.select_context` | ✅ **APPLICATION COMPLETE** |
| **Cache Security** | Tenant-scoped keyspaces (`user_id` & `conversation_id`) | `InMemoryIndexCache`, `RedisCache` | ✅ **APPLICATION COMPLETE** |
| **File Upload** | Magic-byte signature verification for PDF, DOCX, TXT, MD | `MagicByteValidator` | ✅ **APPLICATION COMPLETE** |
| **File Upload** | Zip bomb defense (max file size 25MB, expansion ratio < 100x) | `MagicByteValidator` | ✅ **APPLICATION COMPLETE** |
| **File Upload** | Filename path-traversal sanitization | `DocumentService._sanitize_filename` | ✅ **APPLICATION COMPLETE** |
| **Malware Scanning** | Antivirus streaming socket adapter (`ClamAVScanner`) | `app.core.security.malware` | ✅ **APPLICATION COMPLETE** |
| **Malware Scanning** | ClamAV / clamd daemon infrastructure provisioning | Linux `clamd` TCP daemon (Port 3310) | ⚙️ **DEPLOYMENT REQUIRED** |
| **Prompt Injection** | Direct heuristic input scanner on `/chat` and `/search` | `PromptInjectionScanner` | ✅ **APPLICATION COMPLETE** |
| **Prompt Injection** | Structured security logging (`PROMPT_INJECTION_BLOCKED`) | Sanitized logger in scanner | ✅ **APPLICATION COMPLETE** |
| **Prompt Injection** | Retrieved content isolated in `<retrieved_context>` tags | `PromptBuilder` | ✅ **APPLICATION COMPLETE** |
| **Prompt Injection** | System prompt directive: retrieved content is untrusted | `system_prompt.txt`, `SynthesisAgent` | ✅ **APPLICATION COMPLETE** |
| **Sandboxing** | AST arithmetic validator blocking imports, calls, builtins | `SafeCalculator` | ✅ **APPLICATION COMPLETE** |
| **Sandboxing** | Exponential calculation DoS protection (`base <= 10000`, `exp <= 15`) | `SafeCalculator._eval_node` | ✅ **APPLICATION COMPLETE** |
| **Queue Security** | Background job payload tenant verification against DB record | Queue job handlers | ✅ **APPLICATION COMPLETE** |
| **Queue Security** | Task allowlist checking | `JobDispatcher` | ✅ **APPLICATION COMPLETE** |
| **Error Security** | Sanitized client 500 error messages (zero connection strings/paths) | Exception handlers & route try/except | ✅ **APPLICATION COMPLETE** |
| **Secrets & Keys** | Production startup validation for `ENCRYPTION_MASTER_KEY` & `JWT_SECRET` | `Settings.validate_production_secrets` | ✅ **APPLICATION COMPLETE** |
| **Privacy & Logging**| Automatic PII, token, password, and credential masking in telemetry | `app.core.telemetry.sanitizer` | ✅ **APPLICATION COMPLETE** |
| **Security Headers**| CSP, X-Frame-Options: DENY, X-Content-Type-Options: nosniff | `ProductionMiddleware` | ✅ **APPLICATION COMPLETE** |
| **Security Headers**| Strict-Transport-Security (HSTS) in production HTTPS mode | `ProductionMiddleware` | ✅ **APPLICATION COMPLETE** |
| **Rate Limiting**   | Application sliding-window limiter on mutation/heavy endpoints | `RateLimiter` (Redis / In-Memory) | ✅ **APPLICATION COMPLETE** |
| **WAF / DDoS**      | Cloud WAF (AWS WAF / Cloudflare) for volumetric DDoS mitigation | Edge DNS & CDN configuration | ⚙️ **DEPLOYMENT REQUIRED** |
| **TLS Termination** | TLS 1.3 termination and HTTPS enforcement at edge | Reverse proxy / Load Balancer | ⚙️ **DEPLOYMENT REQUIRED** |
| **Secrets Manager** | Cloud KMS / Vault for runtime environment secret injection | AWS Secrets Manager / HashiCorp Vault | ⚙️ **DEPLOYMENT REQUIRED** |

---

## 3. Production ClamAV Deployment Verification Procedure

When deploying to a staging or production Kubernetes / VM cluster:

1. Deploy the ClamAV daemon container:
   ```yaml
   image: clamav/clamav:latest
   ports:
     - containerPort: 3310
   ```
2. Configure application environment variables:
   ```bash
   MALWARE_SCANNER_TYPE=clamav
   CLAMAV_HOST=clamav-service.internal
   CLAMAV_PORT=3310
   CLAMAV_TIMEOUT_SECONDS=10.0
   MALWARE_SCAN_FAIL_CLOSED=true
   ```
3. Test daemon connectivity:
   ```bash
   uv run python -c "
   import asyncio
   from app.core.security.malware import ClamAVScanner
   scanner = ClamAVScanner(host='clamav-service.internal', port=3310)
   print('Daemon Alive:', asyncio.run(scanner.ping()))
   "
   ```
4. Verify with EICAR test string:
   - Uploading `eicar.txt` (`X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*`) must return HTTP 400 with `"Malware or virus signature detected in file"`.

---

## 4. Production WAF Deployment Blueprint

1. **Layer 7 Rate Limiting**:
   - Configure edge WAF to enforce 100 req/min per IP on `/api/v1/auth/*` and 300 req/min on `/api/v1/*`.
2. **Payload Size Restrictions**:
   - Limit HTTP request bodies to 30 MB maximum (accommodates 25 MB max document upload).
3. **HTTP Method Allowlisting**:
   - Allow only `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS`, and `HEAD`.
4. **Origin Protection**:
   - Configure reverse proxy to accept traffic solely from WAF IPs (preventing origin bypass).
