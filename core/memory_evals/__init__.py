"""memory-evals (Plan Step 93): a benchmark repo reporting real numbers
against the real engine, not a claim that "it works." See runner.py."""

from .runner import ScenarioResult, format_report, run_all, run_scenario
from .scenarios import SCENARIOS, RetrievalScenario

__all__ = [
    "RetrievalScenario",
    "SCENARIOS",
    "ScenarioResult",
    "format_report",
    "run_all",
    "run_scenario",
]
