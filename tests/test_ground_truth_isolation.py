"""Enforce ground-truth isolation and the fixed subsystem contract."""

from __future__ import annotations

import ast
from pathlib import Path

from prometheus.contracts import SUBSYSTEMS, Subsystem

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "prometheus"


def _modules() -> list[Path]:
    return list(PACKAGE_ROOT.rglob("*.py"))


def _relative(path: Path) -> tuple[str, ...]:
    return path.relative_to(PACKAGE_ROOT).parts


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_sim_eval_and_cli_may_reference_ground_truth() -> None:
    # sim/ writes it, eval/ reads it, and cli.py only passes the output path
    # through to the writer and prints it. No pipeline stage may mention it.
    allowed = {"sim", "eval", "cli.py"}
    offenders = [
        str(Path(*_relative(path)))
        for path in _modules()
        if "ground_truth" in path.read_text(encoding="utf-8")
        and _relative(path)[0] not in allowed
    ]

    assert offenders == [], f"ground truth referenced outside sim/eval/cli: {offenders}"


def test_only_eval_may_import_eval_package() -> None:
    offenders = [
        str(Path(*_relative(path)))
        for path in _modules()
        if any(name.startswith("prometheus.eval") for name in _imported_modules(path))
        and _relative(path)[0] != "eval"
    ]

    assert offenders == [], f"eval package imported outside eval/: {offenders}"


def test_pipeline_never_imports_ground_truth_builder() -> None:
    offenders = [
        str(Path(*_relative(path)))
        for path in _modules()
        if any(
            name == "prometheus.sim.ground_truth"
            for name in _imported_modules(path)
        )
        and _relative(path)[0] not in {"sim", "eval"}
    ]

    assert offenders == [], f"ground truth builder imported outside sim/eval: {offenders}"


def test_subsystems_are_exactly_four() -> None:
    assert [member.value for member in SUBSYSTEMS] == ["power", "thermal", "comms", "adcs"]
    assert SUBSYSTEMS == tuple(Subsystem)
