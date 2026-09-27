"""
Adaptive Configuration Profiles (Phase 21 -- not one of the plan's
original 100 steps; the highest-priority gap I flagged when first
synthesizing that plan: "adapts to the environment of the user's use
case, application type, and business type" stayed a marketing sentence,
not an architecture, without this).

A TenantProfile is a real answer to "this tenant is a healthcare app, so
default privacy classes/retention are X; this tenant is an e-commerce
store, so they're Y" -- registered once per tenant, at tenant-creation
time, then consulted by any surface (REST, MCP, direct embedding) that
creates a memory without the caller explicitly overriding its sensitivity,
privacy categories, or tags.

Three things a profile supplies, matching the gap's own wording exactly:

- **Default policy bundles** (`PolicyDefaults`): a starting `sensitivity`
  and `privacy_categories` for a new memory of this tenant's, applied
  only when the caller didn't specify their own.
- **Taxonomy extensions** (`additional_tags`): open-ended, tenant-specific
  categorization via `MemoryObject.tags` -- deliberately NOT an extension
  of the closed, reviewed `PrivacyCategory` enum (Step 83), which stays
  fixed. Extending a security-relevant enum per tenant would mean an
  unreviewed string silently gaining security meaning; `tags` carries no
  special handling anywhere in PolicyEngine, so there's nothing for an
  unreviewed value to compromise.
- **Retention rules** (`RetentionPolicy`): how long this tenant's memories
  live before `retention.py`'s sweep marks them FORGOTTEN (never deletes
  -- Step 35's "a memory never silently disappears" holds here too).

Explicitly NOT included, to keep this honest: this module names no
compliance regime (SOC 2 / HIPAA / GDPR / ...) and makes no certification
claim. The per-industry starting defaults below are reasonable starting
points a deployer can override entirely, not a legal or regulatory
determination -- gap #2 in docs/UNIVERSAL_MEMORY_OS_PLAN.md's own list
("'most secure system' isn't a spec until you pick a target") is
unresolved by this module and stays unresolved on purpose; picking an
actual compliance target is a business decision, not one this module can
make on a deployer's behalf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import PrivacyCategory, PrivacyLevel


class Industry(str, Enum):
    """A deliberately small starter set -- real, not padded to look
    exhaustive. Extend as a real tenant needs an industry not listed;
    GENERAL is the honest fallback, not a silent default masquerading as
    a considered choice."""

    GENERAL = "general"
    HEALTHCARE = "healthcare"
    FINANCIAL = "financial"
    ECOMMERCE = "ecommerce"


class ApplicationType(str, Enum):
    CONSUMER_APP = "consumer_app"
    B2B_SAAS = "b2b_saas"
    INTERNAL_TOOL = "internal_tool"
    AGENT_FRAMEWORK = "agent_framework"


class BusinessType(str, Enum):
    B2B = "b2b"
    B2C = "b2c"
    B2B2C = "b2b2c"


@dataclass(frozen=True)
class PolicyDefaults:
    """The "default policy bundle" -- applied to a new memory only when
    the caller didn't specify these fields themselves. Never overrides
    an explicit value; see apply_profile_defaults()."""

    sensitivity: PrivacyLevel = PrivacyLevel.INTERNAL
    privacy_categories: tuple[PrivacyCategory, ...] = ()
    additional_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetentionPolicy:
    """`default_retention_days=None` means no automatic expiry -- the
    behavior every tenant had before this phase, and the correct default
    for a profile that hasn't considered retention at all."""

    default_retention_days: "int | None" = None


