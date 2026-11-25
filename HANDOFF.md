# Handoff guide: start here

This guide is for whoever picks this project up next, whether that's a developer or an AI agent. It's written in plain language, so you don't need to know the earlier history. For technical detail, see `REVIEW_NOTES.md`.

## 1. What this project is

A small Python program that runs on the owner's VPS. It lets AI tools use the chat models on solana.ai as if they were an OpenAI-style API at `/v1/chat/completions`.

- Upstream (original author): https://gitlab.com/inspectorai/inspectorai-solana-chat
- This copy (owner's private repo): https://github.com/lyft168/Solana-LLM
- On the VPS: `/home/blue/projects/inspectorai-solana-chat`

## 2. Current state (Nov 2026)

| Item | Status |
|---|---|
| Code fixes (encryption, thread safety, speed, Chromium helper) | Done and merged into `main` |
| Offline tests | 45 of 45 pass |
| Memory use | About 25 to 35 MB, so it's fine for a small VPS |
| **Works against the live site?** | **Not yet.** The site answers `HTTP 403` when the program opens a session (the bot check). Nothing after that step has been tested live |
| Connected to 9router | Not yet |

## 3. Where things are

| Path | What it is |
|---|---|
| `src/solana_chat/server.py` | The OpenAI-style API server |
| `src/solana_chat/client.py` | Talks to solana.ai (session, model choice, chat) |
| `src/solana_chat/hpke.py` | Encryption. **Handle with care**, see section 6 |
| `src/solana_chat/http.py` | Network connections (reused for speed) |
| `src/solana_chat/session.py` | Saves the session to disk safely |
| `tools/botid_browser.mjs` | Optional Chromium helper (Node.js). Uses 200 to 400 MB while running |
| `tests/` | Automated tests |
| `REVIEW_NOTES.md` | Detailed technical notes and open to-dos |

## 4. How to run the tests

```bash
cd ~/projects/inspectorai-solana-chat
source .venv/bin/activate        # use the project's own Python
pytest -q                        # should end with: 45 passed
```

If any test fails after your change, don't merge.

## 5. How to run the server safely

```bash
source .venv/bin/activate
export SOLANA_CHAT_API_KEY="$(openssl rand -hex 24)"   # pick a secret key
systemd-run --user --scope -p MemoryMax=150M solana-chat serve --host 127.0.0.1
```

- Always set an API key.
- Use `127.0.0.1` unless something in Docker (like 9router) has to reach it. Then use the Docker gateway (`172.17.0.1`), still with a key.
- `MemoryMax=150M` stops a bug from eating the whole VPS.

If you run the Chromium helper, run it under systemd with `MemoryMax=500M`, `TasksMax=200`, `KillMode=control-group`, `RuntimeMaxSec=6h` and a dedicated user. Prefer `--print-once` (it exits after each use). Check `pgrep -c chrome` after an hour: the number should be small, and 0 when idle.

## 6. Rules: please don't break these

1. **Never undo the nonce fix in `hpke.py`.** The old code encrypted everything with an all-zero nonce, which is a serious security bug.
2. **The old tests can't catch encryption bugs.** They only check that the program can read its own output. When you change `hpke.py`, also check it against a separate library (`pyhpke`), as was done here.
3. **If live replies fail to decrypt**, the site may use a slightly different encryption setup. Compare with the site's own JavaScript client before changing anything. Don't just revert.
4. **Keep the strict enclave domain check.** Don't allow `#`, `/`, `?`, `@` or `:` in it. Tests guard this.
5. **Run every change through a pull request** and the test suite. Don't push straight to `main`.
6. This project doesn't change how the site's bot check is handled, and the previous reviewer wouldn't help with that. Fixes have been limited to correctness, safety, speed and memory.

## 7. What to do next, in order

1. **Get one live chat working.** Nothing else can be confirmed until then. When it works, save one real streamed reply (remove any secrets) into `tests/fixtures/`.
2. **Thinking text:** the server currently drops the model's thinking. Add `reasoning_content` to replies and streamed chunks, and `reasoning_tokens` to usage. Small change.
3. **Real streaming:** after step 1, use the saved reply to build it. `iter_open_stream` in `hpke.py` is ready. Don't guess the format.
4. **Regression tests for all 5 models** (`gpt-oss`, `gemma-4-31b`, `deepseek-v4.1-flash`, `glm-5.3`, `kimi-k3.1-pro`) with a fake upstream.
5. **Connect to 9router.** It runs in Docker on host port 5003, with data in `/home/blue/dockge/stacks/9router/data`. Add an OpenAI-compatible provider pointing at `http://172.17.0.1:<port>/v1` with the API key and the 5 model names.
6. **Long chats:** more than 20 messages are refused. Add trimming of old messages.
7. **Chromium helper:** only syntax-checked so far. Test it with a fake browser (parallel requests, crash, timeout, idle shutdown).

## 8. Undo / safety net

- Tag `upstream-original` marks the code exactly as it came from GitLab, before any fixes.
- To compare: `git diff upstream-original main`
- To roll back, open a PR that reverts the merge. Don't force-push `main`.

## 9. Housekeeping

- 9router's `MACHINE_ID_SALT` was printed into an old chat log. Rotate it if that log is ever shared.
- The repo is private and contains third-party code. Check the upstream licence before making it public.
- Commit author shows `blue@localhost.localdomain`. The owner is fine with that.
