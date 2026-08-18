# E2E Smoke Tests

Reusable smoke tests for the auth path against a running stack:

- **`login-flow.js`** — browser smoke test (`npm run e2e:login`): registers a
  throwaway account through the public API, drives a real Chrome session
  through login, verifies the refresh-cookie session survives a fresh page
  load, deletes the account through the **Settings UI** (Data & Privacy →
  Delete Account → typed-email + re-entered-password confirmation), and keeps
  the API cleanup as a safety net — even if a check fails.
- **`account-delete.js`** — pure API smoke test (`npm run e2e:account-delete`):
  exercises `DELETE /auth/account` directly (register → delete → verify the
  credentials and stale refresh cookie are rejected), including the
  password re-entry gate and the 204 response. No browser needed.
- **`redis-fallback.js`** — pure API + docker-compose smoke test
  (`npm run e2e:redis-fallback`): stops the `redis` service, proves the
  in-memory rate-limit fallback still enforces the delete budget
  (`401` × budget, then `429`), restarts redis, and cleans up its throwaway
  account. No browser needed.
- **`redis-fallback-login.js`** — pure API + docker-compose smoke test
  (`npm run e2e:redis-fallback-login`): stops `redis`, proves the **general**
  limiter (shared by login/register/chat, `60` rpm + `10` burst = `70` per
  window, IP-keyed) still enforces its budget with Redis down, then proves the
  per-user delete budget was **not** consumed by the login hammer
  (per-endpoint isolation in the shared in-memory store). Restarts redis and
  cleans up. No browser needed.
- **`verify-two-tier.js`** — full browser E2E of the two-tier document model
  (`npm run e2e:two-tier`): uploads a GLOBAL document via the Documents
  section and uses it through `@documents` in any chat, attaches a CHAT-SCOPED
  document in the composer (auto-used with no mention, cascade-deleted when
  the conversation is deleted), and checks the "Answering from general
  knowledge" hint for queries that match nothing. Needs Chrome, the Vite dev
  server, the dockerized backend, and a real LLM key (`GEMINI_API_KEY`) —
  embeddings are also generated via Gemini, which requires a valid `GEMINI_API_KEY` on the backend.

Both `redis-fallback*` scripts share their docker orchestration through
`stack.js`.

## Prerequisites

- The stack is running:
  - Vite dev server on `http://localhost:5173` (`cd frontend && npm run dev`)
  - Dockerized backend on `http://localhost:8000` (`docker compose up -d`)
- For the browser test only: Google Chrome installed (the script drives the
  installed Chrome via `puppeteer-core`; it does not download a browser).

## Run

```bash
cd frontend
npm run e2e:login               # browser login flow + session persistence
npm run e2e:account-delete      # DELETE /auth/account API assertion
npm run e2e:redis-fallback      # delete-limit fallback with Redis stopped
npm run e2e:redis-fallback-login  # general-limit fallback + budget isolation
npm run e2e:two-tier            # two-tier document model (needs GEMINI_API_KEY)
```

All scripts exit `0` when every check passes and `1` on any failure, so they
can be wired into CI.

## What the login flow verifies

| # | Check |
|---|-------|
| 1 | `POST /api/v1/auth/register` creates the throwaway account (HTTP 201) |
| 2 | Login page renders at `/login` |
| 3 | Submitting valid credentials redirects to `/chat` (no error text) |
| 4 | The logged-in user's email appears in the sidebar |
| 5 | The `refresh_token` cookie is stored at the API path (`/api/v1/auth`) |
| 6 | A fresh page (no in-memory access token) auto-logs-in to `/chat` via the refresh cookie |
| 7 | No console errors, failed requests, or 4xx/5xx responses during the flow |
| 8 | Settings UI deletes the account: the dialog gates on the typed email **and** a non-empty re-entered password, confirming redirects to `/login`, and a re-login with the same credentials is rejected |
| 9 | Safety net: if the UI step never deleted the account, `DELETE /auth/account` (with the password in the body) returns 204 and the same credentials are rejected afterwards |

## What the account-delete test verifies

| # | Check |
|---|-------|
| 1 | `POST /api/v1/auth/register` creates the throwaway account (HTTP 201) |
| 2 | `POST /auth/login` returns an access token (HTTP 200) |
| 3 | `DELETE /auth/account` with a **wrong password** returns 401 and the account survives |
| 4 | `DELETE /auth/account` with the Bearer token **and correct password** returns 204 |
| 5 | The same credentials are rejected afterwards (`401`) — account is gone |
| 6 | A refresh with the stale `refresh_token` cookie is rejected (`401`) — sessions were cascaded |

## What the Redis-down fallback test verifies

`redis-fallback.js` exercises the shared in-memory rate-limit fallback in
`backend/app/core/security/rate_limiter.py` against a **live stack**:

