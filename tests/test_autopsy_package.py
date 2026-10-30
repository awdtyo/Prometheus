"""Smoke tests for the core package surface."""

import re

import autopsy
from autopsy import agents, analysis, graph, ingest, models, simulation


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", autopsy.__version__)


def test_core_subpackages_import() -> None:
    subpackages = (models, ingest, graph, simulation, agents, analysis)

    assert all(module.__name__.startswith("autopsy.") for module in subpackages)
