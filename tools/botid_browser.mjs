#!/usr/bin/env node
/**
 * Bot-protection challenge bridge, headless-browser edition.
 *
 * Every browser the relay trusts is a browser that ran its challenge script
 * in a real DOM. Rather than emulate that DOM (fragile, and dishonest about
 * what it proves), this shim drives a real headless Chromium over CDP, asks
 * the page itself for a token, and serves it over loopback HTTP so the Python
 * client can attach the exact same `x-is-human` value a human visitor would.
 *
 * Requirements (Linux VPS):
 *   npx playwright install --with-deps chromium
 *   npm i playwright            # or: npm i playwright-core
 *
 * Usage:
 *   node tools/botid_browser.mjs --listen 127.0.0.1:20130
 *   curl -s http://127.0.0.1:20130/challenge?size=0.31
 *
 * Lifecycle / resource guarantees (VPS safety):
 *   - at most ONE Chromium exists at any time (single-flight boot)
 *   - a failed boot closes the browser it launched (no orphans)
 *   - browser/page crash or disconnect resets state; next request reboots
 *   - every page.evaluate has a hard timeout; a wedged page is torn down
 *   - requests are serialised on the single page with a bounded queue
 *   - optional idle shutdown frees Chromium memory between bursts
 *   - SIGTERM/SIGINT/uncaught errors close Chromium before exit
 */

import { createServer } from "node:http";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  options: {
    listen: { type: "string", default: "127.0.0.1:20130" },
    upstream: { type: "string", default: "https://solana.ai" },
    path: {
      type: "string",
      default:
        "/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39-8ed7-437e-a3be-862e0f06eea3/a-4-a/c.js",
    },
    headless: { type: "boolean", default: true },
    "print-once": { type: "boolean", default: false },
    // Resource limits (all in ms / counts). Tunable without code changes.
    "mint-timeout": { type: "string", default: "15000" },
    "boot-timeout": { type: "string", default: "60000" },
    "idle-timeout": { type: "string", default: "300000" }, // 0 = never
    "max-queue": { type: "string", default: "8" },
    "max-mints": { type: "string", default: "500" }, // recycle browser; 0 = never
  },
  strict: false,
});

const upstream = values.upstream.replace(/\/$/, "");
const challengePath = values.path; // kept for CLI compatibility
void challengePath;
const lastColon = values.listen.lastIndexOf(":");
const host = values.listen.slice(0, lastColon);
const port = Number(values.listen.slice(lastColon + 1));

const MINT_TIMEOUT = Number(values["mint-timeout"]);
const BOOT_TIMEOUT = Number(values["boot-timeout"]);
const IDLE_TIMEOUT = Number(values["idle-timeout"]);
const MAX_QUEUE = Number(values["max-queue"]);
const MAX_MINTS = Number(values["max-mints"]);

const log = (msg) => process.stderr.write(`[botid] ${msg}\n`);

let browser = null;
let page = null;
let bootPromise = null; // single-flight guard
let mintCount = 0;
let idleTimer = null;
let shuttingDown = false;
let bootGen = 0; // bumped on every teardown; stale boots self-destruct

