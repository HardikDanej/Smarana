#!/usr/bin/env python3
"""Smarana Tier Screen: an optional, local Laya-based calibrated cross-check for
Phase 2 (Tier Resolution) of the Smarana pipeline (see SKILL.md and
workflows/tier-screen.md).

Given a candidate fact surfaced during a session, plus an optional flattened
digest of the existing Tier 2/Tier 3 context, this asks a small,
non-autoregressive classifier (https://huggingface.co/convaiinnovations/laya)
three questions in one forward pass:

  - tier_placement (choice): which of the three tiers the fact belongs in.
  - contradicts_existing_decision (noul): does it supersede an existing ADR.
  - duplicate_or_noop (noul): is it already present, i.e. a no-op write.

This is a cross-check, never the resolution itself -- Phase 2's own
resolution procedure in SKILL.md is still what actually assigns a tier and
writes the entry. Laya has read only the flattened text it's given here, not
the rest of the conversation; disagreement between its output and the
model's own Phase 2 reasoning is a reason to double check, not a verdict.

Reads one JSON object from a file path given as argv[1], or from stdin if no
argv[1] is given: {"candidate_text": "...", "existing_context": "..."}
(`existing_context` is optional and defaults to "".)

Always prints exactly one line of JSON to stdout and exits 0, even when Laya
isn't installed or inference fails -- a broken screen must never block a
memory write or crash the pipeline. A failure is reported as {"error": "..."}
with `tier_placement: null` and both cross-checks' probability null / flagged
false, so it can never manufacture a false tier assignment or a false
supersede/duplicate flag.
"""
import json
import sys
import time

FLAG_THRESHOLD = 0.85

TIER_QUESTION = {
    "type": "choice",
    "instructions": (
        "A new fact surfaced during a project conversation needs to be filed "
        "into exactly one of three memory tiers. Tier 1 (active execution) "
        "holds a current task, an in-flight bug, or temporary/uncommitted "
        "state that stops being true once the current task ships. Tier 2 "
        "(architecture & decisions) holds a structural or technical choice "
        "-- tech stack, API contract, database schema, architecture pattern "
        "-- that future work must respect. Tier 3 (domain rules & "
        "preferences) holds a non-negotiable standing constraint or "
        "preference stated independent of any single task, an 'always' or "
        "'never' rule. Which tier does the candidate fact belong in?"
    ),
    "criteria": {
        "tier1_active_execution": (
            "Current task, in-flight bug, or temporary/uncommitted state."
        ),
        "tier2_architecture_decision": (
            "Structural or technical decision future work must respect."
        ),
        "tier3_domain_rule": (
            "Standing, task-independent constraint or preference."
        ),
    },
}

CROSS_CHECK_QUESTIONS = {
    "contradicts_existing_decision": {
        "type": "noul",
        "instructions": (
            "Given the candidate fact and the existing context (if any), "
            "does the candidate fact contradict or reverse a decision "
            "already recorded in the existing context, such that the old "
            "decision should be marked superseded?"
        ),
    },
    "duplicate_or_noop": {
        "type": "noul",
        "instructions": (
            "Given the candidate fact and the existing context (if any), is "
            "the candidate fact substantively identical to information "
            "already present in the existing context, such that recording "
            "it again would add no new information?"
        ),
    },
}

QUESTIONS = {"tier_placement": TIER_QUESTION, **CROSS_CHECK_QUESTIONS}

EMPTY_RESULT = {
    "tier_placement": None,
    "contradicts_existing_decision": {"probability": None, "flagged": False},
    "duplicate_or_noop": {"probability": None, "flagged": False},
    "flag_threshold": FLAG_THRESHOLD,
}


def emit(obj):
    print(json.dumps(obj))


def load_payload(argv):
    """Read and JSON-parse the input. Returns (payload_dict, error_str)."""
    if len(argv) > 1:
        try:
            with open(argv[1], "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            return None, "could not read input file %s: %s" % (argv[1], e)
    else:
        raw = sys.stdin.read()

    try:
        return (json.loads(raw) if raw.strip() else {}), None
    except json.JSONDecodeError as e:
        return None, "invalid JSON input: %s" % e


def run_screen(payload):
    """Run the Laya pre-screen over one payload dict and return the result
    dict (never raises -- every failure mode becomes a structured error).
    `laya` is imported here, not at module scope, so tests can substitute a
    fake module via sys.modules without needing the real dependency or a
    network call.
    """
    candidate_text = payload.get("candidate_text") or ""
    existing_context = payload.get("existing_context") or ""
    state = {"candidate": candidate_text, "existing_context": existing_context}

    try:
        import laya
    except Exception as e:
        return dict(
            EMPTY_RESULT,
            error=(
                "laya not importable: %s -- run `pip install laya` (or "
                "`pip install -r requirements.txt` in this repo's scripts/ "
                "directory) in the Python environment the memory session's "
                "shell tool resolves" % e
            ),
        )

    try:
        agent = laya.load("convaiinnovations/laya")
    except Exception as e:
        return dict(EMPTY_RESULT, error="laya model load failed: %s" % e)

    # Timed from here, not from laya.load() above: load includes a first-run
    # Hugging Face download (seconds to minutes on a fast connection, far
    # longer or stalled indefinitely on a slow or interrupted one) that would
    # otherwise swamp the actual inference latency this field is meant to
    # report.
    start = time.time()
    try:
        result = agent.predict(state, QUESTIONS)
    except Exception as e:
        return dict(EMPTY_RESULT, error="laya inference failed: %s" % e)
    latency_ms = (time.time() - start) * 1000.0

    answers = result.get("answers", {}) if isinstance(result, dict) else {}

    tier_ans = answers.get("tier_placement") or {}
    tier_placement = None
    if tier_ans.get("choice") is not None:
        tier_placement = {
            "choice": tier_ans.get("choice"),
            "probabilities": tier_ans.get("probabilities"),
            "confidence": tier_ans.get("confidence"),
        }

    cross_checks = {}
    for key in CROSS_CHECK_QUESTIONS:
        ans = answers.get(key) or {}
        prob = ans.get("noul")
        cross_checks[key] = {
            "probability": prob,
            "flagged": bool(prob is not None and prob >= FLAG_THRESHOLD),
        }

    return {
        "model": "laya-english (convaiinnovations/laya)",
        "tier_placement": tier_placement,
        "contradicts_existing_decision": cross_checks["contradicts_existing_decision"],
        "duplicate_or_noop": cross_checks["duplicate_or_noop"],
        "flag_threshold": FLAG_THRESHOLD,
        "latency_ms": round(latency_ms, 1),
        "error": None,
    }


def main(argv=None):
    argv = sys.argv if argv is None else argv
    payload, err = load_payload(argv)
    if err is not None:
        emit(dict(EMPTY_RESULT, error=err))
        return
    emit(run_screen(payload))


if __name__ == "__main__":
    main()
