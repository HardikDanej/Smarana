# Postgres Row-Level Security Design (Plan Step 82)

Step 81-82: "tenant_id/organization_id/project_id/owner_id/agent_id/scope
on every memory, enforced at both the application layer and the database
layer (Postgres RLS) -- never application code alone."

**Status: closed, Phase 17.** This started as a design artifact only --
the paragraph below is left in place as the historical record of why,
not as the current state. `core/adapters/postgres_adapter.py` now runs
almost exactly the policy specified here (one adjustment, noted below),
against a real Postgres+pgvector instance, and
`tests/test_postgres_adapter.py::test_rls_holds_even_for_a_raw_query_that_bypasses_the_adapters_own_code`
proves it: a plain `SELECT` issued directly on the connection, not
through any of the adapter's own Python methods, still cannot see
another tenant's row once `set_tenant_context()` has scoped the session.
See `docs/POSTGRES_SETUP.md` for how to stand the database up and the
one real gotcha (table-owner RLS exemption) hit while closing this.

**The one deliberate change from the original design below:** the policy
actually shipped is
`NULLIF(current_setting('app.tenant_id', true), '') IS NULL OR tenant_id
= current_setting('app.tenant_id', true)`, not the bare
`tenant_id = current_setting(...)` this document originally specified.
The bare version denies by default, which sounds like the safer choice
in isolation, but it breaks the moment `PostgresAdapter` runs any
ordinary `get()`/`search()`/`list_all()` with no tenant context ever set
-- and every other opt-in filter in this codebase (`principal_id` on
`RetrievalEngine.retrieve()`, `tenant_id` on that same call, `audit_log`
on `PolicyEngine`) is additive: omitting it means "no filtering," never
"see nothing." The shipped policy keeps RLS consistent with that same
default instead of contradicting it, while still closing the real gap --
once a tenant context IS set, isolation is exactly as absolute as
originally specified.

---

*Original design record, written before a Postgres adapter existed:*

This document was a design artifact, not running code. It existed so the
database-layer half of Step 82 was specified precisely enough to build,
honestly labeled as **not yet executable**: there was no Postgres adapter
in this codebase, and the only `StorageAdapter` (`SQLiteAdapter`) stores
each `MemoryObject` as a single opaque JSON blob in a `data` column --
there was no `tenant_id` *column* for a database-level policy to filter
on yet, only a `tenant_id` *field* inside that JSON. RLS needs a real
column, which is exactly what `postgres_adapter.py`'s normalized schema
now provides.

## Why application-layer isolation alone isn't Step 82's answer

Phase 16 already built the application-layer half:
`access_control.can_access_tenant()` and `RetrievalEngine.retrieve(...,
tenant_id=...)` filter query results in Python. That is real and tested
(`test_multi_tenancy.py`), but it has exactly the shape Step 82 warns
against relying on alone: it only runs if the calling code remembers to
pass `tenant_id`. A bug, a new code path, or a future adapter that talks
to the same database directly (bypassing `RetrievalEngine` entirely) gets
no isolation at all. A database-level policy is the second, independent
wall: even a query that forgets `tenant_id` still can't read another
tenant's rows, because Postgres itself refuses the row before the
application ever sees it.

## The schema this design assumes

A normalized `memories` table (not the JSON-blob shape `SQLiteAdapter`
uses today), with `tenant_id` as a real, indexed column:

```sql
CREATE TABLE memories (
    id            TEXT PRIMARY KEY,
    tenant_id     TEXT,              -- NULL means untenanted, per models.py's own rule
    owner_id      TEXT,
    scope         TEXT NOT NULL,
    data          JSONB NOT NULL,    -- the rest of MemoryObject, as today
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX memories_tenant_id_idx ON memories (tenant_id);
```

## The policy

```sql
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Deny by default: with RLS enabled and no policy matching, every row is
-- hidden. This mirrors can_access_tenant()'s own rule -- a memory with
-- no tenant_id belongs to no tenant, not to every tenant -- by making
-- current_setting('app.tenant_id') unset behave the same way: no policy
-- below matches a NULL setting against a NULL tenant_id, so untenanted
-- rows stay invisible to a tenant-scoped session rather than leaking in.

CREATE POLICY tenant_isolation ON memories
    USING (tenant_id = current_setting('app.tenant_id', true));

-- A session-level escape hatch for untenanted operational access
-- (migrations, cross-tenant admin tooling) is a separate, explicitly
-- granted role -- BYPASSRLS on a dedicated admin role, never a second
-- permissive policy that would silently widen what an ordinary
-- application connection can see.
```

`current_setting('app.tenant_id', true)` (the `true` makes a missing
setting return `NULL` instead of raising) is set once per connection or
transaction by the application, right after authenticating the caller
and resolving which tenant they belong to:

```sql
SET app.tenant_id = 'tenant-abc123';
```

The application decides *which* tenant a session gets to see (that part
can't move into the database); the database then makes sure that
decision, once set, can't be bypassed by any query issued afterward on
that connection -- including a query the application layer never
intended to scope, or a bug that forgot to filter.

## What this does and doesn't close

**Closes:** a compromised or buggy application code path can no longer
read across tenants merely by omitting a `WHERE tenant_id = ...` clause,
*given* the Postgres adapter sets `app.tenant_id` correctly per session
and the table is genuinely RLS-enabled.

**Does not close by itself:**
- Connection pooling that reuses a Postgres connection across different
  tenants' requests without resetting `app.tenant_id` in between would
  leak the previous tenant's setting forward. The adapter must reset (or
  explicitly re-`SET`) it on every checkout from the pool.
- A role with `BYPASSRLS` (superuser, or the admin role above) sees
  everything regardless of policy -- RLS is a wall for ordinary
  application roles, not a substitute for controlling who holds that
  privilege.
- This policy alone doesn't express `owner_id`/`Permission` grants
  (Step 69) -- that finer-grained layer stays exactly where Phase 13
  built it, in `AccessPolicy`. Tenant isolation is the outer wall;
  permission grants are the inner one, and RLS is only designed here to
  replace the outer wall's application-layer-only enforcement, not the
  inner one's.