| # | Check |
|---|-------|
| 1 | `POST /api/v1/auth/register` creates the throwaway account (HTTP 201) |
| 2 | `POST /auth/login` returns an access token (HTTP 200) |
| 3 | `docker compose stop redis` — the backend must keep serving (liveness stays 200) |
| 4 | `DELETE /auth/account` with a wrong password returns `401` for exactly the configured budget (default 10) |
| 5 | Every request past the budget returns `429` — only the in-memory fallback can produce that with Redis down |
| 6 | `docker compose start redis`, redis answers `PING` again, and the cleanup `DELETE` with the correct password returns 204 |
| 7 | The same credentials are rejected afterwards (`401`) — account is gone |

Redis is always restarted in a `finally` block (even on failure), and the
throwaway account is cleaned up through the API. The script needs docker
compose access to the same stack it tests — it never touches the database
and never deletes pre-existing accounts.

## What the Redis-down general-limiter test verifies

`redis-fallback-login.js` covers the **general** limiter (`60` rpm + `10` burst
= `70` allowed per window) and proves the shared fallback store isolates
per-endpoint budgets:

| # | Check |
|---|-------|
| 1 | `POST /api/v1/auth/register` creates the throwaway account (HTTP 201) |
| 2 | `POST /auth/login` returns an access token (HTTP 200) |
| 3 | `docker compose stop redis` — the backend keeps serving (liveness 200) |
| 4 | Hammers `POST /auth/register` with the throwaway's **own email**: every request is `400` (DUPLICATE_ACCOUNT) until the IP's general budget is exhausted, then the first `429` lands in `[60, 70]` and everything after stays `429` |
| 5 | Hammers `DELETE /auth/account` with a wrong password: the first 10 are still `401` and the rest `429` — the register hammer did **not** consume the per-user delete budget (isolation) |
| 6 | `docker compose start redis`, redis answers `PING` again, cleanup `DELETE` with the correct password returns 204 |
| 7 | The same credentials are rejected afterwards (`401`) — account is gone |

Login/register/chat share the general limiter keyed by **client IP**
(`ip:<host>`), while `DELETE /auth/account` uses a strict limiter keyed by the
**authenticated user** (`user:<id>`) with its own `(rpm, burst)` config — the
shared in-memory store is keyed by config, so the two budgets are isolated by
construction and this test proves it against a live stack.

The general limiter is exhausted through **register** rather than login
because login runs an Argon2 hash verify per attempt (~4-5s on the dockerized
stack) — a 70-request hammer would span minutes, so the 60s sliding window
would keep evicting entries and the budget could never fill. Re-registering an
already-registered email returns `400` (`DUPLICATE_ACCOUNT`) from the uniqueness
check **before** any hashing, exercising the same rate limiter in a few
seconds.

With Redis down, each rate-limited request used to stall ~4s on the failed
Redis attempt (blocking the event loop), so even the fast 400 path could not
fill the window. `rate_limiter.py`'s Redis-health circuit breaker fixes that:
the first failed attempt trips the breaker and subsequent requests skip Redis
and hit the shared in-memory store in microseconds — so the budget fills
within the 60s window and the hammer completes in seconds. The breaker TTL
(5s) is close to the hammer duration, so a mid-hammer expiry can add one
~4s probe stall; this never shifts the observed 429 boundary (the memory
store is what blocks, so the first 429 lands at exactly the configured
budget regardless of stalls).

> **Note:** because the general limiter is IP-keyed, re-running
> `redis-fallback-login.js` within ~60s of a previous run against the same
> long-lived backend can lower the observed 429 boundary. CI always boots a
> fresh backend; locally, wait a minute between runs.

## What the two-tier document model test verifies

`verify-two-tier.js` drives the real UI through the full document lifecycle.
It registers a throwaway account, then:

| # | Check |
|---|-------|
| 1 | Uploads `aurora.txt` **globally** via the Documents section (Upload All → processed + vectorized) |
| 2 | Chat A: attaches `tunneling.txt` in the composer, asks **without** `@documents` — the answer cites `tunneling.txt` (chat-scoped auto-use), and no general-knowledge hint appears (retrieval ran) |
| 3 | Chat B: asks with `@documents` — the answer cites the global `aurora.txt` and shows **no** leak of chat A's `tunneling.txt` |
| 4 | Chat B: asks a question that matches nothing (no mention) — the "Answering from general knowledge" hint appears |
| 5 | Deletes chat A through the sidebar UI — the conversation is gone, no documents remain scoped to it, and `tunneling.txt` is gone while `aurora.txt` survives on the Documents page |
| 6 | No unexpected console errors or uncaught page errors; the throwaway account is deleted through the API in cleanup |

The test fixtures are the tracked files in `frontend/e2e/fixtures/` (their
content is what the grounding assertions depend on). LLM answers stream from a
real provider (Gemini by default), so the script needs `GEMINI_API_KEY` set
in the backend's environment. The script's `sendAndWaitForLog` retry loop
absorbs transient Gemini free-tier 429s. Embeddings run locally
(via the `text-embedding-004` model), which requires `GEMINI_API_KEY` in all environments.

