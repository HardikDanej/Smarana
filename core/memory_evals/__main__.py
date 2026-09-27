"""Run with: PYTHONPATH=. python3 -m memory_evals (from core/)."""

from .runner import format_report, run_all

if __name__ == "__main__":
    print(format_report(run_all()))
