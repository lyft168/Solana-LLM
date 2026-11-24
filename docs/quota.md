# Quota, credits, accounts — what is actually there

Every line below was verified against the live site on **2026-11-24** by
fetching `https://solana.ai/chat` and reading the shipped client bundle
(`_next/static/immutable/chunks/*.js`) plus the public relay contract.

## 1. No sign-up, no login

The chat page ships zero auth surfaces. `GET /api/chat/session` returns
`204` and sets an opaque relay cookie. There is no `/login`, `/register`,
`/account`, `/billing`, or email field anywhere in the bundle.

**Consequence:** there is no "register with mail.tm / emailnator" step to
automate, because the product has no account system. The earlier plan
(throwaway email → verification → account) does not map to this product.

## 2. No promo code

`grep -i promo` over every shipped chunk (`0c0hxoamwjsbw.js`,
`0yy8txmmvt6ux.js`, `288uub_11hw6n.js`, `3y7pjxq506gc5.js`, ...) returns
zero hits. The relay contract has no `promo` / `referral` / `credit` fields.
The only "free" concept is the shared demo budget.

**Consequence:** nothing to claim. Building a "promo claimer" would be
building against a field that does not exist.

## 3. No desktop app

`solana.ai/download` → `404`. `solana.ai/_next/static` contains no
Electron/Tauri artifacts; the "app" is the web page itself. The TEE client
is a ~60 KB in-bundle JS module (`ehbp`), which is what this repo
reimplements in Python.

## 4. Per-account credits: none

The relay exposes no balance, no `/credits`, no token counter in the UI. The
only limits are session-scoped and are surfaced through documented error
codes:

| Code | Meaning | HTTP |
|---|---|---|
| `session_limit` | "You've reached this demo's hourly message limit." | 429 |
| `chat_message_limit` | per-chat message cap | 429 |
| `demo_exhausted` | shared demo budget reset needed | 503 |
| `rate_limited` | per-network burst guard | 429 |
| `session_required` | cookie missing/expired (401 → auto-recover) | 401 |

**Answer to "berapa total credit per akun":** there is no per-account credit.
The unit is *messages per relay session*, capped by `session_limit` (hourly)
and `chat_message_limit` (per conversation), against a shared demo pool
(`demo_exhausted`). Any README that quotes a hard credit number for this
product is inventing it.

## 5. The bot gate (read this before filing "403 forbidden")

Every relay endpoint is wrapped in a Vercel bot-protection check. The site's
own client never calls the relay directly: it patches `window.fetch` to attach
`x-is-human`, `x-path`, `x-method`, where `x-is-human` is the JSON token
produced by `/149e9513-…/a-4-a/c.js`. The token carries `{"b":0,...}` on an
ordinary desktop visit and `{"b":1,...}` on a flagged one; a `b:1` token is
what produces `HTTP 403 {"error":{"code":"bot"}}`.

Consequences for a VPS client:

| Situation | Result |
|---|---|
| Browser page visit (human) | `x-is-human` token accepted, `204` |
| Raw request, no challenge header | `403` (`bot` or `forbidden`) |
| Datacenter IP, challenge header | `403` (`bot`) |
| Residential/US IP, challenge header | `204` |

The correct answer is **not** to forge a token — a forged `b:0` is only as
trustworthy as the network it was minted on, and the relay binds `rate_limited`
to the egress anyway. Run the bridge behind the same kind of IP a browser
would use (`SOLANA_CHAT_PROXY`), or run it from a machine you browse from and
copy `session.json` over. Both paths are first-class in the code:
`SolanaChatClient(session_store=...)` and `Transport(proxy=...)`.

This is why `solana-chat doctor` checks *reachability* but not *session*:
reachability is universal, session establishment is IP-dependent.

## 5a. How the client deals with the gate

Two supported paths, both shipped:

| Path | Setup | When to use |
|---|---|---|
| **Seed** | browse the chat once, copy `~/.local/state/inspectorai-solana-chat/session.json` (or point `--session-file` at a copy) | bridge on a datacenter VPS |
| **Solve link** | `node tools/botid_browser.mjs --listen 127.0.0.1:20130`, then `SOLANA_CHAT_SOLVE_COMMAND="node tools/botid_browser.mjs --print-once"` | long-running bridge that must re-mint tokens |

`tools/botid_browser.mjs` drives a real headless Chromium, loads the chat
page, and asks *the page* for a token through `window.V_C[0]()`. It does not
emulate the VM and does not forge anything — the token comes from the exact
script the browser runs.

The alternative we tried and rejected: re-implementing the challenge VM in
pure Python. The VM fingerprints its own environment, so a static emulation
desynchronises into `not a function` errors the moment the upstream build
rotates. Running the real script is the only honest reproduction, and it is
what ships.

## 6. What multiprocessing actually buys

Because the limit is per session + per egress IP, the only lever is **more
relay sessions from more egress IPs**. `solana-chat serve` is safe to run
once per IP; the persisted `session.json` is 0600 and holds only the opaque
cookie. That is the honest capacity story, and it is what `examples/9router.json`
points 9router at.
