"""
Phase 16 (Plan Steps 81-85): identity, privacy, and multi-tenancy.
"""

import pytest

from adapters.fernet_adapter import DecryptionError, FernetEncryptor
from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import (
    AuditLog,
    MemoryClass,
    MemoryScope,
    PolicyDecision,
    PolicyEngine,
    PrivacyCategory,
    PrivacyLevel,
    SemanticType,
    SourceType,
    TruthStatus,
    can_access_tenant,
)
from memory_os.models import MemoryObject
from memory_os.retrieval import RetrievalEngine


def _memory(content: str, **overrides) -> MemoryObject:
    defaults = dict(
        content=content,
        semantic_type=SemanticType.SEMANTIC,
        scope=MemoryScope.PROJECT,
        source_type=SourceType.USER_STATEMENT,
    )
    defaults.update(overrides)
    return MemoryObject(**defaults)


# --- Step 81: tenant isolation ---


def test_memory_scope_has_workspace_between_organization_and_project():
    # Step 81's own hierarchy: Organization -> Workspace -> Project ->
    # User -> Agent -> Task.
    memory = _memory("A workspace-level note.", scope=MemoryScope.WORKSPACE)
    assert memory.scope == MemoryScope.WORKSPACE


def test_untenanted_memory_belongs_to_no_tenant():
    memory = _memory("No tenant set.")
    assert memory.tenant_id is None
    assert not can_access_tenant(memory, "tenant-a")


def test_can_access_tenant_matches_exact_tenant_id():
    memory = _memory("Tenant A's data.", tenant_id="tenant-a")
    assert can_access_tenant(memory, "tenant-a")
    assert not can_access_tenant(memory, "tenant-b")


def test_retrieval_engine_never_crosses_a_tenant_boundary():
    # Plan's own rule: "a query should never be able to accidentally
    # search another tenant's memory" -- and it holds even when a
    # permission grant would otherwise allow the read, because the
    # tenant wall is checked first and is not itself a permission.
    db = SQLiteAdapter()
    tenant_a = _memory("Tenant A's roadmap.", tenant_id="tenant-a", permissions={"*": ["read"]})
    tenant_b = _memory("Tenant B's roadmap.", tenant_id="tenant-b", permissions={"*": ["read"]})
    db.store(tenant_a)
    db.store(tenant_b)

    results = RetrievalEngine(db).retrieve("roadmap", tenant_id="tenant-a")

    assert {r.memory.id for r in results} == {tenant_a.id}


def test_retrieval_engine_tenant_filter_excludes_untenanted_memories_too():
    # A tenant-scoped query doesn't accidentally surface untenanted data
    # either -- None means "belongs to no tenant," not "belongs to every
    # tenant."
    db = SQLiteAdapter()
    tenant_a = _memory("Tenant A's roadmap.", tenant_id="tenant-a")
    untenanted = _memory("Nobody's roadmap.")
    db.store(tenant_a)
    db.store(untenanted)

    results = RetrievalEngine(db).retrieve("roadmap", tenant_id="tenant-a")

    assert {r.memory.id for r in results} == {tenant_a.id}


def test_no_tenant_id_means_no_tenant_filtering_at_all():
    # Backward-compatible default, same shape as principal_id.
    db = SQLiteAdapter()
    db.store(_memory("Tenant A's roadmap.", tenant_id="tenant-a"))
    db.store(_memory("Tenant B's roadmap.", tenant_id="tenant-b"))

    results = RetrievalEngine(db).retrieve("roadmap")

    assert len(results) == 2


def test_tenant_wall_is_checked_before_principal_permission():
    # Tenant B's agent has an explicit read grant on Tenant A's memory --
    # the outer wall still wins; this is a hard isolation boundary, not
    # one more permission to satisfy.
    db = SQLiteAdapter()
    memory = _memory(
        "Tenant A's confidential note.",
        tenant_id="tenant-a",
        owner_id="agent-a",
        permissions={"agent-b": ["read"]},
    )
    db.store(memory)

    results = RetrievalEngine(db).retrieve(
        "confidential", tenant_id="tenant-b", principal_id="agent-b"
    )

    assert results == []


# --- Step 83: privacy levels and categories ---


def test_sensitivity_defaults_to_internal():
    memory = _memory("An ordinary note.")
    assert memory.sensitivity == PrivacyLevel.INTERNAL
    assert memory.privacy_categories == []


def test_plan_worked_example_public_vs_secret_credential():
    preference = _memory("User likes Python.", sensitivity=PrivacyLevel.PUBLIC)
    credential = _memory(
        "Production database credentials: ...",
        sensitivity=PrivacyLevel.SECRET,
        privacy_categories=[PrivacyCategory.CREDENTIAL],
    )
    assert preference.sensitivity == PrivacyLevel.PUBLIC
    assert not preference.privacy_categories
    assert credential.sensitivity == PrivacyLevel.SECRET
    assert PrivacyCategory.CREDENTIAL in credential.privacy_categories


