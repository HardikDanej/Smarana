# scripts/

`tier_screen.py` is an optional, local calibrated cross-check for Phase 2
(Tier Resolution) — see `workflows/tier-screen.md` for the workflow it's
called from and `SKILL.md`'s Phase 2 for where it fits in the pipeline.

## Install

```bash
pip install -r requirements.txt
```

This pulls in [`laya`](https://huggingface.co/convaiinnovations/laya) and its
own dependencies (torch, transformers, safetensors, huggingface_hub) — a real
dependency-weight increase, similar in kind to `server/`'s `chromadb`
addition for `search_memory`. It is entirely optional: `tier_screen.py`
degrades to a structured `{"error": "..."}` response with every field null
if `laya` isn't installed, and Phase 2 falls back to its own unassisted
resolution procedure in that case — nothing in the pipeline requires this
script to be present.

## Usage

```bash
echo '{"candidate_text": "Switched session storage from Redis to Postgres-backed sessions.", "existing_context": "[ADR-002] Session storage: Redis. Status: active."}' | python tier_screen.py
```

or with a file argument instead of stdin:

```bash
python tier_screen.py path/to/input.json
```

Always prints exactly one line of JSON to stdout and exits 0, whether or not
`laya` loaded successfully or inference ran.

## Known limitations

- **First run downloads the model.** `laya.load("convaiinnovations/laya")`
  fetches the checkpoint from Hugging Face on first use (roughly 1.2–1.7GB
  for the English checkpoint) and caches it under the Hugging Face cache
  directory afterward. On a slow or interrupted connection this can take
  several minutes, or stall.
- **CPU latency is real, not the marketing number.** The model card and
  `laya`'s own MCP server docstring cite ~33ms/question on GPU and
  ~200ms/question on CPU. On a CPU-only torch build (no CUDA) this was
  measured at roughly 3–10 seconds for the full three-question batch in this
  script — noticeably higher than either published figure, on ordinary
  consumer hardware with no GPU. `fast=True` on `laya.load()` is a
  TileLang GPU-only path and does not help on CPU. This is a one-time cost
  per Phase 2 write it's actually invoked for, not per turn — but it is not
  instant, and this script does not pretend otherwise.
- **The checkpoint ships with some miscalibrated temperatures.** `laya`
  itself warns on load (`RuntimeWarning: ... this checkpoint ships invalid
  temperatures or values outside [0.5, 5]...`) for a subset of its internal
  option buckets. Treat `tier_placement.confidence` and the two cross-checks'
  `probability` as a useful second signal, not ground truth — this is why
  `workflows/tier-screen.md` treats disagreement with Claude's own Phase 2
  reading as a prompt to double-check, never as an automatic override.
- **No automated test invokes the real model.** `tests/test_tier_screen.py`
  covers the script's input-parsing and error-handling contract by
  substituting a fake `laya` module — it never downloads weights or runs
  inference, matching this repo's existing pattern of automated tests for
  the deterministic parts of the pipeline only (see `tests/README.md`, and
  `server/test_oauth_flow.py` for the same manual-smoke-test precedent on
  the server side). Verify real inference manually with the command above
  after `pip install -r requirements.txt`.
