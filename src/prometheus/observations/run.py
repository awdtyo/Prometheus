"""Orchestrate observation extraction for one mission.

The pipeline stage is intentionally a pure function of the ingested run:

1. run the telemetry detectors on every channel;
2. suppress transient detections that a level change explains;
3. merge duplicate and near-simultaneous detections;
4. convert command/alarm rows into event observations;
5. assign stable ``OBS-0001`` identifiers after a deterministic sort.

Only the mission directory is read. Ground truth is never opened.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from prometheus.contracts import (
    Observation,
    ObservationKind,
    ObservationSet,
    ObservationSource,
    Severity,
    Subsystem,
)
from prometheus.ingest import IngestedRun, NormalizedEvent, ingest_run
from prometheus.observations.detect import Detection, DetectorConfig, detect_channel
from prometheus.observations.merge import (
    filter_transition_fallbacks,
    merge_detections,
    suppress_overlaps,
)

__all__ = [
    "ObservationResult",
    "extract_observations",
    "observe_run",
    "write_observations",
]

_DEFAULT_FILENAME = "observations.json"


@dataclass(frozen=True)
class ObservationResult:
    """An ingested run, its observations and where they were written."""

    ingested: IngestedRun
    observations: ObservationSet
    output_path: Path | None

    @property
    def telemetry_count(self) -> int:
        """Number of telemetry observations."""
        return sum(
            observation.source is ObservationSource.TELEMETRY
            for observation in self.observations.observations
        )

    @property
    def event_count(self) -> int:
        """Number of event observations."""
        return sum(
            observation.source is ObservationSource.EVENT
            for observation in self.observations.observations
        )

    def counts_by_kind(self) -> dict[str, int]:
        """Observation counts keyed by kind, in contract order."""
        counter = Counter(observation.kind.value for observation in self.observations.observations)
        return {kind.value: counter.get(kind.value, 0) for kind in ObservationKind}

    def counts_by_source(self) -> dict[str, int]:
        """Observation counts keyed by source."""
        counter = Counter(
            observation.source.value for observation in self.observations.observations
        )
        return {source.value: counter.get(source.value, 0) for source in ObservationSource}


@dataclass(frozen=True)
class _Draft:
    """An observation before its stable identifier is assigned."""

    subsystem: Subsystem
    channel: str | None
    t_start: datetime
    t_end: datetime
    kind: ObservationKind
    magnitude: float
    severity: Severity
    confidence: float
    source: ObservationSource
    detail: str = ""


def _draft_from_detection(detection: Detection) -> _Draft:
    return _Draft(
        subsystem=detection.subsystem,
        channel=detection.channel,
        t_start=detection.t_start,
        t_end=detection.t_end,
        kind=detection.kind,
        magnitude=float(detection.magnitude),
        severity=detection.severity,
        confidence=float(detection.confidence),
        source=ObservationSource.TELEMETRY,
        detail=f"method={detection.method}",
    )


def _draft_from_event(event: NormalizedEvent) -> _Draft:
    return _Draft(
        subsystem=event.subsystem,
        channel=None,
        t_start=event.timestamp,
        t_end=event.timestamp,
        kind=ObservationKind.EVENT,
        magnitude=0.0,
        severity=Severity(event.severity),
        confidence=1.0,
        source=ObservationSource.EVENT,
        detail=f"{event.event_id} {event.kind} {event.code}: {event.message}",
    )


def _deduplicate_events(events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    """Drop byte-identical log rows, keeping the first occurrence."""
    seen: set[tuple[datetime, Subsystem, str, str]] = set()
    unique: list[NormalizedEvent] = []
    for event in events:
        key = (event.timestamp, event.subsystem, event.code, event.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def _sort_key(draft: _Draft) -> tuple:
    return (
        draft.t_start,
        draft.source.value,
        draft.channel or "",
        draft.kind.value,
        round(draft.magnitude, 9),
        draft.t_end,
        draft.detail,
    )


def _assign_ids(drafts: list[_Draft]) -> list[Observation]:
    """Sort drafts deterministically and assign ``OBS-0001`` identifiers."""
    observations: list[Observation] = []
    for number, draft in enumerate(sorted(drafts, key=_sort_key), start=1):
        observations.append(
            Observation(
                id=f"OBS-{number:04d}",
                subsystem=draft.subsystem,
                channel=draft.channel,
                t_start=draft.t_start,
                t_end=draft.t_end,
                kind=draft.kind,
                magnitude=draft.magnitude,
                severity=draft.severity,
                confidence=draft.confidence,
                source=draft.source,
                detail=draft.detail,
            )
        )
    return observations


def extract_observations(
    ingested: IngestedRun,
    config: DetectorConfig | None = None,
) -> ObservationSet:
    """Extract discrete observations from one ingested mission.

    Args:
        ingested: Output of :func:`prometheus.ingest.ingest_run`.
        config: Optional detector thresholds. Defaults are documented in
            :class:`prometheus.observations.detect.DetectorConfig`.

    Returns:
        A validated :class:`ObservationSet` with stable identifiers.
    """
    config = config or DetectorConfig()
    drafts: list[_Draft] = []

    for name in sorted(ingested.series):
        series = ingested.series[name]
        detections = detect_channel(series, config)
        detections = filter_transition_fallbacks(detections)
        detections = suppress_overlaps(detections)
        detections = merge_detections(detections)
        drafts.extend(_draft_from_detection(detection) for detection in detections)

    drafts.extend(
        _draft_from_event(event) for event in _deduplicate_events(ingested.events)
    )

    return ObservationSet(
        scenario=ingested.spec.scenario,
        seed=ingested.spec.seed,
        mission=ingested.spec.mission,
        observations=_assign_ids(drafts),
    )


def write_observations(observation_set: ObservationSet, path: str | Path) -> Path:
    """Write an :class:`ObservationSet` as deterministic JSON."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = observation_set.model_dump(mode="json")
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def observe_run(
    run_dir: str | Path,
    *,
    out_path: str | Path | None = None,
    config: DetectorConfig | None = None,
) -> ObservationResult:
    """Ingest, extract and write observations for one mission directory."""
    ingested = ingest_run(run_dir)
    observation_set = extract_observations(ingested, config)
    target = (
        Path(out_path).expanduser()
        if out_path is not None
        else ingested.run_dir / _DEFAULT_FILENAME
    )
    written = write_observations(observation_set, target)
    return ObservationResult(
        ingested=ingested,
        observations=observation_set,
        output_path=written,
    )