@dataclass(frozen=True)
class TenantProfile:
    tenant_id: str
    industry: Industry
    application_type: ApplicationType
    business_type: BusinessType
    policy_defaults: PolicyDefaults = field(default_factory=PolicyDefaults)
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)

    @classmethod
    def for_industry(
        cls,
        tenant_id: str,
        industry: Industry,
        application_type: ApplicationType,
        business_type: BusinessType,
        *,
        policy_defaults: "PolicyDefaults | None" = None,
        retention: "RetentionPolicy | None" = None,
    ) -> "TenantProfile":
        """Builds a profile starting from that industry's reasonable
        defaults (below), with `policy_defaults`/`retention` as an
        explicit override for either or both -- "at tenant-creation
        time" means this classmethod runs once, not a hidden default a
        caller can't see or change."""
        return cls(
            tenant_id=tenant_id,
            industry=industry,
            application_type=application_type,
            business_type=business_type,
            policy_defaults=policy_defaults if policy_defaults is not None else _DEFAULT_POLICY_BUNDLES[industry],
            retention=retention if retention is not None else _DEFAULT_RETENTION[industry],
        )


# Starting points, not a compliance determination -- see this module's
# own docstring. A deployer overrides any of this per-tenant via
# TenantProfile.for_industry()'s own keyword arguments.
_DEFAULT_POLICY_BUNDLES: dict[Industry, PolicyDefaults] = {
    Industry.GENERAL: PolicyDefaults(),
    Industry.HEALTHCARE: PolicyDefaults(
        sensitivity=PrivacyLevel.CONFIDENTIAL,
        privacy_categories=(PrivacyCategory.PERSONAL,),
    ),
    Industry.FINANCIAL: PolicyDefaults(
        sensitivity=PrivacyLevel.CONFIDENTIAL,
        privacy_categories=(PrivacyCategory.FINANCIAL,),
    ),
    Industry.ECOMMERCE: PolicyDefaults(
        sensitivity=PrivacyLevel.INTERNAL,
        privacy_categories=(PrivacyCategory.PERSONAL,),
    ),
}

_DEFAULT_RETENTION: dict[Industry, RetentionPolicy] = {
    Industry.GENERAL: RetentionPolicy(default_retention_days=None),
    # ~7 years -- a common recordkeeping period in both regimes, not a
    # citation to a specific regulation this module doesn't name.
    Industry.HEALTHCARE: RetentionPolicy(default_retention_days=2555),
    Industry.FINANCIAL: RetentionPolicy(default_retention_days=2555),
    Industry.ECOMMERCE: RetentionPolicy(default_retention_days=730),
}


class TenantProfileStore:
    """In-memory, single-process -- the same honesty as api/auth.py's
    APIKeyStore and api/rate_limit.py's RateLimiter: right for a first
    real registry, not a claim this is a production-scale profile
    service. A real deployment swaps this for a real one (a database
    table) behind the same two methods."""

    def __init__(self):
        self._profiles: dict[str, TenantProfile] = {}

    def register(self, profile: TenantProfile) -> None:
        self._profiles[profile.tenant_id] = profile

    def get(self, tenant_id: "str | None") -> "TenantProfile | None":
        if tenant_id is None:
            return None
        return self._profiles.get(tenant_id)


def apply_profile_defaults(
    profile: "TenantProfile | None",
    *,
    sensitivity: "PrivacyLevel | None",
    privacy_categories: "list[PrivacyCategory] | None",
    tags: "list[str] | None",
) -> tuple[PrivacyLevel, list[PrivacyCategory], list[str]]:
    """Resolves what a new memory's sensitivity/privacy_categories/tags
    should actually be: an explicit (non-None) argument always wins;
    otherwise the tenant's profile default; otherwise
    MemoryObject's own hardcoded default (PrivacyLevel.INTERNAL, no
    categories, no tags) when there's no profile at all. This is the one
    function every surface (api/app.py, mcp_server/server.py, a direct
    caller) calls, so "explicit beats profile beats hardcoded" is
    decided once, not reimplemented per surface."""
    bundle = profile.policy_defaults if profile is not None else PolicyDefaults()
    resolved_sensitivity = sensitivity if sensitivity is not None else bundle.sensitivity
    resolved_categories = (
        privacy_categories if privacy_categories is not None else list(bundle.privacy_categories)
    )
    resolved_tags = tags if tags is not None else list(bundle.additional_tags)
    return resolved_sensitivity, resolved_categories, resolved_tags
