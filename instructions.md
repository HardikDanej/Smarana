# Installing and Running Smaraṇa (the Engine)

This covers `core/`: the Universal Memory OS engine. For the Claude Projects Skill instead, see [`docs/project-setup-guide.md`](docs/project-setup-guide.md).

Everything below assumes you are working from the repository root, with `core/` present. If you received this file inside a zip archive with a `core/` folder next to it, you already have everything you need.

## 1. Prerequisites

- Python 3.10, 3.11, 3.12, or 3.13.
- `pip`.
- For the dev-only path (steps 2 to 4 below): nothing else. SQLite ships with Python.
- For the production path (step 6): a local or reachable PostgreSQL 16 instance with the `pgvector` extension available.

## 2. Install dependencies

```bash
cd core
pip install -r requirements.txt -r requirements-dev.txt
```

This installs the engine itself plus everything every adapter needs: `anthropic`, `psycopg2-binary`, `cryptography`, `fastapi`, `uvicorn`, `httpx`, `mcp`, `opentelemetry-sdk`, and `pytest`.

## 3. Run the test suite

```bash
PYTHONPATH=. python3 -m pytest tests -q
```

Without a running Postgres instance, every test that needs one skips cleanly with a stated reason. It does not fail, and it does not pretend to pass. Expect `328 passed, 31 skipped` in that case, or `359 passed` once Postgres is reachable (see step 6).

Two more checks are worth running once the tests pass:

```bash
python3 scripts/verify_no_llm_dependency.py
python3 scripts/verify_adapter_isolation.py
```

Both print a single `GATE_...` line on success. They confirm that `memory_os`, the engine itself, imports no LLM library, no storage driver, and no network client. Every concrete technology lives in `adapters/` instead.

To see the full, machine-checked completion record for every phase of this engine's development, install the [`unlazy`](https://github.com/Leonxlnx/unlazy) skill this repository already uses (`.claude/skills/unlazy`) and run:

```bash
node .claude/skills/unlazy/scripts/gate-check.mjs --status GATES.md
```

## 4. Use it directly, in Python

The fastest way to see it work, no server, no database beyond SQLite:

```python
import sys
sys.path.insert(0, "core")  # or run with PYTHONPATH=core

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import MemoryScope, SemanticType, SourceType
from memory_os.models import MemoryObject
from memory_os.retrieval import RetrievalEngine

storage = SQLiteAdapter()  # in-memory by default; pass a path for a real file

memory = MemoryObject(
    content="The user prefers dark mode and terse status updates.",
    semantic_type=SemanticType.PREFERENCE,
    scope=MemoryScope.USER,
    source_type=SourceType.USER_STATEMENT,
)
storage.store(memory)

results = RetrievalEngine(storage).retrieve("What does the user prefer?")
print(results[0].memory.content)
```

That's the whole loop: a typed memory object goes in, a fused keyword/vector/temporal/relationship search comes back with it ranked.

## 5. Run the REST API

```bash
cd core
python3 -c "
import uvicorn
from adapters.sqlite_adapter import SQLiteAdapter
from api import create_app, APIKeyStore

storage = SQLiteAdapter(check_same_thread=False)
keys = APIKeyStore()
key = keys.issue_key('my-agent', tenant_id='my-tenant')
print('API key:', key)

app = create_app(storage, api_keys=keys)
uvicorn.run(app, host='127.0.0.1', port=8000)
"
```

Then, from another terminal:

```bash
curl -s http://127.0.0.1:8000/health

curl -s -X POST http://127.0.0.1:8000/memories \
  -H "Authorization: Bearer <the API key printed above>" \
  -H "Content-Type: application/json" \
  -d '{"content": "The user prefers dark mode.", "semantic_type": "preference", "scope": "user", "source_type": "user_statement"}'

curl -s "http://127.0.0.1:8000/memories?q=dark+mode" \
  -H "Authorization: Bearer <the API key>"
```

The interactive OpenAPI docs are at `http://127.0.0.1:8000/docs` once the server is running.

## 6. Add PostgreSQL and pgvector (production path)

SQLite is the dev-only default. Postgres with pgvector is the production baseline: hybrid full-text and vector search in one query, and row-level security enforced at the database itself, not just in application code.

