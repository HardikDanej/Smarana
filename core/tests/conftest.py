"""
Shared pytest fixtures.

Postgres-backed tests (Steps 86-90) need a real local Postgres+pgvector
instance -- provisioning it is an environment concern
(core/docs/POSTGRES_SETUP.md), not something a test fixture fakes. When
one isn't reachable, tests that need it skip with a clear reason rather
than either failing the whole run or silently passing against a mock --
the same honesty rule this project applies everywhere else: a gap is
named, never hidden behind green output.
"""

from __future__ import annotations

import os
import threading
import time

import psycopg2
import pytest
import uvicorn


def _connect_kwargs() -> dict:
    return dict(
        host=os.environ.get("MEMORY_OS_TEST_PGHOST", "localhost"),
        port=int(os.environ.get("MEMORY_OS_TEST_PGPORT", "5432")),
        dbname=os.environ.get("MEMORY_OS_TEST_PGDATABASE", "memory_os_dev"),
        user=os.environ.get("MEMORY_OS_TEST_PGUSER", "memory_os"),
        password=os.environ.get("MEMORY_OS_TEST_PGPASSWORD", "memory_os_dev"),
    )


@pytest.fixture
def postgres_adapter():
    from adapters.postgres_adapter import PostgresAdapter

    try:
        adapter = PostgresAdapter(**_connect_kwargs())
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable for integration tests: {exc}")
        return
    with adapter._conn.cursor() as cur:
        cur.execute("TRUNCATE memories, relationships")
    yield adapter
    adapter.close()


@pytest.fixture
def live_api_server():
    """Runs api.app.create_app's FastAPI app on a real ephemeral TCP
    port, in a background thread -- for sdk/test_client.py, which is
    testing a REAL network client (Step 97), not an in-process ASGI
    shortcut. httpx.ASGITransport only supports httpx.AsyncClient, and
    the SDK is deliberately synchronous (matching every other client in
    this codebase); a live server is the honest way to exercise it.

    Yields a factory `make_app(storage, **create_app_kwargs) -> base_url`
    so each test builds its own storage/api_keys/rate_limiter and gets
    back the URL to point MemoryOSClient at.
    """
    from api import create_app

    servers: list[uvicorn.Server] = []
    threads: list[threading.Thread] = []

    def make_app(storage, **kwargs) -> str:
        app = create_app(storage, **kwargs)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        while not server.started:
            time.sleep(0.01)
        servers.append(server)
        threads.append(thread)
        port = server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    yield make_app

    for server, thread in zip(servers, threads):
        server.should_exit = True
        thread.join(timeout=5)