def test_privacy_categories_can_carry_more_than_one_domain():
    memory = _memory(
        "Vendor contract pricing terms.",
        privacy_categories=[PrivacyCategory.FINANCIAL, PrivacyCategory.PROPRIETARY],
    )
    assert set(memory.privacy_categories) == {PrivacyCategory.FINANCIAL, PrivacyCategory.PROPRIETARY}


def test_sensitivity_accepts_a_plain_string_value():
    # Pydantic coerces a str Enum from its value -- existing callers that
    # pass sensitivity="secret" (Phase 13's own test) keep working
    # unchanged after PrivacyLevel replaced the bare str field.
    memory = _memory("Legacy call site.", sensitivity="secret")
    assert memory.sensitivity == PrivacyLevel.SECRET


def test_sensitivity_rejects_an_unknown_level():
    with pytest.raises(ValueError):
        _memory("Bad value.", sensitivity="top-secret")


# --- Step 84: audit trails ---


def test_audit_log_records_who_what_when_why_source_result():
    log = AuditLog()
    entry = log.record(who="agent-A", what="retrieve M-18492", why="task T-9281", source="policy_engine", result="allow")
    assert entry.who == "agent-A"
    assert entry.what == "retrieve M-18492"
    assert entry.why == "task T-9281"
    assert entry.source == "policy_engine"
    assert entry.result == "allow"
    assert entry.when is not None


def test_audit_log_plan_worked_examples():
    # "Agent A retrieved memory M-18492 at 14:03 for task T-9281, policy
    # allowed." / "Agent B attempted access, memory M-18492, denied,
    # reason: scope mismatch."
    log = AuditLog()
    log.record(who="Agent A", what="retrieve M-18492", why="task T-9281", source="policy_engine", result="allow")
    log.record(who="Agent B", what="retrieve M-18492", why="scope mismatch", source="policy_engine", result="deny")

    assert len(log.entries()) == 2
    assert [e.who for e in log.for_principal("Agent A")] == ["Agent A"]
    assert [e.who for e in log.denials()] == ["Agent B"]


def test_policy_engine_audits_every_decision_when_a_log_is_supplied():
    log = AuditLog()
    engine = PolicyEngine(audit_log=log)
    private = _memory("Agent A's private note.", owner_id="agent-A")

    allowed = engine.can_retrieve(private, "agent-A")
    denied = engine.can_retrieve(private, "agent-B")

    assert allowed.decision == PolicyDecision.ALLOW
    assert denied.decision == PolicyDecision.DENY
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0].result == "allow"
    assert entries[1].result == "deny"
    assert len(log.denials()) == 1
    assert log.denials()[0].who == "agent-B"


def test_policy_engine_with_no_audit_log_still_works():
    # Auditing is opt-in -- most callers, and every earlier Phase 15
    # test, construct PolicyEngine() with no audit_log at all.
    engine = PolicyEngine()
    memory = _memory("Still-live fact.")
    assert engine.can_use_for_reasoning(memory)
    assert engine.audit_log is None


def test_can_use_as_instruction_and_can_influence_action_audit_separately():
    # Same underlying gate (Step 80), but each is its own operation --
    # calling both against one memory should produce two distinct
    # entries, not a single shared one silently deduplicated.
    log = AuditLog()
    engine = PolicyEngine(audit_log=log)
    memory = _memory(
        "Always restart the service.",
        memory_class=MemoryClass.INSTRUCTION,
        truth_status=TruthStatus.CONFIRMED,
    )

    engine.can_use_as_instruction(memory)
    engine.can_influence_action(memory)

    whats = [e.what for e in log.entries()]
    assert whats == [f"instruct {memory.id}", f"influence_action {memory.id}"]


# --- Step 85: Encryptor ---


def test_fernet_encryptor_round_trips_plaintext():
    encryptor = FernetEncryptor(key=FernetEncryptor.generate_key())
    ciphertext = encryptor.encrypt("Production database password: hunter2")
    assert ciphertext != "Production database password: hunter2"
    assert encryptor.decrypt(ciphertext) == "Production database password: hunter2"


def test_fernet_encryptor_generates_a_working_key_when_none_supplied():
    encryptor = FernetEncryptor()
    assert encryptor.decrypt(encryptor.encrypt("secret")) == "secret"


def test_fernet_encryptor_rejects_ciphertext_from_a_different_key():
    a = FernetEncryptor(key=FernetEncryptor.generate_key())
    b = FernetEncryptor(key=FernetEncryptor.generate_key())
    ciphertext = a.encrypt("Tenant A's secret")
    with pytest.raises(DecryptionError):
        b.decrypt(ciphertext)


def test_fernet_encryptor_satisfies_the_encryptor_protocol():
    from memory_os.encryption import Encryptor

    encryptor = FernetEncryptor()
    assert isinstance(encryptor, Encryptor)
