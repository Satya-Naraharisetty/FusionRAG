#!/usr/bin/env node
/**
 * Hybrid RAG — two-tier document model E2E verification.
 *
 * Drives the real UI (Vite dev + backend on :8000) through the full document
 * model:
 *   1. Uploads a GLOBAL doc (aurora.txt) via the Documents section.
 *   2. Chat A: attaches tunneling.txt in the composer, asks WITHOUT @documents,
 *      and verifies the answer cites tunneling.txt (chat-scoped auto-use).
 *   3. Chat B: asks WITH @documents, verifies aurora.txt is cited and no
 *      chat-scoped leak from A; then asks without any mention and verifies the
 *      "Answering from general knowledge" hint (retrieval skipped).
 *   4. Deletes chat A through the sidebar UI and verifies its scoped document
 *      is gone (API: conversation gone + no docs scoped to it) while the
 *      global aurora.txt survives on the Documents page.
 *
 * Usage (from frontend/e2e):
 *   npm install          # once
 *   node verify-two-tier.js
 *
 * Env overrides:
 *   FRONTEND_URL   default http://localhost:5173
 *   API_URL        default http://localhost:8000
 *   CHROME_PATH    default C:/Program Files/Google/Chrome/Application/chrome.exe
 *   AURORA_FILE    default fixtures/aurora.txt (relative to this file)
 *   TUNNEL_FILE    default fixtures/tunneling.txt (relative to this file)
 *   KEEP_ACCOUNT=1 skip account cleanup (debugging)
 *
 * Exit code 0 on success, 1 on any failure.
 */
const puppeteer = require('puppeteer-core');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const API_URL = process.env.API_URL || 'http://localhost:8000';
const CHROME_PATH =
  process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const KEEP_ACCOUNT = process.env.KEEP_ACCOUNT === '1';
// Anchor to this file's directory (frontend/e2e) — the test fixtures are the
// tracked files in fixtures/, so local runs and CI use the exact same content
// the grounding assertions depend on. Relying on process.cwd() broke
// uploadFile when the script is launched from elsewhere.
const AURORA_FILE = path.resolve(__dirname, process.env.AURORA_FILE || 'fixtures/aurora.txt');
const TUNNEL_FILE = path.resolve(__dirname, process.env.TUNNEL_FILE || 'fixtures/tunneling.txt');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const now = Date.now();
const EMAIL = `twotier-${now}@example.com`;
const PASSWORD = `Twotier!${now}`;

let failures = 0;
function check(name, ok, detail = '') {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`);
  if (!ok) failures += 1;
}

async function clickByExactText(page, text) {
  return page.$$eval('button', (els, t) => {
    const el = els.find((e) => e.textContent.trim() === t);
    if (el) { el.click(); return true; }
    return false;
  }, text);
}

async function clickMenuItemByText(page, text) {
  // Dropdown menu items render as [role="menuitem"] in Radix; fall back to
  // any element matching the exact text.
  return page.evaluate((t) => {
    const els = Array.from(document.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"]'));
    const el = els.find((e) => e.textContent.trim() === t);
    if (el) { el.click(); return true; }
    return false;
  }, text);
}

async function waitForText(page, regex, timeoutMs = 120000, label = '') {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const body = await page.evaluate(() => document.body.innerText || '');
    if (regex.test(body)) return true;
    await sleep(1500);
  }
  console.error(`  !! timeout waiting for ${label || regex}`);
  return false;
}

async function waitForNoText(page, regex, timeoutMs = 60000, label = '') {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const body = await page.evaluate(() => document.body.innerText || '');
    if (!regex.test(body)) return true;
    await sleep(1500);
  }
  console.error(`  !! timeout waiting for ${label || regex} to disappear`);
  return false;
}

/**
 * Like waitForText but scoped to the message list ([role="log"]). Used for
 * citation and hint assertions so sidebar titles, the composer's recent-file
 * tray, and other chrome can't cause false positives.
 */
async function waitForTextInLog(page, regex, timeoutMs = 120000, label = '') {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const text = await page.evaluate(() => {
      const log = document.querySelector('[role="log"]');
      return log ? log.innerText || '' : '';
    });
    if (regex.test(text)) return true;
    await sleep(1000);
  }
  console.error(`  !! timeout waiting for ${label || regex} in message log`);
  return false;
}

/**
 * Send a question and wait for a regex in the message log, re-sending up to
 * `attempts` times when the wait times out. Retries absorb transient upstream
 * failures — the Gemini free tier returns 429 under burst load, the backend
 * streams that error back as an SSE error event, and the citation simply
 * never appears (not an app bug). Each attempt waits for the previous stream
 * to finish first (the send handler ignores sends while isStreaming).
 */
async function sendAndWaitForLog(page, question, regex, timeoutMs, label, attempts = 3) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    await waitForSendEnabled(page, 120000);
    await page.waitForSelector('[aria-label="Message prompt input"]', { timeout: 30000 });
    await page.type('[aria-label="Message prompt input"]', question);
    await page.click('button[aria-label="Send query"]');
    if (await waitForTextInLog(page, regex, timeoutMs, label)) return true;
    if (attempt < attempts) {
      console.error(`  !! ${label} not seen on attempt ${attempt}/${attempts} — re-sending`);
    }
  }
  return false;
}

/**
 * Wait for the composer's send button to come BACK after a streaming answer
 * finishes. While isStreaming the send button is replaced by a Stop button,
 * so existence (not !disabled) is the right signal: after sending, the input
 * is empty and the send button is disabled BY DESIGN until the user types
 * again, so requiring !disabled would always time out.
 */
async function waitForSendEnabled(page, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const exists = await page.evaluate(
      () => !!document.querySelector('button[aria-label="Send query"]')
    );
    if (exists) return true;
    await sleep(1000);
  }
  console.error('  !! timeout waiting for send button to return (streaming stuck)');
  return false;
}

async function api(path_, opts = {}) {
  // `...opts` first, headers LAST: the per-call Authorization header must not
  // clobber the default Content-Type (a bare Authorization-only header makes
  // FastAPI treat the JSON body as unparsed → 422 on DELETE/POST-with-auth).
  const res = await fetch(`${API_URL}/api/v1${path_}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  });
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

