#!/usr/bin/env node
/**
 * Fusion RAG — Redis-down rate-limit fallback smoke test.
 *
 * Pure API + docker-compose orchestration (no browser, no Chrome): proves the
 * in-memory rate-limit fallback actually enforces limits when Redis is
 * unreachable. The fallback lives in `backend/app/core/security/rate_limiter.py`
 * as a module-level shared store, so counters persist across the per-request
 * limiter instances even though no Redis is involved.
 *
 * Flow:
 *   1. Registers a throwaway account and logs in (while Redis is up, so the
 *      signup/login rate-limiters are exercised on their normal path).
 *   2. `docker compose stop redis` — the backend then falls back to the shared
 *      in-memory store for every rate-limited endpoint.
 *   3. Hammers DELETE /auth/account with a WRONG password for
 *      (budget + extra) sequential requests. The account-delete limiter allows
 *      exactly `budget` (default 10) per minute, so the first `budget` must be
 *      rejected with 401 (wrong password) and every request after that must be
 *      rejected with 429 (rate limited) — the fallback is the only thing that
 *      can produce that 429.
 *   4. `docker compose start redis` and waits for the backend to recover.
 *   5. Deletes the throwaway account via the API (with retries on 429, in case
 *      the limiter is mid-recovery) and proves the credentials are rejected
 *      afterwards.
 *
 * The script ALWAYS restarts Redis in a `finally` block, even when a check
 * fails, so it never leaves CI (or a dev machine) with Redis down. The
 * throwaway account is cleaned up through the same API as account-delete.js.
 *
 * Usage (from frontend/e2e):
 *   node redis-fallback.js
 *
 * Env overrides:
 *   API_URL                default http://localhost:8000
 *   COMPOSE_PROJECT_NAME   compose project of the running stack (CI pins this
 *                          to `fusion_rag`; local defaults to the repo dir
 *                          name, which docker compose derives itself)
 *   RATE_LIMIT_BUDGET      expected per-user delete budget (default 10)
 *   RATE_LIMIT_EXTRA       extra requests sent past the budget (default 2)
 *   KEEP_ACCOUNT=1         skip account cleanup (debugging)
 *
 * Requires: docker compose with access to the running stack (the script stops
 * and restarts the `redis` service). Exit code 0 on success, 1 on failure.
 */
const { sleep, stopRedis, startRedis, runningRedisId, exitWith } = require('./stack');

const API_URL = process.env.API_URL || 'http://localhost:8000';
const KEEP_ACCOUNT = process.env.KEEP_ACCOUNT === '1';
const BUDGET = Number(process.env.RATE_LIMIT_BUDGET || 10);
const EXTRA = Number(process.env.RATE_LIMIT_EXTRA || 2);

const now = Date.now();
const EMAIL = `rlf-${now}@example.com`;
const PASSWORD = `RlfPass!${now}`;
const WRONG_PASSWORD = `WrongPass!${now}`;

let failures = 0;
let deleted = false;

function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
  if (!ok) failures += 1;
}

const jsonHeaders = { 'Content-Type': 'application/json' };

/* ── API helpers ────────────────────────────────────────────────────────── */

async function apiRegister() {
  return fetch(`${API_URL}/api/v1/auth/register`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
}

async function apiLogin() {
  return fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
}

async function apiDelete(token, password) {
  return fetch(`${API_URL}/api/v1/auth/account`, {
    method: 'DELETE',
    headers: { ...jsonHeaders, Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password }),
  });
}

/**
 * Delete the account with the correct password, retrying on 429 while the
 * backend reconnects to Redis. The delete limiter's in-memory counter may
 * still be exhausted from the hammer; once the limiter is Redis-backed again
 * a fresh budget applies, so 429 means "still recovering" here.
 */
async function deleteWithRetry(token) {
  for (let attempt = 0; attempt < 6; attempt++) {
    const del = await apiDelete(token, PASSWORD);
    if (del.status === 204 || del.status !== 429) return del.status;
    await sleep(2000);
  }
  return 429;
}

/** Remove the throwaway account once Redis is back (safety net). */
async function apiCleanup() {
  try {
    const loginRes = await apiLogin();
    if (!loginRes.ok) return; // nothing left to delete
    const { access_token } = await loginRes.json();
    const status = await deleteWithRetry(access_token);
    if (status === 204) {
      console.log(`[cleanup] removed leftover account ${EMAIL} via DELETE /auth/account`);
    } else {
      console.error(`[cleanup] WARNING: DELETE returned HTTP ${status} — ${EMAIL} may remain`);
    }
  } catch (err) {
    // Log-only: a real check already failed for this run to reach cleanup.
    console.error(`[cleanup] WARNING: cleanup failed — ${err.message}`);
  }
}

