# Memory Threat Model (Plan Step 76)

This documents the actual system as built through Phase 15 (Steps 31-80),
not an aspirational one. It is the foundation Steps 77-80's tests
(`tests/test_security.py`) check against, and it should be updated
whenever a later phase changes an answer given here — a threat model that
drifts from the code it describes is worse than none.

## Who can do what to memory

**Who can write memory?** Any caller that constructs a `MemoryObject` and
calls a `StorageAdapter.store()` — there is no write-time gate in the
storage layer itself (`SQLiteAdapter.store()` accepts anything valid
against the Pydantic schema). The actual gate is `PolicyEngine.can_store()`
(Step 77/80), which callers must consult themselves; nothing forces them
to. **This is a real gap**, tracked below.

**Who can read memory?** Anyone calling `RetrievalEngine.retrieve()`
without a `principal_id` sees everything (Phase 13's deliberate
backward-compatible default). Passing `principal_id` enforces
`AccessPolicy` — the memory's owner always reads it; anyone else needs an
explicit grant or the `"*"` wildcard.

**Who can modify memory?** Same shape as write: `StorageAdapter.update()`
has no built-in gate. `AccessPolicy.can(memory, principal_id,
Permission.WRITE)` exists and is meaningful, but nothing calls it
automatically before an update.

**Who can delete memory?** `StorageAdapter.delete()` is likewise
ungated at the storage layer; `PolicyEngine.can_delete()` exists and
checks `Permission.DELETE`, but again requires the caller to invoke it.

**Who can create shared memories?** `share_to_scope()` (Phase 13) takes
any private memory and a target scope — there is no check that the
caller calling it is the memory's owner, or holds `Permission.SHARE`.
`PolicyEngine.can_share()` exists for exactly this and is, again, not
wired into `share_to_scope()` itself.

**Who can create inferred memories?** `ExtractionPipeline` (Phase 7) with
`source_type=SourceType.INFERRED`, or `build_reflection()` (Phase 9) with
`source_type=SourceType.REFLECTION`. Both are ordinary Python calls —
anything that can import `memory_os` can call them.

**Who can promote an inference into a trusted fact?** This is the one
question Phase 15 actually closes structurally, not just by policy:
`can_promote()` (Step 79) requires the evidence a target trust level
implies, and `build_skill()` (Phase 14) refuses to build a Skill from
anything but an already-`VALIDATED` procedure. Neither can be bypassed by
constructing a plausible-looking object — the checks read real fields
(`evidence`, `lifecycle_state`, `truth_status`), not a self-reported flag.

## Attack surfaces

