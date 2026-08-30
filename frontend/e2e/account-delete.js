#!/usr/bin/env node
/**
 * Fusion RAG — DELETE /auth/account API smoke test.
 *
 * Pure API assertion (no browser, no Chrome): exercises the account-deletion
 * endpoint end-to-end against a running backend:
 *   1. Registers a throwaway account via POST /auth/register (HTTP 201).
 *   2. Logs in to obtain a Bearer access token (HTTP 200).
 *   3. Calls DELETE /auth/account with the token and the re-entered password:
 *      a wrong password must be rejected (HTTP 401), the correct one must
 *      delete (HTTP 204).
 *   4. Proves the account is gone: re-login with the same credentials must
 *      fail with 401, and a refresh with the stale refresh cookie must too
 *      (sessions were cascaded away with the user).
 *
 * The account is always cleaned up — the endpoint deletes it, and a finally
 * safety net removes it via the same API if any step fails mid-flow. It never
 * touches pre-existing accounts.
 *
 * Usage (from frontend/e2e):
 *   npm run account-delete    # or: node account-delete.js
 *
 * Env overrides:
 *   API_URL          default http://localhost:8000
 *   KEEP_ACCOUNT=1   skip cleanup (debugging)
 *
 * Exit code 0 on success, 1 on any failure. Prints PASS/FAIL per step.
 */
const API_URL = process.env.API_URL || 'http://localhost:8000';
const KEEP_ACCOUNT = process.env.KEEP_ACCOUNT === '1';

const now = Date.now();
const EMAIL = `acctdel-${now}@example.com`;
const PASSWORD = `AcctDelPass!${now}`;

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

/** Remove the account if it still exists (safety net for mid-flow failures). */
async function apiCleanup() {
  try {
    const loginRes = await apiLogin();
    if (!loginRes.ok) return; // nothing left to delete
    const { access_token } = await loginRes.json();
    const del = await fetch(`${API_URL}/api/v1/auth/account`, {
      method: 'DELETE',
      headers: { ...jsonHeaders, Authorization: `Bearer ${access_token}` },
      body: JSON.stringify({ password: PASSWORD }),
    });
    if (del.ok) {
      console.log(`[cleanup] removed leftover account ${EMAIL} via DELETE /auth/account`);
    } else {
      console.error(`[cleanup] WARNING: DELETE returned HTTP ${del.status} — ${EMAIL} may remain`);
    }
  } catch (err) {
    // Log-only: a real check already failed for this run to reach cleanup,
    // so the exit code is already non-zero — count it as noise, not a new
    // failure (a down backend would otherwise double-count register + cleanup).
    console.error(`[cleanup] WARNING: cleanup failed — ${err.message}`);
  }
}

async function main() {
  console.log(`[setup] throwaway account: ${EMAIL}`);
  console.log(`[setup] api=${API_URL}`);

  // ---- 1. Register ----
  const reg = await apiRegister();
  check('register creates account', reg.status === 201, `HTTP ${reg.status}`);
  if (!reg.ok) return;

  // ---- 2. Login (Bearer token + refresh cookie) ----
  const loginRes = await apiLogin();
  const loginBody = await loginRes.json().catch(() => ({}));
  check('login succeeds', loginRes.status === 200, `HTTP ${loginRes.status}`);
  const token = loginBody.access_token;
  check('access token returned', typeof token === 'string' && token.length > 0);
  if (!loginRes.ok || !token) return;

  // ---- 3. Delete (password re-entry required) ----
  const delBody = (password) =>
    fetch(`${API_URL}/api/v1/auth/account`, {
      method: 'DELETE',
      headers: { ...jsonHeaders, Authorization: `Bearer ${token}` },
      body: JSON.stringify({ password }),
    });

  const wrong = await delBody('WrongPassword!');
  check(
    'wrong password rejected: DELETE returns 401',
    wrong.status === 401,
    `HTTP ${wrong.status}`
  );

  // The account must still exist after the rejected attempt
  const stillThere = await apiLogin();
  check(
    'account survives wrong password',
    stillThere.status === 200,
    `HTTP ${stillThere.status}`
  );

  const del = await delBody(PASSWORD);
  check('DELETE /auth/account returns 204', del.status === 204, `HTTP ${del.status}`);
  if (del.status === 204) deleted = true;

  // ---- 4. Account is gone: credentials must be rejected ----
  const relogin = await apiLogin();
  check(
    'account gone: re-login rejected',
    relogin.status === 401,
    `HTTP ${relogin.status}`
  );

  // ---- 5. Sessions cascaded: stale refresh cookie must be rejected ----
  const setCookies =
    typeof loginRes.headers.getSetCookie === 'function'
      ? loginRes.headers.getSetCookie()
      : [];
  const refreshCookie = setCookies.find((c) => c.startsWith('refresh_token='));
  if (refreshCookie) {
    const refresh = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: { ...jsonHeaders, Cookie: refreshCookie.split(';')[0] },
    });
    check(
      'session gone: stale refresh cookie rejected',
      refresh.status === 401,
      `HTTP ${refresh.status}`
    );
  } else {
    check('session gone: stale refresh cookie rejected', false, 'no refresh_token cookie in login response');
  }
}

/**
 * Exit the process with the given code. On Windows, process.exit() while
 * libuv async handles (undici fetch keep-alive) are still closing aborts with
 * a UV_HANDLE_CLOSING assertion and exit 127 — even for code 0. Setting
 * process.exitCode first lets the event loop drain, and the short grace period
 * gives libuv time to finish before process.exit() runs.
 */
function exitWith(code) {
  process.exitCode = code;
  setTimeout(() => process.exit(code), 200);
}

main()
  .catch((err) => {
    console.error('FATAL', err.message);
    failures += 1;
  })
  .finally(async () => {
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
