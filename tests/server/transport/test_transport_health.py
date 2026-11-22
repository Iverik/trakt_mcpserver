"""Tests for /healthz: token states and an unreadable store."""

import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from starlette.applications import Starlette
from starlette.routing import Route

import server.transport.health as health
from client.auth.token_store import TokenStore
from server.transport.health import healthz


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = Starlette(routes=[Route("/healthz", healthz)])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


@pytest.fixture
def token_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "auth_token.json"
    monkeypatch.setattr(health, "AUTH_TOKEN_FILE", str(path))
    return path


def write_token(path: Path, created_at: int, expires_in: int) -> None:
    path.write_text(
        json.dumps(
            {
                "access_token": "secret-access",
                "refresh_token": "secret-refresh",
                "expires_in": expires_in,
                "created_at": created_at,
            }
        )
    )


@pytest.mark.asyncio
async def test_token_present(client: httpx.AsyncClient, token_path: Path) -> None:
    write_token(token_path, int(time.time()), 3600)

    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "token": "present"}
    assert "secret" not in response.text


@pytest.mark.asyncio
async def test_token_absent(client: httpx.AsyncClient, token_path: Path) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "token": "absent"}


@pytest.mark.asyncio
async def test_token_expired_is_still_healthy(
    client: httpx.AsyncClient, token_path: Path
) -> None:
    write_token(token_path, int(time.time()) - 7200, 3600)

    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "token": "expired"}


@pytest.mark.asyncio
async def test_corrupt_token_file_is_unhealthy(
    client: httpx.AsyncClient, token_path: Path
) -> None:
    token_path.write_text("{not json")

    response = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "token": "unreadable"}


@pytest.mark.asyncio
async def test_store_failure_is_unhealthy(
    client: httpx.AsyncClient, token_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenStore:
        def probe(self) -> None:
            raise PermissionError(f"cannot read {token_path}")

    def broken_store(_path: str) -> BrokenStore:
        return BrokenStore()

    monkeypatch.setattr(health, "get_token_store", broken_store)

    response = await client.get("/healthz")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "token": "unreadable"}


def test_probe_raises_for_unreadable_file_but_sync_does_not(
    token_path: Path,
) -> None:
    token_path.write_text("{not json")
    store = TokenStore(str(token_path))

    store.sync_from_disk()
    assert store.token is None
    with pytest.raises(ValueError):
        store.probe()


def test_probe_returns_none_when_file_missing(token_path: Path) -> None:
    assert TokenStore(str(token_path)).probe() is None


@pytest.mark.asyncio
async def test_malformed_token_does_not_leak_values_into_logs(
    client: httpx.AsyncClient,
    token_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    token_path.write_text(
        json.dumps(
            {
                "access_token": "secret-access",
                "refresh_token": "secret-refresh",
                "expires_in": "secret-not-an-int",
                "created_at": 1,
            }
        )
    )

    with caplog.at_level(logging.DEBUG):
        response = await client.get("/healthz")
        TokenStore(str(token_path)).sync_from_disk()

    assert response.status_code == 503
    assert caplog.records
    assert "secret" not in caplog.text
    assert "expires_in" in caplog.text