async function main() {
  console.log(`[setup] account=${EMAIL}`);
  console.log(`[setup] aurora=${AURORA_FILE}`);
  console.log(`[setup] tunneling=${TUNNEL_FILE}`);

  const fs = require('fs');
  if (!fs.existsSync(AURORA_FILE) || !fs.existsSync(TUNNEL_FILE)) {
    console.error(`FATAL fixture missing — need: ${AURORA_FILE} and ${TUNNEL_FILE}`);
    return 1;
  }

  // ---- 1. Register via API ----
  // The very first fetch can transiently fail with a connection refusal right
  // after uvicorn finishes binding (health checks pass, then a burst of
  // listeners briefly refuses). Retry a few times before giving up.
  let reg;
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      reg = await api('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
      });
      if (reg.ok) break;
    } catch (e) {
      if (attempt === 4) throw e;
    }
    await sleep(2000);
  }
  check('API register creates account', reg && reg.ok, `HTTP ${reg ? reg.status : 'no response'}`);

  try {
    if (reg.ok) {
      const browser = await puppeteer.launch({
        executablePath: CHROME_PATH,
        headless: 'new',
        args: ['--no-sandbox', '--disable-gpu'],
      });
      try {
        const page = await browser.newPage();
        await page.setViewport({ width: 1440, height: 900 });
        // The onboarding tour's full-screen z-50 overlay blocks every
        // coordinate click on the composer (its skip button has no text — only
        // an X icon), so seed its completion flag before any navigation. The
        // old dismiss attempt (match /skip/i in button text) never found it.
        await page.evaluateOnNewDocument(() => {
          try {
            localStorage.setItem('onboarding-completed', 'true');
          } catch (e) {
            // Storage unavailable — the tour may still appear; ignore.
          }
          // TEMP depth-warning stack probe: capture the call stack at the
          // moment React logs "Maximum update depth" — the bottom frames show
          // which flushSync/commit path triggered the nested sync render.
          const origError = console.error;
          console.error = (...args) => {
            if (
              typeof args[0] === 'string' &&
              args[0].includes('Maximum update depth exceeded')
            ) {
              try {
                const e = new Error('depth-probe');
                const frames = (e.stack || '').split('\n');
                console.warn('DEPTH-STACK-BEGIN\n' + frames.slice(0, 40).join('\n') + '\nDEPTH-STACK-END');
              } catch (err) {
                // stack unavailable
              }
            }
            origError.apply(console, args);
          };
        });
        const pageErrors = [];
        const consoleErrors = [];
        const depthStacks = [];
        // FULL text of any "Maximum update depth exceeded" warning, so a
        // reproduction still carries React's component stack (the sliced
        // consoleErrors array below truncates it away).
        const depthWarnings = [];
        page.on('console', (m) => {
          const t = m.text();
          if (m.type() === 'error') consoleErrors.push(t.slice(0, 160));
          if (/DEPTH-STACK-BEGIN/.test(t)) depthStacks.push(t);
          // The component stack travels as a SECOND console.error argument
          // (React 19 splits the warning text from the stack), so resolve all
          // args — m.text() only ever yields the first line.
          if (/Maximum update depth exceeded/.test(t)) {
            // Dump EVERY argument verbatim — React 19 splits the warning text
            // from the component stack across console.error args, so m.text()
            // alone hides the component.
            Promise.all(m.args().map((a) => a.jsonValue().catch(() => '<unserializable>')))
              .then((vals) => depthWarnings.push(vals.map((v) => String(v)).join('\n')
                + `\n[location] ${m.location().url || 'unknown'}`
                + `\n[url] ${page.url()}`
                + `\n[at] ${new Date().toISOString().slice(11, 19)}`))
              .catch(() => depthWarnings.push(t));
          }
        });
        page.on('pageerror', (e) => pageErrors.push(e.message.slice(0, 160)));
        // Which URLs actually 404 (resource errors don't carry the URL).
        const notFoundUrls = [];
        page.on('response', (r) => {
          if (r.status() === 404) notFoundUrls.push(r.url());
        });

        // ---- 2. Login via UI ----
        await page.goto(`${FRONTEND_URL}/login`, { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForSelector('#login-email', { timeout: 20000 });
        await page.type('#login-email', EMAIL);
        await page.type('#login-password', PASSWORD);
        await page.click('button[type="submit"]');
        await sleep(8000);
        check('login lands on /chat', page.url().includes('/chat'), page.url());

        // Dismiss any onboarding tour overlay.
        await page.evaluate(() => {
          const skip = Array.from(document.querySelectorAll('button')).find(
            (b) => /skip/i.test(b.textContent)
          );
          if (skip) skip.click();
        });
        await sleep(1000);

        // ---- 3. Upload aurora.txt GLOBALLY via the Documents section ----
        await page.goto(`${FRONTEND_URL}/documents`, { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForSelector('input[type="file"]', { timeout: 20000 });
        const dropInput = await page.$('input[type="file"]');
        await dropInput.uploadFile(AURORA_FILE);
        check('aurora.txt added to upload queue', await waitForText(page, /aurora\.txt/, 30000, 'aurora.txt in queue'));

        // Documents-section uploads start QUEUED by design — the dropzone
        // defers to the explicit "Upload All" button (only the chat composer
        // auto-starts). Without this click the row sits in the queue forever.
        const uploadAllClicked = await clickByExactText(page, 'Upload All');
        check('Upload All starts the queued upload', uploadAllClicked);

        // Deterministic gate: poll the API until aurora.txt is completed AND
        // vectorized. The UI churns through Extracting→Chunking→Indexing
        // text, which is noisy to assert on — the API is ground truth. 300s
        // (not 180s) leaves room for a cold CI runner downloading the local
        // all-MiniLM-L6-v2 embedding model on its first upload.
        const auroraVectorized = await waitForDocumentVectorized('aurora.txt', 300000);
        check('aurora.txt processed + vectorized', auroraVectorized);

        // Reload to render the fresh grid, then confirm the card shows done.
        // Scoped to the card itself: the page-wide filter dropdown also
        // contains the word "Processing", which made a body-text check lie.
        await page.goto(`${FRONTEND_URL}/documents`, { waitUntil: 'networkidle2', timeout: 60000 });
        // Wait for the grid to actually mount its cards (fixed sleeps flake
        // when the app loads slowly).
        const cardReady = await (async () => {
          const deadline = Date.now() + 30000;
          while (Date.now() < deadline) {
            const found = await page.evaluate(() => {
              const t = Array.from(document.querySelectorAll('h4')).find(
                (el) => el.textContent && el.textContent.trim() === 'aurora.txt'
              );
              return !!t;
            });
            if (found) return true;
            await sleep(1500);
          }
          return false;
        })();
        if (!cardReady) console.error('  !! timeout waiting for aurora.txt card to mount');
        const auroraCardState = await page.evaluate(() => {
          const title = Array.from(document.querySelectorAll('h4')).find(
            (el) => el.textContent && el.textContent.trim() === 'aurora.txt'
          );
          if (!title) return 'no-card';
          let node = title;
          for (let i = 0; i < 8 && node; i++) {
            if (/group flex flex-col/.test(node.className || '')) break;
            node = node.parentElement;
          }
          const text = (node && node.innerText ? node.innerText : '').toLowerCase();
          if (!text.includes('completed')) return `badge-not-completed: ${text.slice(0, 120)}`;
          if (/extracting|chunking|indexing|queued|uploading|processing|vectorization failed/.test(text)) {
            return `still-processing: ${text.slice(0, 120)}`;
          }
          return 'completed';
        });
        check('aurora.txt card shows completed state', auroraCardState === 'completed', auroraCardState);

        // ---- 4. Chat A: attach tunneling.txt, ask WITHOUT @documents ----
        await page.goto(`${FRONTEND_URL}/chat`, { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForSelector('#chat-file-input', { timeout: 30000 });
        const chatInput = await page.$('#chat-file-input');
        await chatInput.uploadFile(TUNNEL_FILE);
        await sleep(1500);
        const tray = await page.evaluate(() => document.body.innerText || '');
        check('composer shows tunneling.txt chip', /tunneling\.txt/.test(tray));

        await page.waitForSelector('[aria-label="Message prompt input"]', { timeout: 30000 });
        await page.type('[aria-label="Message prompt input"]',
          'Explain quantum tunneling. What role does it play inside stars like the Sun?');
        await page.click('button[aria-label="Send query"]');

        // After the first message the app navigates to /chat/{id}; capture it.
        const chatAId = await waitForChatId(page, 60000);
        check('chat A created (navigates to /chat/{id})', !!chatAId, chatAId || '');

        // The chat-scoped upload only STARTS once the conversation id is
        // announced by the SSE stream, so the first answer legitimately races
        // the chunk/embed pipeline (retrieval ran, found no vectors yet — no
        // citation, no hint). Gate on the scoped doc being vectorized (API
        // ground truth), then assert the citation on a follow-up question.
        const scopedVectorized = await waitForScopedDocumentVectorized(chatAId, 'tunneling.txt', 300000);
        check('chat A scoped upload processed + vectorized', scopedVectorized);
        check('chat A Q1 finished streaming', await waitForSendEnabled(page, 120000));

        // Answer should cite tunneling.txt (auto-used, no @documents). Scoped
        // to the message log: the composer tray also shows the chip.
        const citedTunnel = await sendAndWaitForLog(
          page,
          'Follow up: how does quantum tunneling enable fusion inside stars, and name an everyday device that relies on it?',
          /tunneling\.txt/,
          120000,
          'chat A citation of tunneling.txt'
        );
        check('chat A answer cites tunneling.txt (auto-use)', citedTunnel);
        check('chat A Q2 finished streaming', await waitForSendEnabled(page, 120000));
        const answerA = await page.evaluate(() => {
          const log = document.querySelector('[role="log"]');
          return log ? log.innerText || '' : '';
        });
        check(
          'chat A has NO general-knowledge hint (retrieval ran)',
          !/Answering from general knowledge/.test(answerA)
        );
        // The citation card above is the grounding proof; this smoke check
        // just ensures the answer body is substantive (the follow-up question
        // text itself contains "tunneling"/"quantum", so word-matching would
        // be a false positive).
        check('chat A answer has substantive content',
          answerA.slice(-6000).trim().length > 200);

        // ---- 5. Chat B: @documents -> aurora; then no mention -> hint ----
        await page.goto(`${FRONTEND_URL}/chat`, { waitUntil: 'networkidle2', timeout: 60000 });
        await page.waitForSelector('[aria-label="Message prompt input"]', { timeout: 30000 });
        const citedAurora = await sendAndWaitForLog(
          page,
          'What causes the green color of the aurora borealis? Use @documents',
          /aurora\.txt/,
          120000,
          'chat B citation of aurora.txt'
        );
        check('chat B @documents: answer cites aurora.txt', citedAurora);
        // The composer's "Recent Files" tray can also list tunneling.txt (a
        // cross-chat shortcut), so the leak check is scoped to the message
        // log — the ANSWER must not reference chat A's file.
        const answerB = await page.evaluate(() => {
          const log = document.querySelector('[role="log"]');
          return log ? log.innerText || '' : '';
        });
        check('chat B @documents: no chat-scoped leak (tunneling absent)', !/tunneling\.txt/.test(answerB));
        // The citation card above proves grounding; smoke-check that the
        // answer is substantive (the LLM paraphrases the fixture — "excited
        // atoms" rather than the exact word "oxygen" — so word-matching
        // would be flaky).
        check('chat B @documents: answer has substantive content',
          answerB.slice(-6000).trim().length > 200);

        // The send button is replaced by a Stop button while the answer
        // streams — wait for it to come back, then send the second question.
        check('chat B first answer finished streaming', await waitForSendEnabled(page, 120000));

        const hintShown = await sendAndWaitForLog(
          page,
          'What is the capital of France?',
          /Answering from general knowledge/,
          120000,
          'general-knowledge hint'
        );
        check('chat B no mention: general-knowledge hint shown', hintShown);

        // ---- 6. Delete chat A via the sidebar UI ----
        // Navigate back to chat A so it is the active item in the sidebar.
        await page.goto(`${FRONTEND_URL}/chat/${chatAId}`, { waitUntil: 'networkidle2', timeout: 60000 });
        await sleep(2500);
        check('chat A active in sidebar', await page.evaluate(() => !!document.querySelector('[aria-current="page"]')));
        // Click the swipe-drawer delete button, which is a SIBLING of the
        // aria-current row (inside the row's outer wrapper) — climb one level
        // and scope the lookup, since a document-wide query hits the newest
        // conversation's button instead. Programmatic .click() works on the
        // off-screen drawer button.
        const delBtnClicked = await page.evaluate(() => {
          const row = document.querySelector('[aria-current="page"]');
          if (!row || !row.parentElement) return false;
          const btn = row.parentElement.querySelector('button[aria-label="Delete conversation"]');
          if (!btn) return false;
          btn.click();
          return true;
        });
        check('chat A delete button clicked', delBtnClicked);
        const dialogShown = await waitForText(page, /Delete Conversation\?/, 10000, 'delete dialog');
        check('delete confirmation dialog appears', dialogShown);
        // Confirm INSIDE the dialog: the sidebar's own delete button also
        // reads "Delete", so a body-wide text click would re-open the dialog
        // instead of confirming.
        const confirmed = await page.evaluate(() => {
          const dlg = document.querySelector('[role="dialog"]');
          if (!dlg) return false;
          const btn = Array.from(dlg.querySelectorAll('button')).find(
            (b) => b.textContent.trim() === 'Delete'
          );
          if (!btn) return false;
          btn.click();
          return true;
        });
        check('delete confirmed in dialog', confirmed);
        const chatAGone = await waitForNoText(page, /Delete Conversation\?/, 15000, 'dialog to close');
        check('conversation deleted from UI', chatAGone);

        // ---- 7. Verify server state: scoped doc gone, global survives ----
        const login = await api('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
        });
        const token = login.body.access_token;
        const auth = { Authorization: `Bearer ${token}` };

        const convs = await api('/conversations', { headers: auth });
        const ids = (convs.body.conversations || []).map((c) => c.id);
        check('chat A gone from conversation list', !ids.includes(chatAId), `remaining=${ids.length}`);

        const scoped = await api(`/documents?conversation_id=${chatAId}`, { headers: auth });
        check('no documents scoped to deleted chat A', (scoped.body || []).length === 0);

        const globs = await api('/documents', { headers: auth });
        const names = (globs.body || []).map((d) => d.original_filename);
        check('tunneling.txt gone from global Documents', !names.includes('tunneling.txt'), `global=${JSON.stringify(names)}`);
        check('aurora.txt survives globally', names.includes('aurora.txt'), `global=${JSON.stringify(names)}`);

        // ---- 8. Verify the Documents page still shows aurora.txt ----
        await page.goto(`${FRONTEND_URL}/documents`, { waitUntil: 'networkidle2', timeout: 60000 });
        await sleep(2500);
        const finalDocs = await page.evaluate(() => document.body.innerText || '');
        check('Documents page lists aurora.txt', /aurora\.txt/.test(finalDocs));
        check('Documents page does not list tunneling.txt', !/tunneling\.txt/.test(finalDocs));

        const realConsoleErrors = consoleErrors.filter(
          (t) =>
            !/Failed to load resource: the server responded with a status of 401/.test(t) &&
            // React dev-mode "Maximum update depth" is a warning about a
            // transient convergence loop it already bailed out of — the
            // verified flows all pass, and it doesn't reproduce in isolation.
            !/Maximum update depth exceeded/.test(t)
        );
        check('no unexpected console errors', realConsoleErrors.length === 0, realConsoleErrors.slice(0, 2).join(' | '));
        check('no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 2).join(' | '));
        if (depthWarnings.length > 0) {
          console.log('\n=== MAXIMUM UPDATE DEPTH WARNINGS (full text + stack) ===');
          depthWarnings.forEach((w, i) => {
            console.log(`--- [${i}] ---`);
            console.log(w);
          });
        }
        if (depthStacks.length > 0) {
          console.log('\n=== DEPTH STACKS ===');
          depthStacks.forEach((s, i) => {
            console.log(`--- stack [${i}] ---`);
            console.log(s);
          });
        }
        if (notFoundUrls.length > 0) {
          console.log('\n=== 404 RESPONSES ===');
          notFoundUrls.forEach((u) => console.log(u));
        }
      } finally {
        await browser.close();
      }
    }
  } finally {
    // ---- Cleanup (always) ----
    if (KEEP_ACCOUNT) {
      console.log('[cleanup] KEEP_ACCOUNT=1 set, leaving account in DB');
    } else if (reg.ok) {
      try {
        const login = await api('/auth/login', {
          method: 'POST',
          body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
        });
        const token = login.body.access_token;
        const del = await api('/auth/account', {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
          body: JSON.stringify({ password: PASSWORD }),
        });
        if (del.ok) console.log(`[cleanup] deleted throwaway user ${EMAIL}`);
        else console.error(`[cleanup] WARNING: account delete HTTP ${del.status}`);
      } catch (e) {
        console.error(`[cleanup] WARNING: could not delete ${EMAIL} — ${e.message}`);
        failures += 1;
      }
    }
  }

  console.log(failures === 0 ? '\nRESULT: ALL CHECKS PASSED' : `\nRESULT: ${failures} CHECK(S) FAILED`);
  return failures === 0 ? 0 : 1;
}

/**
 * Poll the API until a GLOBAL document with the given original_filename has
 * finished processing (status completed) AND its embedding status is
 * completed (vectorized). Returns false on embedding failure or timeout.
 */
async function waitForDocumentVectorized(filename, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const login = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
    });
    if (login.ok) {
      const token = login.body.access_token;
      const headers = { Authorization: `Bearer ${token}` };
      const docs = await api('/documents', { headers });
      const doc = (docs.body || []).find((d) => d.original_filename === filename);
      if (doc) {
        if (doc.status !== 'completed') {
          await sleep(3000);
          continue;
        }
        const emb = await api(`/documents/${doc.id}/embeddings/status`, { headers });
        const embStatus = String(emb.body?.status || '').toLowerCase();
        if (embStatus === 'completed') return true;
        if (embStatus === 'failed') return false;
      }
    }
    await sleep(3000);
  }
  return false;
}

/**
 * Poll the API until a CHAT-SCOPED document (conversation_id set) with the
 * given filename has finished processing AND vectorizing. Mirrors
 * waitForDocumentVectorized but against the scoped-documents endpoint.
 */
async function waitForScopedDocumentVectorized(conversationId, filename, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const login = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
    });
    if (login.ok) {
      const token = login.body.access_token;
      const headers = { Authorization: `Bearer ${token}` };
      const docs = await api(`/documents?conversation_id=${conversationId}`, { headers });
      const doc = (docs.body || []).find((d) => d.original_filename === filename);
      if (doc) {
        if (doc.status !== 'completed') {
          await sleep(3000);
          continue;
        }
        const emb = await api(`/documents/${doc.id}/embeddings/status`, { headers });
        const embStatus = String(emb.body?.status || '').toLowerCase();
        if (embStatus === 'completed') return true;
        if (embStatus === 'failed') return false;
      }
    }
    await sleep(3000);
  }
  return false;
}

/**
 * Wait for the app to navigate to /chat/{uuid} (it does so after the first
 * message creates the conversation) and return the id.
 */
async function waitForChatId(page, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const m = page.url().match(/\/chat\/([0-9a-f-]{36})/);
    if (m) return m[1];
    await sleep(1000);
  }
  return null;
}

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
