"""
Python SDK (Plan Step 97): a client for the REST API (Step 96), so an
external Python caller never hand-rolls HTTP calls or reimplements the
Authorization-header and error-response conventions itself.

Talks over HTTP -- never imports memory_os or adapters directly --
because the whole point of Steps 96-98 together is "any language, any
MCP-compatible app, can reach the OS": a Python process using this SDK
and a Rust process hitting the REST API directly are the same kind of
client, from the server's point of view. That is also why `transport` is
a constructor parameter: tests exercise the real FastAPI app in-process
via `httpx.ASGITransport`, no live socket, but every layer between this
client and the app (auth, rate limiting, policy checks, serialization)
still actually runs.
"""

from __future__ import annotations

import httpx


class MemoryOSError(Exception):
    """Raised for any non-2xx response -- wraps the server's own detail
    message so a caller doesn't need to know httpx's exception shape."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


class MemoryOSClient:
    def __init__(
        self,
        base_url: str = "http://memory-os",
        api_key: "str | None" = None,
        *,
        timeout: float = 10.0,
        transport: "httpx.BaseTransport | None" = None,
    ):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key is not None else {}
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MemoryOSClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            content_type = response.headers.get("content-type", "")
            detail = response.json().get("detail", response.text) if "application/json" in content_type else response.text
            raise MemoryOSError(response.status_code, detail)
        return response

    def health(self) -> dict:
        return self._request("GET", "/health").json()

    def store(self, content: str, semantic_type: str, scope: str, source_type: str, **fields: object) -> dict:
        payload = {"content": content, "semantic_type": semantic_type, "scope": scope, "source_type": source_type, **fields}
        return self._request("POST", "/memories", json=payload).json()

    def get(self, memory_id: str) -> "dict | None":
        try:
            return self._request("GET", f"/memories/{memory_id}").json()
        except MemoryOSError as exc:
            if exc.status_code == 404:
                return None
            raise

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        return self._request("GET", "/memories", params={"q": query, "top_k": top_k}).json()

    def delete(self, memory_id: str) -> None:
        self._request("DELETE", f"/memories/{memory_id}")
