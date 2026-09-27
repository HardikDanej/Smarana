"""
Postgres adapter (Plan Steps 86-89): "SQLite stays dev-only; Postgres+
pgvector is the production baseline."

Like sqlite_adapter.py and claude_provider.py before it, this is the ONLY
file allowed to import `psycopg2` -- core/memory_os never touches a
concrete storage technology, enforced by the same adapter-isolation gate
that covers every other adapter.

Four things live here, one per Step:

- Step 86: PostgresAdapter itself, a StorageAdapter with a normalized
  schema (real tenant_id/owner_id columns, not fields buried in a JSON
  blob) -- which is what finally makes docs/POSTGRES_RLS.md's design
  executable. `_init_schema` applies that exact policy for real.
- Step 87: an `embedding` VECTOR column plus `vector_search()`, a real
  pgvector cosine-distance query replacing VectorRetriever's brute-force
  Python loop over every stored memory.
- Step 88: `hybrid_search()`, one SQL statement combining full-text rank
  and vector similarity -- a database-level fusion, not the app-level
  score-sum retrieval.py already does across two separate retrievers.
- Step 89: `add_relationship`/`relationships_from`/`relationships_to`
  plus `sync_relationship_graph`/`load_relationship_graph`, persisting
  the edges relationships.py's RelationshipGraph holds only in memory.
  RelationshipGraph itself does not change -- this is the persistence
  layer underneath it that its own docstring named as a later phase's job.
"""

from __future__ import annotations

import psycopg2
import psycopg2.extras

from memory_os.embedding import Embedder, HashingEmbedder
from memory_os.models import MemoryObject
from memory_os.relationships import MemoryRelationship, RelationshipGraph, RelationshipType

# Step 82's policy, adapted to compose with the rest of this codebase's
# own established default: every other opt-in filter here (principal_id,
# tenant_id in RetrievalEngine, audit_log in PolicyEngine) is additive --
# omitting it means "no filtering," never "see nothing." A bare
# `tenant_id = current_setting(...)` policy would instead hide every row
# the moment RLS is enabled, breaking that default the instant this
# adapter runs an ordinary get()/search()/list_all() with no tenant
# context set. This clause keeps RLS backward compatible with that
# default: unset app.tenant_id sees everything (matches Phase 16's own
# "no tenant_id means no tenant filtering"); a set one sees only its own
# tenant's rows, and can_access_tenant's own rule -- untenanted rows
# belong to no tenant, not to every tenant -- still holds once it is set.
_TENANT_POLICY_USING = (
    # NULLIF(..., '') because `SELECT set_config('app.tenant_id', NULL, ...)`
    # (how set_tenant_context(None) clears the context) sets a custom GUC
    # to an empty string, not SQL NULL -- current_setting() only returns a
    # true NULL for a GUC that was never touched this session at all. This
    # clause treats "cleared" and "never set" as the same unscoped state.
    "NULLIF(current_setting('app.tenant_id', true), '') IS NULL "
    "OR tenant_id = current_setting('app.tenant_id', true)"
)


def _vector_literal(vector: list[float]) -> str:
    """pgvector's text input format: '[0.1,0.2,...]'. Formatted by hand
    rather than depending on the separate `pgvector` python package --
    one fewer vendor dependency for one string join."""
    return "[" + ",".join(repr(float(v)) for v in vector) + "]"


