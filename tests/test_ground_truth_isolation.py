"""Enforce ground-truth isolation and the fixed subsystem contract."""

from __future__ import annotations

from pathlib import Path

from prometheus.contracts import SUBSYSTEMS, Subsystem

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "prometheus"


def _pipeline_modules() -> list[Path]:
    """Every module outside ``prometheus/eval/``."""
    return [
        path
        for path in PACKAGE_ROOT.rglob("*.py")
        if "eval" not in path.relative_to(PACKAGE_ROOT).parts
    ]


def test_only_eval_may_reference_ground_truth() -> None:
    offenders = [
        str(path.relative_to(PACKAGE_ROOT))
        for path in _pipeline_modules()
        if "ground_truth" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], f"ground truth referenced outside eval/: {offenders}"


def test_only_eval_may_import_eval_package() -> None:
    offenders = [
        str(path.relative_to(PACKAGE_ROOT))
        for path in _pipeline_modules()
        if "prometheus.eval" in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], f"eval package imported outside eval/: {offenders}"


def test_subsystems_are_exactly_four() -> None:
    assert [member.value for member in SUBSYSTEMS] == ["power", "thermal", "comms", "adcs"]
    assert SUBSYSTEMS == tuple(Subsystem)
