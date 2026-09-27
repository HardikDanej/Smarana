"""
Gate check for Plan Step 38: "Claude must be an adapter, not the
architecture." Proves core/memory_os never imports core/adapters, in
either direction that would matter: the engine must be able to run
without the adapter package present at all.
"""

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MEMORY_OS_DIR = REPO_ROOT / "memory_os"


def imports_adapters(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] == "adapters" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] == "adapters":
                return True
    return False


def main() -> None:
    # Positive control: prove the checker can detect the violation before
    # trusting a clean scan of the real package.
    if not imports_adapters("from adapters.claude_provider import ClaudeProvider\n"):
        print("CONTROL FAILED: checker did not flag a known violation", file=sys.stderr)
        sys.exit(1)

    violations = []
    for path in sorted(MEMORY_OS_DIR.rglob("*.py")):
        if imports_adapters(path.read_text()):
            violations.append(str(path))

    if violations:
        for path in violations:
            print(f"VIOLATION: {path} imports core/adapters", file=sys.stderr)
        sys.exit(1)

    print("GATE_G4_ADAPTER_ISOLATION")


if __name__ == "__main__":
    main()
