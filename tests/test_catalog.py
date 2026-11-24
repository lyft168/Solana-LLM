from solana_chat import catalog


def test_default_model_is_deepseek():
    assert catalog.DEFAULT_MODEL.key == "deepseek-v4.1-flash"


def test_all_models_have_unique_aliases():
    seen = {}
    for model in catalog.MODELS:
        for alias in model.aliases:
            key = alias.lower()
            assert key not in seen, f"duplicate alias {alias}"
            seen[key] = model


def test_resolve_model_by_any_alias():
    for model in catalog.MODELS:
        assert catalog.resolve_model(model.key) is model
        assert catalog.resolve_model(model.sealed) is model
        assert catalog.resolve_model(model.public_id) is model
        assert catalog.resolve_model(model.display_name) is model


def test_resolve_unknown_raises():
    try:
        catalog.resolve_model("nope")
    except KeyError as exc:
        assert "available" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")
