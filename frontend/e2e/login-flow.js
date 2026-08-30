#!/usr/bin/env node
/**
 * Fusion RAG — login flow E2E smoke test.
 *
 * Verifies the complete auth path against a running stack (Vite dev server +
 * backend on :8000):
 *   1. Registers a throwaway account via the public API.
 *   2. Browser login: /login -> credentials -> redirected to /chat, user visible.
 *   3. Session persistence: fresh page, no in-memory token, /chat auto-login
 *      via the refresh cookie.
 *   4. Deletes the account through the Settings UI (Data & Privacy -> Delete
 *      Account -> typed-email + re-entered-password confirmation) and proves it
 *      is gone: redirect to /login plus a rejected re-login.
 *   5. Cleanup safety net: if the UI step never deleted the account, deletes
 *      it through the public DELETE /auth/account endpoint (no DB access).
 *
 * Usage (from frontend/e2e):
 *   npm install          # once
 *   npm run login        # or: node login-flow.js
 *
 * Env overrides:
 *   FRONTEND_URL        default http://localhost:5173
 *   API_URL             default http://localhost:8000
 *   CHROME_PATH         default C:/Program Files/Google/Chrome/Application/chrome.exe
 *   KEEP_ACCOUNT=1      skip account cleanup (debugging)
 *
 * Exit code 0 on success, 1 on any failure. Prints PASS/FAIL per step.
 */
const puppeteer = require('puppeteer-core');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const API_URL = process.env.API_URL || 'http://localhost:8000';
const CHROME_PATH =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const KEEP_ACCOUNT = process.env.KEEP_ACCOUNT === '1';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = Date.now();
const EMAIL = `e2e-${now}@example.com`;
const PASSWORD = `E2ePass!${now}`;

let failures = 0;
let uiDeleted = false; // set when the Settings-UI delete flow confirms the account is gone
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
  if (!ok) failures += 1;
}

async function clickButtonByExactText(page, text) {
  return page.$$eval('button', (els, t) => {
    const el = els.find((e) => {
      const cleanText = (e.innerText || e.textContent || '').trim();
      return cleanText === t || cleanText.includes(t);
    });
    if (el) {
      el.click();
      return true;
    }
    return false;
  }, text);
}

async function getButtonState(page, text) {
  return page.$$eval('button', (els, t) => {
    const el = els.find((e) => {
      const cleanText = (e.innerText || e.textContent || '').trim();
      return cleanText === t || cleanText.includes(t);
    });
    if (!el) return null;
    return { disabled: el.disabled };
  }, text);
}

async function getDialogSubmitState(page) {
  return page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) return null;
    const btn = dialog.querySelector('button[type="submit"]');
    if (!btn) return null;
    return { disabled: btn.disabled };
  });
}

async function clickDialogSubmitButton(page) {
  return page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) return false;
    const btn = dialog.querySelector('button[type="submit"]');
    if (!btn) return false;
    btn.click();
    return true;
  });
}

async function dismissOnboardingTour(page) {
  await page.evaluate(() => {
    localStorage.setItem('onboarding-completed', 'true');
    const skipBtn = document.querySelector('button[aria-label="Skip onboarding"]');
    if (skipBtn) {
      skipBtn.click();
    }
  });
}

