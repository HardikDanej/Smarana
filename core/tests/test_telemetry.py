"""Phase 18 (Plan Step 91): OpenTelemetry instrumentation."""

from adapters.otel_adapter import OTelTelemetry
from adapters.sqlite_adapter import SQLiteAdapter
from memory_os import MemoryScope, PolicyEngine, SemanticType, SourceType, Telemetry
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


def test_otel_telemetry_satisfies_the_protocol():
    assert isinstance(OTelTelemetry(), Telemetry)


def test_span_records_a_named_span_with_attributes():
    telemetry = OTelTelemetry()
    with telemetry.span("some.operation", foo="bar"):
        pass

    spans = telemetry.exported_spans()
    assert [s.name for s in spans] == ["some.operation"]
    assert dict(spans[0].attributes) == {"foo": "bar"}


def test_record_metric_captures_the_value():
    telemetry = OTelTelemetry()
    telemetry.record_metric("some.metric", 0.75, tag="x")

    data = telemetry.collected_metrics()
    points = [
        dp
        for rm in data.resource_metrics
        for sm in rm.scope_metrics
        for m in sm.metrics
        if m.name == "some.metric"
        for dp in m.data.data_points
    ]
    assert points[0].sum == 0.75


def test_retrieval_engine_emits_a_span_and_a_result_count_metric_when_supplied():
    db = SQLiteAdapter()
    db.store(_memory("Project Alpha uses PostgreSQL."))
    telemetry = OTelTelemetry()

    RetrievalEngine(db, telemetry=telemetry).retrieve("PostgreSQL")

    assert [s.name for s in telemetry.exported_spans()] == ["retrieval_engine.retrieve"]
    data = telemetry.collected_metrics()
    metric_names = {m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
    assert "retrieval_engine.result_count" in metric_names


def test_retrieval_engine_works_unchanged_with_no_telemetry_supplied():
    # Opt-in, same as audit_log on PolicyEngine -- every prior test with
    # no telemetry argument keeps passing.
    db = SQLiteAdapter()
    db.store(_memory("Project Alpha uses PostgreSQL."))

    results = RetrievalEngine(db).retrieve("PostgreSQL")

    assert len(results) == 1


def test_policy_engine_emits_a_decision_metric_when_supplied():
    telemetry = OTelTelemetry()
    engine = PolicyEngine(telemetry=telemetry)
    memory = _memory("Still-live fact.")

    engine.can_use_for_reasoning(memory)

    data = telemetry.collected_metrics()
    metric_names = {m.name for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
    assert "policy_engine.decision" in metric_names


def test_policy_engine_works_unchanged_with_no_telemetry_supplied():
    engine = PolicyEngine()
    assert engine.telemetry is None
    assert engine.can_use_for_reasoning(_memory("Still-live fact."))
