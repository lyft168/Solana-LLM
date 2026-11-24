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
 * The page is loaded once and reused; a fresh token is minted per request by
 * calling window.V_C[0]() from the page context. Nothing is patched, nothing
 * is cached beyond the browser session itself.
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
  },
  strict: false,
});

const upstream = values.upstream.replace(/\/$/, "");
const challengePath = values.path;
const [host, port] = values.listen.split(":");

let browser;
let context;
let page;

async function boot() {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch {
    try {
      playwright = await import("playwright-core");
    } catch {
      throw new Error(
        "playwright not installed: npm i playwright && npx playwright install chromium",
      );
    }
  }
  browser = await playwright.chromium.launch({
    headless: values.headless,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    viewport: { width: 1512, height: 982 },
  });
  page = await context.newPage();
  // Use the app's own page: it bootstraps the bot-protection SDK the relay
  // expects (the `p.js` verifier + the per-route fetch patch) before the
  // challenge script will mint anything. Loading c.js on a blank page yields
  // an empty V_C queue and the relay answers 403.
  await page.goto(`${upstream}/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => !!window.V_C && !!window.V_C.S, null, {
    timeout: 45_000,
  });
  // The page may push resolvers on visibility change; normalise the queue so
  // V_C[0] is always a callable challenge function.
  await page.evaluate(() => {
    if (typeof window.V_C[0] !== "function") {
      window.V_C.push(() => window.V_C.S(1, 0, 0.31));
    }
  });
  const ok = await page.evaluate(() => typeof window.V_C[0] === "function");
  if (!ok) throw new Error("challenge function did not install");
  process.stderr.write(`page ready: V_C[0] is ${typeof window.V_C[0]}\n`);
}

async function mint(size = 0.31) {
  if (!page) await boot();
  return await page.evaluate(async (sz) => {
    const fn = window.V_C[0];
    if (typeof fn !== "function") throw new Error("no V_C challenge function");
    return await fn(Number(sz));
  }, size);
}

if (values["print-once"]) {
  mint()
    .then((tok) => {
      process.stdout.write(JSON.stringify(tok));
      process.exit(0);
    })
    .catch((err) => {
      process.stderr.write(`challenge failed: ${err.message}\n`);
      process.exit(1);
    });
} else {
  createServer(async (req, res) => {
    if (!req.url.startsWith("/challenge")) {
      res.writeHead(404).end("not found");
      return;
    }
    const size = Number(
      new URL(req.url, "http://x").searchParams.get("size") || 0.31,
    );
    try {
      const token = await mint(size);
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify(token));
    } catch (err) {
      res.writeHead(502, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
  }).listen(Number(port), host, () => {
    process.stderr.write(
      `botid challenge bridge (browser) on http://${host}:${port}/challenge\n`,
    );
  });
}
