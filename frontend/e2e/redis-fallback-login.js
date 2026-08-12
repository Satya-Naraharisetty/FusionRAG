#!/usr/bin/env node
/**
 * Hybrid RAG — Redis-down GENERAL-limiter fallback + per-endpoint isolation.
 *
 * Companion to redis-fallback.js. Where that script proves the account-delete
 * limiter's in-memory fallback, this one proves the GENERAL limiter (shared by
 * /auth/login, /auth/register, and chat) enforces its budget with Redis down —
 * and that the shared fallback store isolates per-endpoint budgets.
 *
 * The shared in-memory store in rate_limiter.py is keyed by the config tuple
 * (requests_per_minute, burst), so the general limiter (60 rpm + 10 burst = 70
 * allowed per window) and the strict delete limiter (10 + 0) never share
 * counters. The general limiter identifies unauthenticated traffic by client
 * IP (`ip:<host>`); the delete limiter identifies the authenticated user
 * (`user:<id>`).
 *
 * Why the general limiter is hammered via REGISTER (not login):
 * login verifies an Argon2 hash per attempt (~4-5s on this stack), so a
 * 70-request hammer would span minutes and the 60s sliding window keeps
 * evicting entries before the budget can fill. Re-registering an
 * ALREADY-REGISTERED email returns 400 DUPLICATE_ACCOUNT from the uniqueness
 * check (which runs before any hashing) in ~8ms, so the same general limiter
 * can be exhausted in seconds — the response being 400 instead of 401
 * doesn't change the rate-limit semantics being proven.
 *
 * With Redis DOWN every rate-limited request used to stall ~4s on the failed
 * Redis attempt (blocking the event loop), so even the fast 400 path could
 * not fill the window. rate_limiter.py's Redis-health circuit breaker fixes
 * that: the first failed attempt trips the breaker and subsequent requests
 * skip Redis and hit the shared in-memory store in microseconds — letting
 * the budget fill inside the 60s window.
 *
 * Flow:
 *   1. Registers a throwaway and logs in (Redis up).
 *   2. `docker compose stop redis`.
 *   3. Hammers /auth/register with the throwaway's own email (400
 *      DUPLICATE_ACCOUNT, general limiter, IP-keyed). The register + login
 *      above already used 2 of this IP's 70-budget window, so the exact 429
 *      boundary is 70 - preCount; the check asserts the boundary lands in
 *      [60, 70] — the fallback neither broke early nor let more than the
 *      full budget through.
 *   4. Hammers DELETE /auth/account with a WRONG password (user-keyed, budget
 *      10). The first 10 must still be 401 and the rest 429 — proving the
 *      register hammer did NOT consume the delete budget (per-endpoint
 *      isolation in the shared store).
 *   5. Restarts redis (always, in a finally) and deletes the throwaway with
 *      the correct password.
 *
 * Exit code 0 on success, 1 on failure. Env overrides:
 *   API_URL                     default http://localhost:8000
 *   COMPOSE_PROJECT_NAME        compose project of the running stack
 *                               (CI pins `hybrid_rag`)
 *   RATE_LIMIT_GENERAL_ALLOWED  rpm+burst budget of the general limiter (70)
 *   RATE_LIMIT_GENERAL_LOWER    floor for the 429 boundary (60)
 *   RATE_LIMIT_BUDGET           per-user delete budget (10)
 *   RATE_LIMIT_EXTRA            extra requests past the budgets (2)
 *   KEEP_ACCOUNT=1              skip account cleanup (debugging)
 *
 * Note: the general limiter is IP-keyed, so re-running within ~60s of a
 * previous run against the same long-lived backend can lower the observed
 * boundary. CI always boots a fresh backend; locally, wait a minute between
 * runs (or restart the backend container).
 */
const { sleep, stopRedis, startRedis, runningRedisId, exitWith } = require('./stack');

const API_URL = process.env.API_URL || 'http://localhost:8000';
const KEEP_ACCOUNT = process.env.KEEP_ACCOUNT === '1';
// General limiter: RATE_LIMIT_REQUESTS_PER_MINUTE + RATE_LIMIT_BURST.
const GENERAL_ALLOWED = Number(process.env.RATE_LIMIT_GENERAL_ALLOWED || 70);
// Floor: the 429 boundary must not appear before the rpm part of the budget.
const GENERAL_LOWER = Number(process.env.RATE_LIMIT_GENERAL_LOWER || 60);
const DELETE_BUDGET = Number(process.env.RATE_LIMIT_BUDGET || 10);
const EXTRA = Number(process.env.RATE_LIMIT_EXTRA || 2);

