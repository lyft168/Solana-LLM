# Contributing

## Ground rules

1. **No secrets in the repo.** Session cookies live in `~/.local/state`, never in git.
2. **Keep the catalog as the single source of truth.** Model ids live only in
   `src/solana_chat/catalog.py`; docs and bridges read from it.
3. **Fail closed.** New parsing code must raise on malformed input instead of
   returning defaults.
4. **No warnings, no prompts.** Errors are codes (`RelayError.code`), not text.

## Workflow

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
ruff check src tests
ruff format src tests
```

## Adding a model

1. Add a `Model(...)` entry to `MODELS` in `src/solana_chat/catalog.py`.
2. `python -m pytest tests/test_catalog.py` — the uniqueness test catches alias collisions.
3. Update the model table in `README.md` and `docs/i18n/README.*.md`.
4. Nothing else needs changing: the bridge, CLI and 9router examples all
   read from `MODELS`.

## Reporting a protocol change

If solana.ai ships a new EHBP framing or a new relay endpoint, open an issue
with:
- the bundle chunk name (`_next/static/immutable/chunks/<hash>.js`),
- the exact header/field diff,
- the error code returned.

Reverse-engineering notes for the current format live in
`docs/protocol-ehbp.md`.
