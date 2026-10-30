"""Architecture guard: the domain package must stay framework-independent."""

import ast
from pathlib import Path

AUTOPSY_ROOT = Path(__file__).resolve().parents[1] / "autopsy"
FORBIDDEN_IMPORT_ROOTS = {
    "backend",
    "fastapi",
    "sqlalchemy",
    "sqlite3",
    "starlette",
}


def _import_roots(module_path: Path) -> set[str]:
    """Return the top-level module names imported by one Python file."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_autopsy_has_no_web_backend_or_database_imports() -> None:
    violations: list[str] = []
    for module_path in sorted(AUTOPSY_ROOT.rglob("*.py")):
        forbidden = _import_roots(module_path) & FORBIDDEN_IMPORT_ROOTS
        if forbidden:
            relative = module_path.relative_to(AUTOPSY_ROOT)
            violations.append(f"{relative}: {sorted(forbidden)}")

    assert not violations, "autopsy must stay independent:\n" + "\n".join(violations)
