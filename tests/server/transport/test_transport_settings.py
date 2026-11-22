"""Tests for transport settings and the stdio default."""

import pytest

import server.main as main_module
from server.transport.settings import TransportSettings, load_settings


def test_default_is_stdio() -> None:
    assert load_settings([], {}).transport == "stdio"


def test_env_selects_http_with_defaults() -> None:
    settings = load_settings([], {"TRAKT_MCP_TRANSPORT": "http"})

    assert settings == TransportSettings(transport="http")
    assert (settings.host, settings.port) == ("127.0.0.1", 8080)


def test_flags_override_env() -> None:
    env = {
        "TRAKT_MCP_TRANSPORT": "stdio",
        "TRAKT_MCP_HOST": "1.2.3.4",
        "TRAKT_MCP_PORT": "9000",
    }

    settings = load_settings(
        ["--transport", "http", "--host", "0.0.0.0", "--port", "9100"],  # noqa: S104
        env,
    )

    assert (settings.transport, settings.host, settings.port) == (
        "http",
        "0.0.0.0",  # noqa: S104
        9100,
    )


def test_lists_and_flags_from_env() -> None:
    settings = load_settings(
        [],
        {
            "TRAKT_MCP_ALLOWED_ORIGINS": " https://claude.ai , https://x.test ,",
            "TRAKT_MCP_ALLOWED_HOSTS": "trakt:8080",
            "TRAKT_MCP_STATELESS": "TRUE",
        },
    )

    assert settings.allowed_origins == ("https://claude.ai", "https://x.test")
    assert settings.allowed_hosts == ("trakt:8080",)
    assert settings.stateless is True


@pytest.mark.parametrize(
    "env",
    [
        {"TRAKT_MCP_PORT": "abc"},
        {"TRAKT_MCP_PORT": "70000"},
        {"TRAKT_MCP_TRANSPORT": "ws"},
    ],
)
def test_invalid_env_exits(env: dict[str, str]) -> None:
    with pytest.raises(SystemExit):
        load_settings([], env)


def test_legacy_sse_defaults_on() -> None:
    assert load_settings([], {}).legacy_sse is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("yes", True),
        ("Yes", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("NO", False),
    ],
)
def test_legacy_sse_env_spellings(value: str, expected: bool) -> None:
    assert load_settings([], {"TRAKT_MCP_LEGACY_SSE": value}).legacy_sse is expected


@pytest.mark.parametrize("value", ["", "maybe", "off", "2"])
def test_legacy_sse_invalid_env_exits(value: str) -> None:
    with pytest.raises(SystemExit):
        load_settings([], {"TRAKT_MCP_LEGACY_SSE": value})


def test_no_legacy_sse_flag_wins_over_env() -> None:
    assert load_settings(["--no-legacy-sse"], {}).legacy_sse is False
    env = {"TRAKT_MCP_LEGACY_SSE": "true"}
    assert load_settings(["--no-legacy-sse"], env).legacy_sse is False


def test_run_defaults_to_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FakeServer:
        def run(self) -> None:
            calls.append("stdio")

    monkeypatch.setattr(main_module, "mcp", FakeServer())
    monkeypatch.delenv("TRAKT_MCP_TRANSPORT", raising=False)

    def fake_serve(_app: object, _settings: TransportSettings) -> None:
        calls.append("http")

    monkeypatch.setattr(main_module, "serve", fake_serve)

    main_module.run([])

    assert calls == ["stdio"]


def test_run_http_serves_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    served: list[TransportSettings] = []

    def fake_serve(_app: object, settings: TransportSettings) -> None:
        served.append(settings)

    monkeypatch.setattr(main_module, "serve", fake_serve)

    main_module.run(["--transport", "http", "--port", "9001"])

    assert [(s.transport, s.port) for s in served] == [("http", 9001)]
