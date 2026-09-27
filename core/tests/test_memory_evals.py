"""Phase 18 (Plan Step 93): memory-evals/ benchmark repo."""

from memory_evals import SCENARIOS, format_report, run_all, run_scenario


def _scenario(name: str):
    return next(s for s in SCENARIOS if s.name == name)


def test_needle_in_decoys_finds_the_target():
    result = run_scenario(_scenario("needle_in_decoys"))
    assert result.recall_at_k == 1.0
    assert result.mean_reciprocal_rank == 1.0


def test_no_relevant_memory_exists_scores_zero_not_a_crash():
    # The honest negative case: nothing to find, so recall/precision are
    # both 0.0 -- not undefined, not a crash, not a false 1.0.
    result = run_scenario(_scenario("no_relevant_memory_exists"))
    assert result.recall_at_k == 0.0
    assert result.precision_at_k == 0.0


def test_multiple_relevant_memories_both_get_credited():
    result = run_scenario(_scenario("multiple_relevant_memories"))
    assert result.recall_at_k == 1.0


def test_run_all_covers_every_bundled_scenario():
    results = run_all()
    assert {r.name for r in results} == {s.name for s in SCENARIOS}


def test_format_report_lists_every_scenario_by_name():
    report = format_report(run_all())
    for scenario in SCENARIOS:
        assert scenario.name in report