async function main() {
  console.log(`[setup] throwaway account: ${EMAIL}`);
  console.log(`[setup] api=${API_URL} budget=${BUDGET} extra=${EXTRA}`);

  // ---- 1. Register + login (Redis still up) ----
  const reg = await apiRegister();
  check('register creates account', reg.status === 201, `HTTP ${reg.status}`);
  if (!reg.ok) return;

  const loginRes = await apiLogin();
  const loginBody = await loginRes.json().catch(() => ({}));
  check('login succeeds', loginRes.status === 200, `HTTP ${loginRes.status}`);
  const token = loginBody.access_token;
  check('access token returned', typeof token === 'string' && token.length > 0);
  if (!loginRes.ok || !token) return;

  // ---- 2. Stop Redis; the backend falls back to the shared in-memory store ----
  const stopped = await stopRedis();
  check('redis is stopped', stopped);

  // Load-bearing guard: with Redis still up, the hammer would hit the
  // Redis-backed limiter, which enforces the SAME budget — the 401/429
  // assertions would pass without ever exercising the in-memory fallback.
  // Bail out (the outer finally still cleans up the account).
  if (!stopped) {
    console.error('[docker] redis still running — cannot exercise the in-memory fallback; skipping hammer');
    return;
  }

  try {
    // The app must keep serving while Redis is down (graceful degradation).
    const liveness = await fetch(`${API_URL}/api/v1/health/liveness`);
    check(
      'backend still healthy with redis down',
      liveness.status === 200,
      `HTTP ${liveness.status}`
    );

    // ---- 3. Hammer DELETE /auth/account with a wrong password ----
    // Sequential on purpose: the sliding-window counter must see every request
    // in order. First `budget` pass the limiter and fail on the password (401);
    // every request past the budget must be rejected by the limiter itself
    // (429) — proof the in-memory fallback actually enforces the limit.
    const codes = [];
    for (let i = 0; i < BUDGET + EXTRA; i++) {
      const res = await apiDelete(token, WRONG_PASSWORD);
      codes.push(res.status);
      await sleep(50);
    }
    const first = codes.slice(0, BUDGET);
    const rest = codes.slice(BUDGET);
    check(
      `wrong password rejected ${BUDGET}× before the budget`,
      first.length === BUDGET && first.every((c) => c === 401),
      `codes=${first.join(',')}`
    );
    check(
      `rate limit enforced after the budget (${EXTRA}× 429)`,
      rest.length === EXTRA && rest.every((c) => c === 429),
      `codes=${rest.join(',')}`
    );
  } finally {
    // ---- 4. Always bring Redis back ----
    const pingOk = await startRedis();
    check('redis healthy again', pingOk);

    if (!pingOk) {
      // Can't trust the API while Redis is down — surface it and bail.
      return;
    }

    // Give the backend a moment to reconnect before the cleanup login.
    for (let i = 0; i < 15; i++) {
      try {
        const probe = await fetch(`${API_URL}/api/v1/health/liveness`);
        if (probe.status === 200) break;
      } catch {
        /* backend restarting */
      }
      await sleep(1000);
    }

    // ---- 5. Cleanup: delete the throwaway (correct password → 204) ----
    if (KEEP_ACCOUNT) {
      console.log('[cleanup] KEEP_ACCOUNT=1 set, leaving account in DB');
      return;
    }
    const delStatus = await deleteWithRetry(token);
    check('cleanup delete returns 204 after redis restart', delStatus === 204, `HTTP ${delStatus}`);
    if (delStatus === 204) {
      deleted = true;
      const relogin = await apiLogin();
      check('account gone: re-login rejected', relogin.status === 401, `HTTP ${relogin.status}`);
    }
  }
}

main()
  .catch((err) => {
    console.error('FATAL', err.message);
    failures += 1;
  })
  .finally(async () => {
    // Safety net: if Redis is somehow still down (e.g. an unexpected throw
    // between stop and the inner finally), bring it back before anything else.
    if (runningRedisId() === '') {
      console.error('[cleanup] redis still down — restarting');
      try {
        await startRedis();
      } catch {
        console.error('[cleanup] WARNING: could not restart redis');
      }
    }
    if (!KEEP_ACCOUNT && !deleted) {
      await apiCleanup();
    }
    console.log(
      failures === 0
        ? '\nRESULT: ALL CHECKS PASSED'
        : `\nRESULT: ${failures} CHECK(S) FAILED`
    );
    exitWith(failures === 0 ? 0 : 1);
  });