function withTimeout(promise, ms, what) {
  let t;
  const timer = new Promise((_, reject) => {
    t = setTimeout(() => reject(new Error(`${what} timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timer]).finally(() => clearTimeout(t));
}

/** Close Chromium (if any) and clear all state. Safe to call repeatedly. */
async function teardown(reason) {
  bootGen += 1;
  const b = browser;
  browser = null;
  page = null;
  bootPromise = null;
  mintCount = 0;
  if (!b) return;
  log(`closing browser: ${reason}`);
  try {
    await withTimeout(b.close(), 10_000, "browser.close");
  } catch (err) {
    // close() hung or failed: hard-kill the process tree as last resort.
    log(`close failed (${err.message}); killing process`);
    try {
      b.process?.()?.kill("SIGKILL");
    } catch {}
  }
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch {
    try {
      return await import("playwright-core");
    } catch {
      throw new Error(
        "playwright not installed: npm i playwright && npx playwright install chromium",
      );
    }
  }
}

async function doBoot() {
  const gen = bootGen;
  const playwright = await loadPlaywright();
  const b = await playwright.chromium.launch({
    headless: values.headless,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  if (gen !== bootGen || shuttingDown) {
    // Boot was timed out / torn down while launching: don't leak this one.
    await b.close().catch(() => b.process?.()?.kill("SIGKILL"));
    throw new Error("boot superseded");
  }
  browser = b;
  // If Chromium dies for any reason, forget it so the next call reboots.
  b.on("disconnected", () => {
    if (browser === b) {
      log("browser disconnected");
      browser = null;
      page = null;
      bootPromise = null;
    }
  });
  try {
    const context = await b.newContext({
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
      viewport: { width: 1512, height: 982 },
    });
    const p = await context.newPage();
    p.on("crash", () => {
      log("page crashed");
      teardown("page crash");
    });
    await p.goto(`${upstream}/chat`, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => !!window.V_C && !!window.V_C.S, null, {
      timeout: 45_000,
    });
    await p.evaluate(() => {
      if (typeof window.V_C[0] !== "function") {
        window.V_C.push(() => window.V_C.S(1, 0, 0.31));
      }
    });
    const kind = await p.evaluate(() => typeof window.V_C[0]);
    if (kind !== "function") throw new Error("challenge function did not install");
    // Only publish the page once it is fully ready (and still current).
    if (gen !== bootGen) throw new Error("boot superseded");
    page = p;
    log(`page ready: V_C[0] is ${kind}`);
  } catch (err) {
    // Never leave a half-booted Chromium behind.
    await teardown(`boot failed: ${err.message}`);
    throw err;
  }
}

/** Single-flight: concurrent callers share one boot. */
function ensureBooted() {
  if (page) return Promise.resolve();
  if (shuttingDown) return Promise.reject(new Error("shutting down"));
  if (!bootPromise) {
    bootPromise = withTimeout(doBoot(), BOOT_TIMEOUT, "boot").catch(async (err) => {
      await teardown(`boot error: ${err.message}`);
      throw err;
    });
  }
  return bootPromise;
}

function armIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  if (!IDLE_TIMEOUT || values["print-once"]) return;
  idleTimer = setTimeout(() => {
    if (pending === 0) teardown("idle timeout");
  }, IDLE_TIMEOUT);
  idleTimer.unref();
}

async function mintOnce(size) {
  await ensureBooted();
  const p = page;
  try {
    const tok = await withTimeout(
      p.evaluate(async (sz) => {
        const fn = window.V_C[0];
        if (typeof fn !== "function") throw new Error("no V_C challenge function");
        return await fn(Number(sz));
      }, size),
      MINT_TIMEOUT,
      "mint",
    );
    mintCount += 1;
    if (MAX_MINTS && mintCount >= MAX_MINTS) {
      // Periodic recycle bounds long-run page memory growth.
      teardown(`recycle after ${mintCount} mints`);
    }
    return tok;
  } catch (err) {
    // A timed-out or failed evaluate may leave the page wedged: drop it.
    await teardown(`mint failed: ${err.message}`);
    throw err;
  }
}

// Serialise mints on the single shared page, with a bounded queue.
let chain = Promise.resolve();
let pending = 0;

class QueueFull extends Error {}

function mint(size = 0.31) {
  if (pending >= MAX_QUEUE) return Promise.reject(new QueueFull("queue full"));
  pending += 1;
  if (idleTimer) clearTimeout(idleTimer);
  const run = chain.then(() => mintOnce(size));
  chain = run.catch(() => {}).finally(() => {
    pending -= 1;
    if (pending === 0) armIdleTimer();
  });
  return run;
}

function parseSize(raw) {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 && n <= 1 ? n : 0.31;
}

async function shutdown(code, reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  log(`shutdown: ${reason}`);
  if (idleTimer) clearTimeout(idleTimer);
  server?.close();
  await teardown(reason);
  process.exit(code);
}

process.on("SIGTERM", () => shutdown(0, "SIGTERM"));
process.on("SIGINT", () => shutdown(0, "SIGINT"));
process.on("SIGHUP", () => shutdown(0, "SIGHUP"));
process.on("uncaughtException", (err) => shutdown(1, `uncaught: ${err.message}`));
process.on("unhandledRejection", (err) =>
  log(`unhandled rejection: ${err?.message ?? err}`),
);

let server = null;

if (values["print-once"]) {
  mint()
    .then(async (tok) => {
      process.stdout.write(JSON.stringify(tok));
      await shutdown(0, "print-once done");
    })
    .catch(async (err) => {
      process.stderr.write(`challenge failed: ${err.message}\n`);
      await shutdown(1, "print-once failed");
    });
} else {
  server = createServer(async (req, res) => {
    if (req.method !== "GET" || !req.url.startsWith("/challenge")) {
      res.writeHead(404).end("not found");
      return;
    }
    const size = parseSize(new URL(req.url, "http://x").searchParams.get("size"));
    try {
      const token = await mint(size);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(token));
    } catch (err) {
      const busy = err instanceof QueueFull;
      log(`request failed: ${err.message}`);
      res.writeHead(busy ? 503 : 502, {
        "content-type": "application/json",
        ...(busy ? { "retry-after": "2" } : {}),
      });
      res.end(JSON.stringify({ error: busy ? "busy" : "challenge failed" }));
    }
  });
  // Bound slow/abandoned connections.
  server.requestTimeout = MINT_TIMEOUT + BOOT_TIMEOUT + 5_000;
  server.headersTimeout = 10_000;
  server.keepAliveTimeout = 5_000;
  server.maxConnections = MAX_QUEUE * 2;
  server.listen(port, host, () => {
    log(`challenge bridge (browser) on http://${host}:${port}/challenge`);
  });
}
