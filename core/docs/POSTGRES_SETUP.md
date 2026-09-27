# Provisioning Postgres + pgvector for Phase 17

`tests/test_postgres_adapter.py` runs against a real local Postgres
instance -- it is not mocked, because the thing being proven (Step 82's
RLS policy actually blocking a cross-tenant read, Step 87's `<=>`
similarity operator actually ranking results) is only meaningful against
a real server. The tests skip cleanly (see `tests/conftest.py`) if one
isn't reachable; they do not fail the whole suite and do not fall back
to a fake.

## One-time setup (Debian/Ubuntu, what this environment actually ran)

```bash
apt-get install -y postgresql-16-pgvector   # postgresql-16 itself was already installed
service postgresql start

su postgres -c "psql -c \"CREATE ROLE memory_os WITH LOGIN PASSWORD 'memory_os_dev' CREATEDB;\""
su postgres -c "psql -c \"CREATE DATABASE memory_os_dev OWNER memory_os;\""
su postgres -c "psql -d memory_os_dev -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
su postgres -c "psql -d memory_os_dev -c \"GRANT ALL ON SCHEMA public TO memory_os;\""

pip install psycopg2-binary   # or: pip install -r core/adapters/requirements.txt
```

`PostgresAdapter._init_schema()` creates its own `memories` and
`relationships` tables, indexes, and the `tenant_isolation` RLS policy on
first connection -- nothing beyond the role/database/extension above
needs to exist ahead of time.

## Connection parameters

`tests/conftest.py` reads these environment variables, falling back to
the values created above if unset:

| Variable | Default |
|---|---|
| `MEMORY_OS_TEST_PGHOST` | `localhost` |
| `MEMORY_OS_TEST_PGPORT` | `5432` |
| `MEMORY_OS_TEST_PGDATABASE` | `memory_os_dev` |
| `MEMORY_OS_TEST_PGUSER` | `memory_os` |
| `MEMORY_OS_TEST_PGPASSWORD` | `memory_os_dev` |

## The one real gotcha this phase hit

Postgres exempts a table's **owner** from that table's own RLS policies
by default -- `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` alone does
nothing for a connection using the role that created the table (which is
exactly what `PostgresAdapter` does, since it also runs the `CREATE
TABLE`). The fix is `ALTER TABLE memories FORCE ROW LEVEL SECURITY`,
also run in `_init_schema()`. Documented here because it is the kind of
thing that silently passes a naive test (a query "works," it just never
enforces anything) -- `test_rls_holds_even_for_a_raw_query_that_bypasses_the_adapters_own_code`
is the test that would have caught it, and did, during development.

## Why SQLite stays the default everywhere else

Nothing in `core/memory_os` or the existing test suite switched to
Postgres -- `SQLiteAdapter` (in-memory, zero setup) is still what every
non-Phase-17 test uses, and remains the right default for local
development and CI that shouldn't need a database service running.
`PostgresAdapter` is additive: the production-shaped adapter for when one
is needed, wired in by a caller exactly like `ClaudeProvider` is, never
auto-selected by the engine.