class PostgresAdapter:
    """Implements memory_os.storage.StorageAdapter, plus the Step 87-89
    extensions no StorageAdapter Protocol method covers (vector/hybrid
    search take a query embedding the Protocol has no parameter for;
    relationship persistence isn't a memory operation at all)."""

    def __init__(
        self,
        dsn: "str | None" = None,
        *,
        embedder: "Embedder | None" = None,
        embedding_dimensions: int = 256,
        **conn_kwargs,
    ):
        self._conn = psycopg2.connect(dsn) if dsn else psycopg2.connect(**conn_kwargs)
        self._conn.autocommit = True
        self.embedder = embedder or HashingEmbedder(dimensions=embedding_dimensions)
        self.embedding_dimensions = embedding_dimensions
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT,
                    owner_id TEXT,
                    scope TEXT NOT NULL,
                    content TEXT NOT NULL,
                    data JSONB NOT NULL,
                    embedding VECTOR({int(self.embedding_dimensions)}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS memories_tenant_id_idx ON memories (tenant_id)"
            )
            cur.execute(
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS search_vector tsvector "
                "GENERATED ALWAYS AS (to_tsvector('english', content)) STORED"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS memories_search_vector_idx "
                "ON memories USING GIN (search_vector)"
            )
            cur.execute("ALTER TABLE memories ENABLE ROW LEVEL SECURITY")
            # Table owners are exempt from their own table's RLS policies
            # by default (Postgres's own documented behavior) -- and the
            # role this adapter connects as is the table's owner, since it
            # just created it above. FORCE is what makes the policy bind
            # even for the owner; without it, G26's cross-tenant test
            # would pass for the wrong reason (nothing was ever enforced).
            cur.execute("ALTER TABLE memories FORCE ROW LEVEL SECURITY")
            cur.execute("DROP POLICY IF EXISTS tenant_isolation ON memories")
            cur.execute(f"CREATE POLICY tenant_isolation ON memories USING ({_TENANT_POLICY_USING})")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS relationships (
                    id BIGSERIAL PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (source_id, relationship_type, target_id)
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS relationships_source_idx ON relationships (source_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS relationships_target_idx ON relationships (target_id)"
            )

    # --- Step 86: StorageAdapter ---

    def store(self, memory: MemoryObject) -> None:
        self._upsert(memory)

    def update(self, memory: MemoryObject) -> None:
        self._upsert(memory)

    def _upsert(self, memory: MemoryObject) -> None:
        embedding = _vector_literal(self.embedder.embed(memory.content))
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO memories (id, tenant_id, owner_id, scope, content, data, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    owner_id = excluded.owner_id,
                    scope = excluded.scope,
                    content = excluded.content,
                    data = excluded.data,
                    embedding = excluded.embedding
                """,
                (
                    memory.id,
                    memory.tenant_id,
                    memory.owner_id,
                    memory.scope.value,
                    memory.content,
                    memory.model_dump_json(),
                    embedding,
                ),
            )

    def get(self, memory_id: str) -> "MemoryObject | None":
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM memories WHERE id = %s", (memory_id,))
            row = cur.fetchone()
        return None if row is None else MemoryObject.model_validate(row[0])

    def delete(self, memory_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            cur.execute("DELETE FROM relationships WHERE source_id = %s OR target_id = %s", (memory_id, memory_id))

    def search(self, query: str, top_k: int = 10) -> list[MemoryObject]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT data FROM memories
                WHERE search_vector @@ websearch_to_tsquery('english', %s)
                ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) DESC
                LIMIT %s
                """,
                (query, query, top_k),
            )
            rows = cur.fetchall()
        return [MemoryObject.model_validate(row[0]) for row in rows]

    def list_all(self) -> list[MemoryObject]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM memories")
            rows = cur.fetchall()
        return [MemoryObject.model_validate(row[0]) for row in rows]

    def close(self) -> None:
        self._conn.close()

    # --- Step 82: session-scoped tenant context, checked at the DB layer ---

    def set_tenant_context(self, tenant_id: "str | None") -> None:
        """Scopes every subsequent query on this connection to one
        tenant, enforced by the RLS policy in `_init_schema` -- not by
        this adapter's own Python code, which never re-filters rows
        itself. `None` clears the context back to "unscoped" (see all
        rows), the same default RetrievalEngine.retrieve() uses."""
        with self._conn.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", (tenant_id,))

    # --- Step 87: pgvector similarity search ---

    def vector_search(self, query: str, top_k: int = 10) -> list[MemoryObject]:
        embedding = _vector_literal(self.embedder.embed(query))
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM memories ORDER BY embedding <=> %s::vector LIMIT %s",
                (embedding, top_k),
            )
            rows = cur.fetchall()
        return [MemoryObject.model_validate(row[0]) for row in rows]

    # --- Step 88: hybrid full-text + vector search ---

    def hybrid_search(self, query: str, top_k: int = 10, alpha: float = 0.5) -> list[MemoryObject]:
        """One query, one ranking: `alpha` weights full-text rank against
        vector similarity (1 - cosine distance). Not a tuned relevance
        formula (retrieval.py's own fusion carries the same disclaimer)
        -- the point is that hybrid ranking happens inside the database
        in a single statement, not as two retrievers merged in Python."""
        embedding = _vector_literal(self.embedder.embed(query))
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT data,
                    (%s * COALESCE(ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)), 0)
                     + (1 - %s) * (1 - (embedding <=> %s::vector))) AS score
                FROM memories
                ORDER BY score DESC NULLS LAST
                LIMIT %s
                """,
                (alpha, query, alpha, embedding, top_k),
            )
            rows = cur.fetchall()
        return [MemoryObject.model_validate(row[0]) for row in rows]

    # --- Step 89: persisted relationship graph ---

    def add_relationship(
        self, source_id: str, relationship_type: RelationshipType, target_id: str, **metadata
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO relationships (source_id, relationship_type, target_id, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id, relationship_type, target_id) DO UPDATE SET metadata = excluded.metadata
                """,
                (source_id, relationship_type.value, target_id, psycopg2.extras.Json(metadata)),
            )

    def relationships_from(
        self, source_id: str, relationship_type: "RelationshipType | None" = None
    ) -> list[MemoryRelationship]:
        return self._query_relationships("source_id", source_id, relationship_type)

    def relationships_to(
        self, target_id: str, relationship_type: "RelationshipType | None" = None
    ) -> list[MemoryRelationship]:
        return self._query_relationships("target_id", target_id, relationship_type)

    def _query_relationships(
        self, column: str, value: str, relationship_type: "RelationshipType | None"
    ) -> list[MemoryRelationship]:
        sql = f"SELECT source_id, relationship_type, target_id, metadata FROM relationships WHERE {column} = %s"
        params: list = [value]
        if relationship_type is not None:
            sql += " AND relationship_type = %s"
            params.append(relationship_type.value)
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [
            MemoryRelationship(source_id=r[0], relationship_type=RelationshipType(r[1]), target_id=r[2], metadata=r[3])
            for r in rows
        ]

    def sync_relationship_graph(self, graph: RelationshipGraph) -> None:
        """Writes every edge currently in an in-memory RelationshipGraph
        into the `relationships` table. One-directional (graph -> DB) --
        RelationshipGraph is still the live object callers build lineage
        queries against; this is a durability snapshot underneath it,
        not a replacement for it."""
        for edge in graph.edges():
            self.add_relationship(edge.source_id, edge.relationship_type, edge.target_id, **edge.metadata)

    def load_relationship_graph(self) -> RelationshipGraph:
        """The reverse direction: rebuilds a fresh in-memory
        RelationshipGraph from everything persisted so far -- how a new
        process picks the graph back up after a restart."""
        graph = RelationshipGraph()
        with self._conn.cursor() as cur:
            cur.execute("SELECT source_id, relationship_type, target_id, metadata FROM relationships")
            rows = cur.fetchall()
        for source_id, relationship_type, target_id, metadata in rows:
            graph.add(source_id, RelationshipType(relationship_type), target_id, **metadata)
        return graph
