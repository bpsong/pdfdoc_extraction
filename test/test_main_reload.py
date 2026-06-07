from main import _should_use_reload


def test_should_use_reload_allows_development_reload():
    env = {"USE_RELOAD": "true", "APP_ENV": "development"}

    assert _should_use_reload(env) is True


def test_should_use_reload_disables_production_reload():
    env = {"USE_RELOAD": "true", "APP_ENV": "production"}

    assert _should_use_reload(env) is False


def test_should_use_reload_defaults_to_disabled():
    assert _should_use_reload({}) is False
