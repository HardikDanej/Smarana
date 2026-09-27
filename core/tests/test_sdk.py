"""
Phase 19 (Plan Step 97): the Python SDK, exercised against a REAL live
HTTP server (see tests/conftest.py's `live_api_server` fixture) -- the
SDK is a synchronous network client, so this is the honest way to prove
it works, not an in-process shortcut.
"""

import pytest

from adapters.sqlite_adapter import SQLiteAdapter
from api import APIKeyStore
from sdk import MemoryOSClient, MemoryOSError


def _connect(live_api_server, **kwargs):
    storage = SQLiteAdapter(check_same_thread=False)
    keys = APIKeyStore()
    key = keys.issue_key("agent-A", tenant_id="tenant-a")
    base_url = live_api_server(storage, api_keys=keys, **kwargs)
    return MemoryOSClient(base_url=base_url, api_key=key), keys


def test_health(live_api_server):
    client, _ = _connect(live_api_server)
    assert client.health() == {"status": "ok"}


def test_store_get_search_delete_round_trip(live_api_server):
    client, _ = _connect(live_api_server)

    memory = client.store("Project Alpha uses PostgreSQL.", "semantic", "project", "user_statement")
    assert memory["content"] == "Project Alpha uses PostgreSQL."

    fetched = client.get(memory["id"])
    assert fetched["id"] == memory["id"]

    results = client.search("PostgreSQL")
    assert any(r["memory_id"] == memory["id"] for r in results)

    client.delete(memory["id"])
    assert client.get(memory["id"]) is None


def test_get_missing_memory_returns_none_not_an_exception(live_api_server):
    client, _ = _connect(live_api_server)
    assert client.get("does-not-exist") is None


def test_no_api_key_raises_memory_os_error(live_api_server):
    storage = SQLiteAdapter(check_same_thread=False)
    keys = APIKeyStore()
    base_url = live_api_server(storage, api_keys=keys)
    client = MemoryOSClient(base_url=base_url)

    with pytest.raises(MemoryOSError) as excinfo:
        client.search("x")
    assert excinfo.value.status_code == 401


def test_client_works_as_a_context_manager(live_api_server):
    client, _ = _connect(live_api_server)
    with client as c:
        assert c.health() == {"status": "ok"}


def test_cross_tenant_get_returns_none_same_as_missing(live_api_server):
    storage = SQLiteAdapter(check_same_thread=False)
    keys = APIKeyStore()
    key_a = keys.issue_key("agent-A", tenant_id="tenant-a")
    key_b = keys.issue_key("agent-B", tenant_id="tenant-b")
    base_url = live_api_server(storage, api_keys=keys)

    client_a = MemoryOSClient(base_url=base_url, api_key=key_a)
    client_b = MemoryOSClient(base_url=base_url, api_key=key_b)

    memory = client_a.store("Tenant A's private note.", "semantic", "project", "user_statement")

    assert client_b.get(memory["id"]) is None
