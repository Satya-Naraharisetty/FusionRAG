#!/usr/bin/env node
/**
 * Shared helpers for the e2e smoke scripts that orchestrate the dockerized
 * stack (stop/restart the `redis` service) so the Redis-down rate-limit
 * fallback can be exercised against a live backend.
 *
 * Used by redis-fallback.js and redis-fallback-login.js. Platform-agnostic
 * (works on Windows cmd.exe and CI bash): docker compose commands target the
 * repo's docker-compose.yml explicitly, honor the COMPOSE_PROJECT_NAME
 * override (CI pins it to `hybrid_rag`), and quote the compose path.
 */
const { execSync } = require('child_process');
const path = require('path');

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function resolveRepoRoot() {
  try {
    return execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
  } catch {
    // Fall back to two levels up from this script (frontend/e2e -> repo root).
    return path.resolve(__dirname, '..', '..');
  }
}

// Resolved once — every docker call reuses it instead of re-spawning
// `git rev-parse` each time.
const REPO_ROOT = resolveRepoRoot();

function composeArgs() {
  const args = ['compose', '-f', `"${path.join(REPO_ROOT, 'docker-compose.yml')}"`];
  if (process.env.COMPOSE_PROJECT_NAME) {
    args.push('-p', process.env.COMPOSE_PROJECT_NAME);
  }
  return args;
}

function dockerCompose(...args) {
  const cmd = ['docker', ...composeArgs(), ...args].join(' ');
  return execSync(cmd, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
}

/** Container id of a running `redis` service, or '' when it is not running. */
function runningRedisId() {
  try {
    return dockerCompose('ps', '--status', 'running', '-q', 'redis').trim();
  } catch {
    return '';
  }
}

/** Stop the redis service and return true once the container is really down. */
async function stopRedis() {
  console.log('[docker] stopping redis…');
  const out = dockerCompose('stop', 'redis');
  const last = out.trim().split('\n').filter(Boolean).pop() || '';
  console.log(`[docker] ${last}`);
  // Poll briefly — `docker compose stop` can return while the container is
  // still mid-shutdown and still reported as `running`.
  for (let i = 0; i < 10 && runningRedisId() !== ''; i++) {
    await sleep(500);
  }
  return runningRedisId() === '';
}

/** Start the redis service and return true once it answers PING. */
async function startRedis() {
  console.log('[docker] restarting redis…');
  dockerCompose('start', 'redis');
  let pingOk = false;
  for (let i = 0; i < 30 && !pingOk; i++) {
    const id = runningRedisId();
    if (id) {
      try {
        const pong = execSync(`docker exec ${id} redis-cli ping`, {
          encoding: 'utf8',
          stdio: ['ignore', 'pipe', 'pipe'],
        }).trim();
        pingOk = pong === 'PONG';
      } catch {
        pingOk = false;
      }
    }
    if (!pingOk) await sleep(1000);
  }
  return pingOk;
}

/**
 * Exit the process with the given code. On Windows, process.exit() while libuv
 * async handles (undici fetch keep-alive) are still closing aborts with a
 * UV_HANDLE_CLOSING assertion and exit 127 — even for code 0. Setting
 * process.exitCode first lets the event loop drain, and the short grace period
 * gives libuv time to finish before process.exit() runs.
 */
function exitWith(code) {
  process.exitCode = code;
  setTimeout(() => process.exit(code), 200);
}

module.exports = { sleep, stopRedis, startRedis, runningRedisId, exitWith };
