"""
Gate check for Plan Step 31: "We do not connect an LLM yet. The Memory OS
must be able to function as a deterministic data system first."

Scans core/memory_os for imports of any LLM/network provider or other
concrete vendor library, and proves the check itself works by first
running it against a known violation (gates.md's guidance: test an
absence check against a known positive control) before trusting a clean
scan of the real package.

"cryptography", "psycopg2", and "opentelemetry" are in FORBIDDEN
alongside the LLM/network libraries for the same reason: Step 85's
encryption, Step 86's Postgres adapter, and Step 91's telemetry are all
vendor libraries, and the Core-vs-Adapter rule doesn't carve out an
exception for which kind of vendor tech it is -- not even one, like
OpenTelemetry's API package, that is itself designed to be a neutral
abstraction other libraries import directly. FernetEncryptor,
PostgresAdapter, and OTelTelemetry (core/adapters/) are where they
belong; encryption.py's Encryptor Protocol, storage.py's StorageAdapter
Protocol, and telemetry.py's Telemetry Protocol are what memory_os
depends on instead.

"fastapi", "starlette", "uvicorn", and "mcp" extend the same set for
Phase 19 (Steps 96-98): core/api, core/sdk, and core/mcp_server are
consumers of the engine -- the same relationship tests/ and
memory_evals/ already have to it -- not the engine itself, so they wire
these libraries in freely, but memory_os itself must stay just as
unaware of REST/MCP as it is of any other vendor technology.
"""

import ast
import pathlib
import sys

FORBIDDEN = {
    "anthropic",
    "openai",
    "google",  # covers google.generativeai
    "genai",
    "cohere",
    "mistralai",
    "ollama",
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "cryptography",
    "psycopg2",
    "opentelemetry",
    "fastapi",
    "starlette",
    "uvicorn",
    "mcp",
}


def imported_top_level_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def forbidden_imports(source: str) -> set[str]:
    return imported_top_level_modules(source) & FORBIDDEN


def main() -> None:
    # Positive control: a checker that can't detect a real violation proves
    # nothing about the real scan below.
    known_violation = "import openai\n"
    if not forbidden_imports(known_violation):
        print("CONTROL FAILED: checker did not flag a known violation", file=sys.stderr)
        sys.exit(1)

    package_dir = pathlib.Path(__file__).resolve().parent.parent / "memory_os"
    violations: dict[str, set[str]] = {}
    for path in sorted(package_dir.rglob("*.py")):
        hit = forbidden_imports(path.read_text())
        if hit:
            violations[str(path)] = hit

    if violations:
        for path, hit in violations.items():
            print(f"VIOLATION: {path} imports {sorted(hit)}", file=sys.stderr)
        sys.exit(1)

    print("GATE_G2_NO_LLM_DEPENDENCY")


if __name__ == "__main__":
    main()