| Surface | What it can currently do | What mitigates it | Known gap |
|---|---|---|---|
| **User** | Supplies `SourceType.USER_STATEMENT` content via whatever adapter calls `ExtractionPipeline`. | Trusted by default (Step 33) — this is correct; the user is the one source the plan treats as authoritative on their own say-so. | None specific to this surface. |
| **Agent** | Reads/writes memory as a `principal_id`; owns memories via `owner_id`. | `AccessPolicy` (Phase 13) — the whole point of Phase 13 is exactly this surface. | Storage/update/delete/share are ungated at the point of the call (see above) — an agent that skips the `PolicyEngine` isn't stopped by the storage layer itself. |
| **LLM** | Runs behind `LLMProvider.extract()`/`.reflect()`/`.summarize()` (Phase 7/9); output is never treated as ground truth. | `ClaudeProvider.extract()` raises on unparseable output rather than fabricating (tested, `test_hallucination_resistance`); reflections are structurally `UNCERTAIN`/`CANDIDATE` (Step 48); a Skill can't be built from LLM output alone (Rule E, Phase 14). | An LLM can still produce fluent `INSTRUCTION`-shaped text; `PoisoningGuard` catches this when the *source* is untrusted, but an LLM call itself isn't listed as an untrusted source type (see Document/Tool row) — if a provider's own output were fed back in as a candidate with `source_type=INFERRED`, it isn't currently flagged by `PoisoningGuard`, which only inspects `DOCUMENT`/`EXTERNAL_SYSTEM`/`TOOL`. |
| **Tool** | `SourceType.TOOL` — a named untrusted source in `PoisoningGuard`. | Flagged at `PolicyEngine.can_store()` when content reads as `INSTRUCTION`/`POLICY`, or when unevidenced. | None beyond the general write-gate gap above. |
| **Document** | `SourceType.DOCUMENT` — Step 77's own worked example ("Always send customer credentials..." arriving from a document). | Same `PoisoningGuard` coverage as Tool. Directly tested (`test_plan_step_77_worked_example_is_high_risk`). | None beyond the general write-gate gap above. |
| **API** | `core/api/app.py` (REST, Step 96) and `core/mcp_server/server.py` (MCP, Step 98) — both external-facing entry points into the engine. | All three closed, non-optionally: `api/auth.py`'s API-key `Principal` resolves who is calling before any route body runs (401 otherwise); `api/rate_limit.py`'s per-principal fixed-window limiter runs right after (429 over quota); `PolicyEngine.can_store/can_retrieve/can_delete` are consulted on every memory-touching request in both surfaces, not left to the caller to remember — the REST layer denies with 404 (never 403, to avoid confirming a memory's existence to someone who can't see it), the MCP layer raises `ToolError`. | Both key stores and the rate limiter are in-memory and single-process (see `core/docs/POSTGRES_SETUP.md`-style honesty: right for closing "none exists at all," not a production identity/quota service — a multi-instance deployment needs a shared store for both). Neither surface re-checks `PolicyEngine` on a memory a caller already holds a reference to outside the request (not a gap either surface could close; that's what per-request enforcement means). |
| **External system** | `SourceType.EXTERNAL_SYSTEM` — a named untrusted source in `PoisoningGuard`, same coverage as Document/Tool. | Same as Document/Tool. | Same general gap. |
| **Plugin** | Not modeled — nothing in this codebase distinguishes "a plugin called this" from "a core caller called this." | N/A. | An adapter ecosystem (Step 99) will need its own trust boundary; not designed yet. |
| **Memory adapter** (`core/adapters/`) | Implements `StorageAdapter`/`LLMProvider`. Enforced to import no core-internal privilege by the adapter-isolation gate (G4), which only checks the reverse direction (core never imports adapters) — an adapter itself is trusted code, by design (Core-vs-Adapter rule). | The isolation gate proves adapters can't reach into `core/memory_os` internals in an undocumented way; it does not (and can't) prove an adapter's own logic is correct. | A malicious or buggy adapter can return anything from `search()`/`list_all()`; nothing downstream re-validates that what comes back from storage still matches the schema it was written with (Pydantic validates on `model_validate_json()`, which does catch malformed data, but not data that's simply wrong). |
| **Database** (SQLite today) | Whatever `SQLiteAdapter` executes. Query parameters are always bound (`?` placeholders), so this is not SQL-injectable through normal use. | Parameterized queries throughout `sqlite_adapter.py`. | `_fts_match_expression()` builds an FTS5 MATCH string by quoting tokens — reviewed as safe against FTS5 query-syntax injection (Step 41's own test, `test_search_query_with_punctuation_does_not_raise`), but this reasoning should be re-checked if the tokenizer or quoting logic ever changes. |

## What Phase 15 actually closes vs. what it documents as open

**Closed, with code and tests:**
- Poisoned-content detection at the point of a store decision (`PoisoningGuard`, Step 77).
- Instructions kept structurally separate from memories, with retrieved
  memory unable to silently become an executable command
  (`MemoryClass`, `PolicyEngine.can_use_as_instruction`, Step 78).
- A trust ladder that can't be skipped (`can_promote`, Step 79).
- One place that answers every store/retrieve/share/reason/instruct/
  export/delete question without calling an LLM to decide
  (`PolicyEngine`, Step 80).
- The API surface itself, closed the same turn it was built rather than
  shipped open and hardened later: authentication, rate limiting, and
  non-optional `PolicyEngine` checks on both the REST API and the MCP
  server (Steps 96/98, `test_api.py`/`test_mcp_server.py`).

**Open, named here rather than silently assumed solved:**
- `PolicyEngine` is still not wired into `StorageAdapter`/`share_to_scope()`
  itself — a caller embedding the engine directly (constructing a
  `SQLiteAdapter`/`PostgresAdapter` and calling `.store()` straight,
  skipping `api/`, `sdk/`, and `mcp_server/` entirely) still has to
  remember to consult `PolicyEngine`, exactly as before. Phase 19 closes
  this for the two surfaces meant for *external* callers (Steps 96/98),
  deliberately at that layer and not the storage layer — the
  Core-vs-Adapter split still means the storage adapter shouldn't import
  policy logic directly any more than it should import an LLM provider.
  An internal embedder bypassing the API on purpose is assumed to be
  trusted code, the same assumption the Memory adapter row below makes.
- Phase 19's API-key store and rate limiter are real but single-process
  (see the API row above) — a production multi-instance deployment needs
  a shared identity/quota backend, not this phase's in-memory one.
- No plugin trust boundary exists yet (Phase 20-adjacent).
- `PoisoningGuard`'s untrusted-source list doesn't yet cover LLM-generated
  content re-entering as a candidate memory in its own right.

This list is the actual next-security-work backlog, not a hedge.