const now = Date.now();
const EMAIL = `rlg-${now}@example.com`;
const PASSWORD = `RlgPass!${now}`;
const WRONG_PASSWORD = `WrongPass!${now}`;

let failures = 0;
let deleted = false;

function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
  if (!ok) failures += 1;
}

const jsonHeaders = { 'Content-Type': 'application/json' };

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
 * backend reconnects to Redis (the in-memory counter from the hammer is
 * abandoned once the limiter is Redis-backed again).
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
  console.log(`[setup] api=${API_URL} general=${GENERAL_ALLOWED} delete=${DELETE_BUDGET} extra=${EXTRA}`);

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

  // Load-bearing guard: with Redis still up, both hammers would hit the
  // Redis-backed limiters, which enforce the SAME budgets — the assertions
  // would pass without ever exercising the in-memory fallback.
  if (!stopped) {
    console.error('[docker] redis still running — cannot exercise the in-memory fallback; skipping hammers');
    return;
  }

  try {
    // The app must keep serving while Redis is down (graceful degradation).
    const liveness = await fetch(`${API_URL}/api/v1/health/liveness`);
    check('backend still healthy with redis down', liveness.status === 200, `HTTP ${liveness.status}`);

    // ---- 3. General-limiter hammer: re-register the existing email (400) ----
    // IP-keyed and shared by register/login/chat. 400 DUPLICATE_ACCOUNT is
    // returned by the uniqueness check BEFORE any Argon2 hashing. With Redis
    // down, the first request trips the rate-limiter's circuit breaker; the
    // rest skip Redis and hit the shared in-memory store in microseconds, so
    // ~70 requests complete within the 60s sliding window and the budget
    // fills. The in-memory store starts empty (the register + login above
    // were served by Redis), so the exact boundary is GENERAL_ALLOWED; the
    // check tolerates a small offset (e.g. a request racing the shutdown that
    // still reached Redis), asserting the first 429 lands in
    // [GENERAL_LOWER, GENERAL_ALLOWED] and everything after stays 429.
    const regCodes = [];
    for (let i = 0; i < GENERAL_ALLOWED + EXTRA; i++) {
      regCodes.push((await apiRegister()).status);
      await sleep(50);
    }
    const first429 = regCodes.indexOf(429);
    const beforeBlock = regCodes.slice(0, first429);
    const fromBlock = regCodes.slice(first429);
    check(
      'general limiter blocks within budget (login/register)',
      first429 >= GENERAL_LOWER && first429 <= GENERAL_ALLOWED,
      `first 429 at request ${first429 + 1} of ${regCodes.length}`
    );
    check(
      'general limiter: duplicate register rejected 400 before the block',
      first429 > 0 && beforeBlock.every((c) => c === 400),
      `codes=${beforeBlock.slice(-4).join(',')}…`
    );
    check(
      'general limiter: stays 429 from the first block on',
      fromBlock.length >= EXTRA && fromBlock.every((c) => c === 429),
      `codes=${fromBlock.join(',')}`
    );

    // ---- 4. Isolation: the delete budget must be untouched ----
    // Different config key (10,0) AND different identifier (user:<id> vs
    // ip:<host>) — the register hammer's 429s must not consume it.
    const deleteCodes = [];
    for (let i = 0; i < DELETE_BUDGET + EXTRA; i++) {
      deleteCodes.push((await apiDelete(token, WRONG_PASSWORD)).status);
      await sleep(50);
    }
    const first = deleteCodes.slice(0, DELETE_BUDGET);
    const rest = deleteCodes.slice(DELETE_BUDGET);
    check(
      'isolation: delete budget intact after register hammer (401 ×budget)',
      first.length === DELETE_BUDGET && first.every((c) => c === 401),
      `codes=${first.join(',')}`
    );
    check(
      'isolation: delete limiter fires on its own budget (429)',
      rest.length === EXTRA && rest.every((c) => c === 429),
      `codes=${rest.join(',')}`
    );
  } finally {
    // ---- 5. Always bring Redis back ----
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

    // ---- 6. Cleanup: delete the throwaway (correct password → 204) ----
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