async function registerUser() {
  const res = await fetch(`${API_URL}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

async function deleteAccount() {
  // Clean up through the public DELETE /auth/account endpoint (Bearer-authenticated),
  // which removes the user and cascades sessions/conversations/documents via the
  // database FK constraints — no docker exec / DB access required.
  const loginRes = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!loginRes.ok) {
    throw new Error(`login for cleanup failed: HTTP ${loginRes.status}`);
  }
  const { access_token } = await loginRes.json();

  const del = await fetch(`${API_URL}/api/v1/auth/account`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${access_token}`,
    },
    body: JSON.stringify({ password: PASSWORD }),
  });
  if (!del.ok) {
    throw new Error(`delete account failed: HTTP ${del.status}`);
  }

  // Prove the account is really gone: the same credentials must now be rejected.
  const relogin = await fetch(`${API_URL}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (relogin.status !== 401) {
    throw new Error(
      `account still exists after delete (re-login returned HTTP ${relogin.status}, expected 401)`
    );
  }
}

async function main() {
  console.log(`[setup] throwaway account: ${EMAIL}`);
  console.log(`[setup] frontend=${FRONTEND_URL} api=${API_URL}`);

  // ---- 1. Register ----
  const reg = await registerUser();
  check('API register creates account', reg.ok, `HTTP ${reg.status}`);

  // Wrap the whole browser phase (launch + checks) so the throwaway user is
  // deleted even if Chrome fails to launch or any check throws.
  try {
    if (reg.ok) {
      const browser = await puppeteer.launch({
        executablePath: CHROME_PATH,
        headless: 'new',
        args: ['--no-sandbox', '--disable-gpu'],
      });
      try {
        // ---- 2. Browser login ----
        const page = await browser.newPage();
        await page.setViewport({ width: 1440, height: 900 });
        const pageErrors = [];
        const consoleErrors = [];
        const failedRequests = [];
        page.on('console', (m) => {
          if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 160));
        });
        page.on('pageerror', (e) => pageErrors.push(e.message.slice(0, 160)));
        page.on('requestfailed', (r) => failedRequests.push(`${r.url().slice(0, 120)} :: ${r.failure()?.errorText || ''}`));

        await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'networkidle2', timeout: 60000 });
        await page.evaluate(() => {
          localStorage.setItem('onboarding-completed', 'true');
        });
        await page.waitForSelector('#login-email', { timeout: 20000 });
        check('login page renders', true);

        await page.type('#login-email', EMAIL);
        await page.type('#login-password', PASSWORD);
        await page.click('button[type="submit"]');
        await sleep(9000);

        const urlAfter = page.url();
        check('login redirects to /chat', urlAfter.includes('/chat'), urlAfter);
        await dismissOnboardingTour(page);

        const bodyText = await page.evaluate(() => document.body.innerText);
        check('no error text on page', !/invalid|error|failed/i.test(bodyText.slice(0, 2000)));
        check('logged-in user visible in sidebar', bodyText.includes(EMAIL));

        const apiCookies = await page.cookies(`${API_URL}/api/v1/auth/refresh`);
        const rc = apiCookies.find((c) => c.name === 'refresh_token');
        check(
          'refresh cookie stored (API path)',
          !!rc,
          rc ? `domain=${rc.domain} path=${rc.path} httpOnly=${rc.httpOnly}` : ''
        );

        // ---- 3. Session persistence (fresh page, same browser context = same cookies) ----
        const page2 = await browser.newPage();
        await page2.setViewport({ width: 1440, height: 900 });
        const errors2 = [];
        const http4xx = [];
        page2.on('console', (m) => { if (m.type() === 'error') errors2.push(m.text().slice(0, 160)); });
        page2.on('pageerror', (e) => errors2.push('PAGEERR: ' + e.message.slice(0, 160)));
        page2.on('response', (r) => { if (r.status() >= 400) http4xx.push(`${r.status()} ${r.url().slice(0, 100)}`); });

        await page2.goto(`${FRONTEND_URL}/chat`, { waitUntil: 'networkidle2', timeout: 60000 });
        await sleep(9000);
        await dismissOnboardingTour(page2);
        const url2 = page2.url();
        const text2 = await page2.evaluate(() => document.body.innerText);

        check('session persists: stays on /chat', !url2.includes('/login'), url2);
        check('session persists: user visible', text2.includes(EMAIL));
        check('session persists: no console errors', errors2.length === 0, errors2.slice(0, 2).join(' | '));
        check('session persists: no 4xx/5xx', http4xx.length === 0, http4xx.slice(0, 2).join(' | '));

        check('login attempt: no failed requests', failedRequests.length === 0, failedRequests.slice(0, 2).join(' | '));

        // On a logged-out boot, the app probes /auth/me without a token; that
        // expected 401 shows up in the browser console as a resource-load error
        // and is how the app decides to show the login page. Ignore that exact
        // pattern; any other console error is a real failure.
        const realConsoleErrors = consoleErrors.filter(
          (t) => !/Failed to load resource: the server responded with a status of 401/.test(t)
        );
        check('login attempt: no unexpected console errors', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));
        check('login attempt: no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));

        // ---- 4. Delete the account via the Settings UI ----
        // Drives the real Settings -> Data & Privacy -> Delete Account flow,
        // including the typed-email + re-entered-password confirmation gate,
        // then proves the account is gone (redirect to /login + rejected
        // re-login). On success the account is already deleted, so the API
        // cleanup in the outer finally becomes a no-op safety net.
        const uiPage = await browser.newPage();
        await uiPage.setViewport({ width: 1440, height: 900 });
        const uiErrors = [];
        const uiPageErrors = [];
        uiPage.on('console', (m) => { if (m.type() === 'error') uiErrors.push(m.text().slice(0, 160)); });
        uiPage.on('pageerror', (e) => uiPageErrors.push('PAGEERR: ' + e.message.slice(0, 160)));

        await uiPage.goto(`${FRONTEND_URL}/settings`, { waitUntil: 'networkidle2', timeout: 60000 });
        await sleep(3000);
        await dismissOnboardingTour(uiPage);
        const settingsTitle = await uiPage.evaluate(() => document.querySelector('h1')?.textContent || '');
        check('settings page renders', settingsTitle.includes('Settings'), settingsTitle);

        check('Data & Privacy tab opens', await clickButtonByExactText(uiPage, 'Data & Privacy'));
        await sleep(1500);

        check('delete dialog opens', await clickButtonByExactText(uiPage, 'Delete'));
        await uiPage.waitForSelector('#delete-account-confirm-email', { timeout: 10000 }).catch(() => { });
        check('dialog email input present', !!(await uiPage.$('#delete-account-confirm-email')));

        let confirmState = await getDialogSubmitState(uiPage);
        check('confirm disabled initially', !!confirmState && confirmState.disabled === true);

        await uiPage.type('#delete-account-confirm-email', 'wrong@example.com');
        confirmState = await getDialogSubmitState(uiPage);
        check('confirm stays disabled with wrong email', !!confirmState && confirmState.disabled === true);

        // Select-all + replace with the exact account email
        await uiPage.click('#delete-account-confirm-email', { clickCount: 3 });
        await uiPage.type('#delete-account-confirm-email', EMAIL);
        confirmState = await getDialogSubmitState(uiPage);
        check('confirm stays disabled until password entered', !!confirmState && confirmState.disabled === true);

        await uiPage.type('#delete-account-confirm-password', PASSWORD);
        confirmState = await getDialogSubmitState(uiPage);
        check('confirm enabled with matching email + password', !!confirmState && confirmState.disabled === false);

        check('delete confirmed', await clickDialogSubmitButton(uiPage));
        let redirectedToLogin = false;
        for (let i = 0; i < 30; i++) {
          if (uiPage.url().includes('/login')) { redirectedToLogin = true; break; }
          await sleep(500);
        }
        check('redirected to /login after deletion', redirectedToLogin, uiPage.url());

        // Definitive proof the account is gone: the same credentials are rejected
        const relogin = await fetch(`${API_URL}/api/v1/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
        });
        check('API login rejected after deletion', relogin.status === 401, `HTTP ${relogin.status}`);
        if (relogin.status === 401) uiDeleted = true;

        const uiConsoleErrors = uiErrors.filter(
          (t) => !/Failed to load resource: the server responded with a status of 401/.test(t)
        );
        check('delete flow: no unexpected console errors', uiConsoleErrors.length === 0, uiConsoleErrors.slice(0, 2).join(' | '));
        check('delete flow: no uncaught page errors', uiPageErrors.length === 0, uiPageErrors.slice(0, 2).join(' | '));
      } finally {
        await browser.close();
      }
    }
  } finally {
    // ---- 4. Cleanup (always, even on launch failure or thrown check) ----
    // Only attempt cleanup when the account was actually registered; otherwise
    // a register failure would cascade into a spurious cleanup failure too.
    if (KEEP_ACCOUNT) {
      console.log('[cleanup] KEEP_ACCOUNT=1 set, leaving account in DB');
    } else if (reg.ok) {
      if (uiDeleted) {
        console.log('[cleanup] account already deleted via the Settings UI — API cleanup skipped');
      } else {
        try {
          await deleteAccount();
          console.log(`[cleanup] deleted throwaway user ${EMAIL} (and cascaded sessions)`);
        } catch (e) {
          console.error(`[cleanup] WARNING: could not delete ${EMAIL} — ${e.message}`);
          failures += 1;
        }
      }
    }
  }

  console.log(failures === 0 ? '\nRESULT: ALL CHECKS PASSED' : `\nRESULT: ${failures} CHECK(S) FAILED`);
  return failures === 0 ? 0 : 1;
}

/**
 * Exit the process with the given code.
 *
 * On Windows, calling process.exit() while libuv async handles are still
 * closing (e.g. undici's fetch keep-alive connections used by deleteAccount)
 * aborts the process with a UV_HANDLE_CLOSING assertion and exit code 127 —
 * even when the requested code is 0. Setting process.exitCode first lets the
 * event loop drain naturally, and the short grace period gives libuv time to
 * finish closing handles before process.exit() runs.
 */
function exitWith(code) {
  process.exitCode = code;
  setTimeout(() => process.exit(code), 200);
}

main()
  .then((code) => exitWith(code))
  .catch((e) => {
    console.error('FATAL', e.message);
    exitWith(1);
  });