## Configuration (env vars)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FRONTEND_URL` | `http://localhost:5173` | Vite dev server origin (login flow) |
| `API_URL` | `http://localhost:8000` | Backend origin (all scripts) |
| `CHROME_PATH` | `C:/Program Files/Google/Chrome/Application/chrome.exe` | Path to Chrome binary (login flow) |
| `COMPOSE_PROJECT_NAME` | auto | Compose project of the running stack (redis-fallback*; CI pins `hybrid_rag`) |
| `RATE_LIMIT_BUDGET` | `10` | Expected per-user delete budget (redis-fallback*) |
| `RATE_LIMIT_EXTRA` | `2` | Requests sent past the budgets to observe 429 (redis-fallback*) |
| `RATE_LIMIT_GENERAL_ALLOWED` | `70` | General limiter rpm+burst budget (`60`+`10`; redis-fallback-login) |
| `RATE_LIMIT_GENERAL_LOWER` | `60` | Floor for the observed 429 boundary (redis-fallback-login) |
| `KEEP_ACCOUNT=1` | unset | Skip account cleanup (debugging) |
| `AURORA_FILE` | `fixtures/aurora.txt` | Global-document fixture (two-tier) |
| `TUNNEL_FILE` | `fixtures/tunneling.txt` | Chat-scoped-document fixture (two-tier) |

Example with overrides:

```bash
FRONTEND_URL=http://localhost:5173 API_URL=http://localhost:8000 npm run e2e:login
API_URL=http://localhost:8000 npm run e2e:account-delete
API_URL=http://localhost:8000 npm run e2e:redis-fallback
API_URL=http://localhost:8000 npm run e2e:redis-fallback-login
```

## API-only — no database access

Both scripts are **pure API**: they never use `docker exec`, `psql`, or any
other direct database access. Every step — register, login, delete, and the
verification that the account is really gone — goes through the public HTTP
API of the running backend:

- Deletion is performed by calling `DELETE /api/v1/auth/account` with a Bearer
token obtained from a normal login **and the account password in the request
body** — the endpoint rejects a wrong password with `401`, and the scripts
exercise that rejection too. On success the endpoint removes the user row and
the database `ON DELETE CASCADE` constraints clean up its `refresh_sessions`
(and any conversations/documents).
- "The account is gone" is *proven* through the API: logging back in with the
same credentials must return `401`, and a refresh with the stale
`refresh_token` cookie must too (its `refresh_sessions` rows were cascaded
away with the user).

Both scripts clean up after themselves — login-flow deletes the account
through the Settings UI, account-delete through its own API assertion, and a
safety net calls the endpoint again via login+delete if any step fails
mid-flow. There is no verification path that inspects the database. The **only** exception is `KEEP_ACCOUNT=1`, a debugging mode that
skips cleanup — the throwaway account then stays in the database (still
created and left behind via the API, never touched directly).

> **Note:** the scripts never touch pre-existing accounts — they only create
> and delete the single throwaway user they registered
> (`e2e-<timestamp>@example.com` / `acctdel-<timestamp>@example.com`).

## pytest runs against a dedicated database — safe to run in parallel

The backend pytest integration suite no longer touches the dev database. It
connects to its own dedicated Postgres — the `postgres-test` compose service
(`hybrid_rag_test` on port **5433**) — via the shared `backend/tests/db.py`
helper, whose URL can be overridden with `TEST_DATABASE_URL`.

The suite creates and truncates tables (`users`, `refresh_sessions`, ...) on
that throwaway database only, so **`pytest` and these e2e scripts can run at
the same time** without clobbering each other:

```bash
# Both can run in parallel — they never share a database
cd frontend && npm run e2e:login &
cd ../backend && .venv/Scripts/python -m pytest &
```

Boot the test database once with `docker compose up -d postgres-test`. To point
the suite at any other Postgres (e.g. a CI ephemeral instance), set
`TEST_DATABASE_URL` — see `backend/.env.example`.

## CI

These scripts need a running stack, so they're not part of the unit-test job.
`.github/workflows/e2e.yml` boots `docker compose up -d` (postgres, redis,
qdrant, backend), starts the Vite dev server, runs `npm run e2e:login`, and
runs `npm run e2e:account-delete`, `npm run e2e:redis-fallback`, and
`npm run e2e:redis-fallback-login` as independent
`if: ${{ !cancelled() }}` steps (they need no Chrome or Vite dev server — and
both `redis-fallback*` scripts restore redis themselves if the browser step
failed, so a browser regression can't mask a rate-limiter regression and vice
versa).

`npm run e2e:two-tier` (the two-tier document-model E2E) runs as a further
step, gated on `secrets.GEMINI_API_KEY != ''` — it needs a real LLM key, and
PRs from forks can't access repo secrets. It starts its own Vite instance
(the login step's dev server dies with that step's shell) and drives Chrome
against the same dockerized backend.