```bash
# Debian/Ubuntu, adjust for your distribution
apt-get install -y postgresql-16 postgresql-16-pgvector
service postgresql start

su postgres -c "psql -c \"CREATE ROLE memory_os WITH LOGIN PASSWORD 'memory_os_dev' CREATEDB;\""
su postgres -c "psql -c \"CREATE DATABASE memory_os_dev OWNER memory_os;\""
su postgres -c "psql -d memory_os_dev -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
```

Then use `PostgresAdapter` in place of `SQLiteAdapter`:

```python
from adapters.postgres_adapter import PostgresAdapter

storage = PostgresAdapter(host="localhost", dbname="memory_os_dev", user="memory_os", password="memory_os_dev")
```

The adapter creates its own schema, indexes, and row-level security policy on first connection. Nothing further to run by hand. Full detail, including the one real gotcha (Postgres exempts a table's owner from its own row-level security by default), is in [`core/docs/POSTGRES_SETUP.md`](core/docs/POSTGRES_SETUP.md).

## 7. Run the MCP server

```python
from adapters.sqlite_adapter import SQLiteAdapter
from mcp_server import create_mcp_server

storage = SQLiteAdapter(check_same_thread=False)
server = create_mcp_server(storage, principal_id="my-agent", tenant_id="my-tenant")
server.run_stdio_async()  # or run_sse_async() / run_streamable_http_async()
```

This exposes three tools to any MCP-compatible client: `remember`, `recall`, and `forget`.

## 8. How it works

Four ideas carry the whole system.

**Core, then adapters.** `memory_os` is the engine: models, retrieval, policy, everything. It imports no vendor library, ever, checked by an automated gate rather than left to convention. `adapters/` is the only place a concrete technology (Claude, SQLite, Postgres, Fernet encryption, OpenTelemetry) gets wired in. Swapping a storage backend or an LLM provider means writing a new adapter, not touching the engine.

**Confidence is not truth.** Every memory carries a `confidence` score and a separate `truth_status`. A fact can be contradicted while still carrying high confidence from whoever stated it; the two questions never get collapsed into one field.

**No memory disappears silently.** Updates create a new version, keeping the old one linked as superseded, never overwritten in place. A tenant's retention policy marks aged-out memories `FORGOTTEN`, still present, not deleted. The one deliberate exception is a GDPR Article 17 erasure request, which does delete, because that is the point of the right to erasure.

**Every external caller goes through the same policy engine.** The REST API, the MCP server, and (if you build one) any other client all consult the same `PolicyEngine` before a memory is stored, retrieved, or deleted. A memory that exists but that the caller isn't allowed to see returns exactly the same response as one that doesn't exist. Confirming existence to someone who can't read the content is its own kind of leak.

For the full specification, read [`core/docs/V1_ARCHITECTURE.md`](core/docs/V1_ARCHITECTURE.md): 32 sections, each one pointing at the real file or test that backs its claim.

## 9. Where things live

```
core/
├── memory_os/       the engine: models, retrieval, policy, security, profiles
├── adapters/        the only place vendor/storage technology is imported
├── api/             REST/OpenAPI surface (FastAPI)
├── sdk/             a synchronous Python client for the REST API
├── mcp_server/      remember/recall/forget as MCP tools
├── memory_evals/    a benchmark repo -- run: python3 -m memory_evals
├── conformance/      adapter certification suites
├── tests/           the full test suite
├── docs/            every design and compliance document, start at V1_ARCHITECTURE.md
└── GATES.md         the actual, machine-verified completion record
```

## 10. If something doesn't work

- **Tests fail on import:** confirm you ran `pip install -r requirements.txt -r requirements-dev.txt` from inside `core/`, and that `PYTHONPATH` includes `core/` (or you `cd`'d into it first).
- **Postgres tests skip:** expected without a running Postgres instance. See step 6.
- **`sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`:** pass `check_same_thread=False` to `SQLiteAdapter` when using it behind the REST API or MCP server, both of which run handlers in a worker thread pool.
- **Everything else:** every open question this engine's own documentation could not resolve on its own is named directly in `core/docs/V1_ARCHITECTURE.md`'s closing section, not hidden.
