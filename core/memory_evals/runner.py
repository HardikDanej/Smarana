"""
Benchmark runner (Plan Step 93): exercises the real engine end to end
against scenarios.py and reports Step 92's metrics as actual numbers --
"here are the numbers," not "I think it works."

Runs against SQLiteAdapter, the same dev-scale default every other test
in this codebase uses: a benchmark that reports Recall@K has no business
requiring a running Postgres service just to do that, and
PostgresAdapter's own correctness is what test_postgres_adapter.py
already proves separately. Importing an adapter here is not an
adapter-isolation violation -- that gate only covers core/memory_os
itself; memory_evals/ is a harness that wires a concrete adapter in,
exactly like tests/ does and exactly like a real caller would.
"""

from __future__ import annotations

from dataclasses import dataclass

from adapters.sqlite_adapter import SQLiteAdapter
from memory_os.metrics import mean_reciprocal_rank, precision_at_k, recall_at_k
from memory_os.retrieval import RetrievalEngine

from .scenarios import SCENARIOS, RetrievalScenario


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    recall_at_k: float
    precision_at_k: float
    mean_reciprocal_rank: float


def run_scenario(scenario: RetrievalScenario) -> ScenarioResult:
    db = SQLiteAdapter()
    for memory in scenario.memories:
        db.store(memory)

    results = RetrievalEngine(db).retrieve(scenario.query, top_k=scenario.top_k)
    retrieved_ids = [r.memory.id for r in results]

    return ScenarioResult(
        name=scenario.name,
        recall_at_k=recall_at_k(scenario.relevant_ids, retrieved_ids, k=scenario.top_k),
        precision_at_k=precision_at_k(scenario.relevant_ids, retrieved_ids, k=scenario.top_k),
        mean_reciprocal_rank=mean_reciprocal_rank(scenario.relevant_ids, retrieved_ids),
    )


def run_all(scenarios: "list[RetrievalScenario] | None" = None) -> list[ScenarioResult]:
    return [run_scenario(s) for s in (scenarios if scenarios is not None else SCENARIOS)]


def format_report(results: list[ScenarioResult]) -> str:
    """A plain-text table, meant to be read by a person or piped into
    telemetry -- not parsed by more code."""
    header = f"{'scenario':<28}{'recall@k':>10}{'precision@k':>13}{'mrr':>8}"
    rows = [
        f"{r.name:<28}{r.recall_at_k:>10.2f}{r.precision_at_k:>13.2f}{r.mean_reciprocal_rank:>8.2f}"
        for r in results
    ]
    return "\n".join([header, *rows])
