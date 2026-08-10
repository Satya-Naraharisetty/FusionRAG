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

## Prerequisites

- The stack is running:
  - Vite dev server on `http://localhost:5173` (`cd frontend && npm run dev`)
  - Dockerized backend on `http://localhost:8000` (`docker compose up -d`)
- For the browser test only: Google Chrome installed (the script drives the
  installed Chrome via `puppeteer-core`; it does not download a browser).

## Run

```bash
cd frontend
npm run e2e:login           # browser login flow + session persistence
npm run e2e:account-delete  # DELETE /auth/account API assertion
```

Both scripts exit `0` when every check passes and `1` on any failure, so they
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

## Configuration (env vars)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FRONTEND_URL` | `http://localhost:5173` | Vite dev server origin (login flow) |
| `API_URL` | `http://localhost:8000` | Backend origin (both scripts) |
| `CHROME_PATH` | `C:/Program Files/Google/Chrome/Application/chrome.exe` | Path to Chrome binary (login flow) |
| `KEEP_ACCOUNT=1` | unset | Skip account cleanup (debugging) |

Example with overrides:

```bash
FRONTEND_URL=http://localhost:5173 API_URL=http://localhost:8000 npm run e2e:login
API_URL=http://localhost:8000 npm run e2e:account-delete
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

## Don't run pytest and the e2e scripts against the same dev database in parallel

The backend integration tests point their fixtures at the **same** local
Dockerized Postgres the e2e scripts use
(`TEST_DATABASE_URL = postgresql://postgres:postgres@localhost:5432/hybrid_rag`)
and **truncate tables before each test** — e.g. the `test_db` / `chat_test_db`
fixtures run `TRUNCATE TABLE users CASCADE` (plus `refresh_sessions`, and
conversations/documents in some files).

Running `pytest` while an e2e script is mid-flow will therefore **delete the
throwaway account the e2e script just registered**, producing confusing
failures such as *"register returned 201 but login returned 401"*. Run them
**sequentially** — never in parallel against the same database:

```bash
# OK — one after the other
cd frontend && npm run e2e:login
cd ../backend && python -m pytest      # only after the e2e script has finished
# (on Windows this repo runs the suite via .venv/Scripts/python -m pytest)

# NOT OK — these race on the same users table
#   cd frontend && npm run e2e:login &   (bad)
#   cd backend  && python -m pytest &    (bad)
```

For local development the cleanest setup is a dedicated database for pytest
(e.g. point `TEST_DATABASE_URL` at its own Postgres instance) so the two never
share one. CI is unaffected: `.github/workflows/e2e.yml` runs only the e2e
scripts against a fresh containerized stack.

## CI

These scripts need a running stack, so they're not part of the unit-test job.
`.github/workflows/e2e.yml` boots `docker compose up -d` (postgres, redis,
qdrant, backend), starts the Vite dev server, runs `npm run e2e:login`, and
runs `npm run e2e:account-delete` as an independent
`if: ${{ !cancelled() }}` step (it needs no Chrome or Vite dev server).
