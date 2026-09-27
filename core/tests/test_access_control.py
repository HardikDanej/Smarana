from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import (
    AccessPolicy,
    MemoryScope,
    Permission,
    RelationshipGraph,
    SemanticType,
    SourceType,
    most_specific,
    share_to_scope,
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


# --- Step 68/69: AccessPolicy ---


def test_owner_always_has_read_access():
    memory = _memory("Agent A's private note.", owner_id="agent-A")
    assert AccessPolicy().can(memory, "agent-A", Permission.READ)


def test_non_owner_has_no_access_by_default():
    memory = _memory("Agent A's private note.", owner_id="agent-A")
    assert not AccessPolicy().can(memory, "agent-B", Permission.READ)


def test_explicit_grant_allows_a_non_owner_specific_permission():
    memory = _memory(
        "Shared note.",
        owner_id="agent-A",
        permissions={"agent-B": ["read"]},
    )
    assert AccessPolicy().can(memory, "agent-B", Permission.READ)
    assert not AccessPolicy().can(memory, "agent-B", Permission.WRITE)


def test_admin_grant_implies_every_other_permission():
    memory = _memory("Shared note.", owner_id="agent-A", permissions={"agent-B": ["admin"]})
    assert AccessPolicy().can(memory, "agent-B", Permission.DELETE)
    assert AccessPolicy().can(memory, "agent-B", Permission.EXPORT)


def test_wildcard_grant_applies_to_any_principal():
    memory = _memory("Public within the store.", owner_id="agent-A", permissions={"*": ["read"]})
    assert AccessPolicy().can(memory, "agent-Z", Permission.READ)
    assert not AccessPolicy().can(memory, "agent-Z", Permission.WRITE)


def test_step_68_worked_example_credentials_restricted_to_one_agent():
    credential = _memory(
        "Production database password: ...",
        owner_id="infrastructure-system",
        permissions={"deployment-agent": ["read"]},
        sensitivity="secret",
    )
    policy = AccessPolicy()
    assert policy.can(credential, "deployment-agent", Permission.READ)
    assert not policy.can(credential, "random-agent", Permission.READ)


# --- Step 66/69: real isolation, enforced in retrieval ---


def test_isolation():
    # This is the test Phase 9's evaluation framework deferred: "Can
    # Agent A accidentally retrieve Agent B's private memory?" Now it
    # can be answered directly, because owner_id and AccessPolicy exist.
    db = SQLiteAdapter()
    agent_a_private = _memory("Agent A's private plan.", owner_id="agent-A")
    agent_b_private = _memory("Agent B's private plan.", owner_id="agent-B")
    db.store(agent_a_private)
    db.store(agent_b_private)

    results_as_a = RetrievalEngine(db).retrieve("plan", principal_id="agent-A")
    results_as_b = RetrievalEngine(db).retrieve("plan", principal_id="agent-B")

    assert {r.memory.id for r in results_as_a} == {agent_a_private.id}
    assert {r.memory.id for r in results_as_b} == {agent_b_private.id}


def test_no_principal_id_means_no_access_filtering_at_all():
    # Backward-compatible default: existing callers who never pass
    # principal_id see everything, exactly as before this phase.
    db = SQLiteAdapter()
    db.store(_memory("Agent A's private plan.", owner_id="agent-A"))
    db.store(_memory("Agent B's private plan.", owner_id="agent-B"))

    results = RetrievalEngine(db).retrieve("plan")

    assert len(results) == 2


def test_shared_memory_is_visible_to_the_agent_it_was_shared_with():
    db = SQLiteAdapter()
    private = _memory("Agent A's private plan.", owner_id="agent-A")
    shared = private.new_version(permissions={"agent-B": ["read"]})
    db.store(shared)

    results = RetrievalEngine(db).retrieve("plan", principal_id="agent-B")

    assert results[0].memory.id == shared.id


# --- Step 67: sharing to a broader scope ---


def test_share_to_scope_creates_a_new_memory_not_a_mutation():
    private = _memory("Deployments fail without env validation.", scope=MemoryScope.AGENT, owner_id="agent-A")

    shared = share_to_scope(private, new_scope=MemoryScope.ORGANIZATION)

    assert shared.id != private.id
    assert shared.scope == MemoryScope.ORGANIZATION
    assert shared.content == private.content
    assert shared.metadata["shared_from"] == private.id
    # The original is untouched.
    assert private.scope == MemoryScope.AGENT


def test_share_to_scope_records_lineage_when_a_graph_is_given():
    from memory_os.relationships import RelationshipType

    private = _memory("A lesson learned.", scope=MemoryScope.AGENT, owner_id="agent-A")
    graph = RelationshipGraph()

    shared = share_to_scope(private, new_scope=MemoryScope.ORGANIZATION, graph=graph)

    lineage = graph.outgoing(shared.id, RelationshipType.DERIVED_FROM)
    assert len(lineage) == 1
    assert lineage[0].target_id == private.id


def test_share_to_scope_can_reassign_owner():
    private = _memory("A lesson learned.", owner_id="agent-A")
    shared = share_to_scope(private, new_scope=MemoryScope.ORGANIZATION, shared_by="org-memory")
    assert shared.owner_id == "org-memory"


# --- Step 70: scope-based precedence ---


def test_step_70_worked_example_most_specific_scope_wins():
    org = _memory("Use AWS.", scope=MemoryScope.ORGANIZATION)
    project = _memory("Use GCP.", scope=MemoryScope.PROJECT)
    task = _memory("Temporary Azure environment.", scope=MemoryScope.TASK)

    winner = most_specific([org, project, task])

    assert winner.id == task.id


def test_most_specific_with_only_broad_scopes():
    org = _memory("Use AWS.", scope=MemoryScope.ORGANIZATION)
    team = _memory("Use GCP within the data team.", scope=MemoryScope.TEAM)

    assert most_specific([org, team]).id == team.id


def test_most_specific_returns_none_for_empty_list():
    assert most_specific([]) is None
