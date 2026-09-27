# Adaptive Configuration Profiles (Phase 21)

Not one of the plan's original 100 steps. This is the highest-priority
gap I flagged when first synthesizing `docs/UNIVERSAL_MEMORY_OS_PLAN.md`
from the four source files: "adapts to the environment of the user's
use case, application type, and business type" stayed a marketing
sentence, not an architecture, without it. `docs/V1_ARCHITECTURE.md`'s
closing list named it as gap #1, explicitly deferred at the V1 freeze.
This phase closes it — `memory_os.__version__` moves from `1.0.0` to
`1.1.0`: additive and backward compatible, not a reopening of the freeze
(nothing frozen in `V1_ARCHITECTURE.md`'s 32 sections changed shape).

## What it is

`memory_os/profiles.py`'s `TenantProfile`: registered once per tenant,
at tenant-creation time, carrying exactly the three things the gap
named:

- **Default policy bundles** (`PolicyDefaults`): a starting
  `sensitivity` and `privacy_categories` for that tenant's memories,
  applied only when a caller creating a memory didn't specify their own
  — an explicit value always wins. `TenantProfile.for_industry()` comes
  with reasonable starting points per `Industry` (healthcare, financial,
  ecommerce, general); a deployer overrides any field explicitly.
- **Taxonomy extensions** (`MemoryObject.tags`, a new additive field):
  open-ended, tenant-specific categorization, deliberately *not* an
  extension of the closed `PrivacyCategory` enum (Step 83). That enum
  stays fixed and reviewed on purpose — letting a tenant inject
  unreviewed values into a security-relevant taxonomy would be a real
  regression, not flexibility. `tags` carries no special handling
  anywhere in `PolicyEngine`; there's nothing for an unreviewed value to
  compromise.
- **Retention rules** (`RetentionPolicy` + `memory_os/retention.py`'s
  `sweep_expired_memories()`): how long a tenant's memories live before
  being marked `FORGOTTEN` — never physically deleted, the same "a
  memory never silently disappears" rule Step 35's supersession already
  established. A plain function, not a scheduler; a deployer calls it
  periodically (an external cron job), the same way any other
  maintenance task would run.

## Where it's wired in

`memory_os.profiles.apply_profile_defaults()` is the one function every
surface calls to resolve "explicit value, else profile default, else
hardcoded default" — decided once, not reimplemented per surface:

- **REST API** (`api/app.py`): `create_app(..., profile_store=...)`.
  `MemoryCreateRequest`'s `sensitivity`/`privacy_categories`/`tags`
  became `Optional`, defaulting to `None` — `None` means "the caller
  didn't specify this," distinguishable from an explicit choice, which
  is what lets a profile's default apply at all.
- **MCP server** (`mcp_server/server.py`): `create_mcp_server(...,
  profile_store=...)`. The `remember` tool gained the same three optional
  parameters.
- **Direct embedding**: call `apply_profile_defaults()` yourself before
  constructing a `MemoryObject`.

`TenantProfileStore` is in-memory and single-process — the same
honesty as `api/auth.py`'s `APIKeyStore` and `api/rate_limit.py`'s
`RateLimiter`: right for a first real registry, not a production-scale
profile service. A real deployment swaps it for a database-backed one
behind the same two methods (`register`/`get`).

## What this does not claim

No compliance regime is named (SOC 2 / HIPAA / GDPR / ISO 27001). The
per-industry defaults in `profiles.py` (e.g., healthcare defaults to
`CONFIDENTIAL` + `PERSONAL`, ~7-year retention) are reasonable starting
points a deployer can override entirely — not a legal or regulatory
determination. Gap #2 in `V1_ARCHITECTURE.md`'s closing list ("no named
compliance target... 'most secure system' isn't a spec until you pick a
target") stays open on purpose: picking an actual compliance target is a
business decision this module can't make on a deployer's behalf, and
pretending otherwise would be a false claim, not a feature.

`PolicyEngine`'s own decision logic is unchanged — a profile supplies
*defaults for a new memory's fields*, not a per-tenant rewrite of what
`can_store`/`can_retrieve`/`can_delete` decide. Keeping that boundary
is what kept this phase's blast radius contained: every one of the 325
tests passing before this phase still passes unchanged.
