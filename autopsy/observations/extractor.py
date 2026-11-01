"""Observation extraction: telemetry + events + subsystem specs -> list[Observation]."""

from __future__ import annotations
from typing import cast

import math
import statistics
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence

from autopsy.schemas.events import MissionEvent
from autopsy.schemas.inputs import InvestigationInputs
from autopsy.schemas.observations import Observation
from autopsy.schemas.enums import Severity
from autopsy.schemas.subsystems import ParameterSpec, SubsystemSpec
from autopsy.schemas.telemetry import TelemetryRecord
from autopsy.schemas.base import UtcDatetime


@dataclass(frozen=True)
class ObservationConfig:
    """Thresholds and parameters for all detectors."""

    baseline_window: int = 10
    k_sigma: float = 4.0
    sustained_n: int = 3
    cusum_threshold: float = 8.0
    cusum_slack: float = 1.0
    merge_window_seconds: float = 300.0
    # Severity ordering: critical > high > medium > low > info
    severity_rank: dict[str, int] = field(
        default_factory=lambda: {
            "info": 0,
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4,
        }
    )


def _severity_max(a: str, b: str, rank: dict[str, int]) -> str:
    return a if rank.get(a, 0) >= rank.get(b, 0) else b


def _param_spec(subsystem: SubsystemSpec, param: str) -> ParameterSpec | None:
    for p in subsystem.monitored_parameters:
        if p.name == param:
            return p
    return None


def _baseline_value(spec: ParameterSpec | None, values: list[float]) -> float:
    if spec is not None:
        return (spec.nominal_min + spec.nominal_max) / 2.0
    if len(values) >= 1:
        window = values[: min(len(values), 10)]
        return statistics.median(window)
    return 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    try:
        return statistics.stdev(values) or 1.0
    except statistics.StatisticsError:
        return 1.0


def _make_obs(
    obs_id: str,
    ts: UtcDatetime,
    subsystem: str,
    obs_type: str,
    description: str,
    value: float,
    threshold: float | None,
    severity: str,
    source_ids: list[str],
) -> Observation:
    return Observation(
        observation_id=obs_id,
        timestamp=ts,
        subsystem=subsystem,
        observation_type=obs_type,
        description=description,
        observed_value=value,
        threshold=threshold,
        severity=Severity(severity),
        source_ids=source_ids,
    )


def _threshold_violations(
    records: list[TelemetryRecord],
    spec: ParameterSpec | None,
    baseline: float,
    std: float,
    cfg: ObservationConfig,
) -> list[tuple[TelemetryRecord, str, float | None, str]]:
    """Returns one detection per contiguous run of threshold violations."""
    out: list[tuple[TelemetryRecord, str, float | None, str]] = []
    if spec is None:
        return out
    run: list[tuple[TelemetryRecord, str, float | None, str]] = []
    for r in records:
        sev = None
        thr = None
        if spec.critical_low is not None and r.value < spec.critical_low:
            sev = "critical"
            thr = spec.critical_low
        elif spec.warning_low is not None and r.value < spec.warning_low:
            sev = "high"
            thr = spec.warning_low
        elif spec.critical_high is not None and r.value > spec.critical_high:
            sev = "critical"
            thr = spec.critical_high
        elif spec.warning_high is not None and r.value > spec.warning_high:
            sev = "high"
            thr = spec.warning_high
        if sev is not None and thr is not None:
            run.append((r, "threshold_breach", thr, sev))
        else:
            if run:
                # emit at onset (first sample of run), escalate severity
                sev_max = run[0][3]
                for x in run:
                    sev_max = _severity_max(sev_max, x[3], cfg.severity_rank)
                out.append((run[0][0], "threshold_breach", run[0][2], sev_max))
                run = []
    if run:
        sev_max = run[0][3]
        for x in run:
            sev_max = _severity_max(sev_max, x[3], cfg.severity_rank)
        out.append((run[0][0], "threshold_breach", run[0][2], sev_max))
    return out


def _sustained_deviations(
    records: list[TelemetryRecord],
    baseline: float,
    std: float,
    cfg: ObservationConfig,
) -> list[tuple[TelemetryRecord, str, float | None, str]]:
    """Detect sustained k*sigma deviations (step/drop/spike). One per run."""
    out: list[tuple[TelemetryRecord, str, float | None, str]] = []
    if std <= 0:
        std = 1.0
    threshold = cfg.k_sigma * std
    run_records: list[TelemetryRecord] = []
    for r in records:
        dev = r.value - baseline
        if abs(dev) >= threshold:
            run_records.append(r)
        else:
            if len(run_records) >= cfg.sustained_n:
                direction = "drop" if (run_records[0].value - baseline) < 0 else "spike"
                sev = "high" if len(run_records) >= cfg.sustained_n * 2 else "medium"
                out.append((run_records[0], f"sustained_{direction}", None, sev))
            run_records = []
    if len(run_records) >= cfg.sustained_n:
        direction = "drop" if (run_records[0].value - baseline) < 0 else "spike"
        sev = "high" if len(run_records) >= cfg.sustained_n * 2 else "medium"
        out.append((run_records[0], f"sustained_{direction}", None, sev))
    return out


def _cusum_drift(
    records: list[TelemetryRecord],
    baseline: float,
    std: float,
    cfg: ObservationConfig,
) -> list[tuple[TelemetryRecord, str, float | None, str]]:
    """Detect drift via CUSUM. At most one crossing per series."""
    out: list[tuple[TelemetryRecord, str, float | None, str]] = []
    if std <= 0:
        std = 1.0
    threshold = cfg.cusum_threshold * std
    s_pos = 0.0
    s_neg = 0.0
    crossed = False
    for r in records:
        z = (r.value - baseline) / std
        s_pos = max(0.0, s_pos + z - cfg.cusum_slack)
        s_neg = max(0.0, s_neg - z - cfg.cusum_slack)
        if not crossed and (s_pos > threshold or s_neg > threshold):
            out.append((r, "drift", None, "medium"))
            crossed = True
            s_pos = 0.0
            s_neg = 0.0
    return out


def _event_observations(events: list[MissionEvent], cfg: ObservationConfig) -> list[Observation]:
    """Convert significant MissionEvents into observations."""
    out: list[Observation] = []
    significant_types = {"warning", "mode_change", "fault", "anomaly", "alert", "safe_mode", "degradation"}
    significant_severities = {"medium", "high", "critical"}
    for ev in events:
        is_sig = (
            ev.severity.value in significant_severities
            or ev.event_type in significant_types
            or any(kw in ev.event_type.lower() for kw in ("warning", "mode", "fault", "anomaly", "safe", "degrad"))
        )
        if not is_sig:
            continue
        obs_id = f"obs_evt_{ev.event_id}"
        sev = ev.severity.value
        if sev not in cfg.severity_rank:
            sev = "medium"
        try:
            obs = _make_obs(
                obs_id=obs_id,
                ts=ev.timestamp,
                subsystem=ev.subsystem,
                obs_type=f"event_{ev.event_type}",
                description=ev.description,
                value=0.0,
                threshold=None,
                severity=sev,
                source_ids=[ev.event_id],
            )
            out.append(obs)
        except Exception:
            continue
    return out


def extract_observations(
    inputs: InvestigationInputs,
    config: ObservationConfig | None = None,
) -> list[Observation]:
    cfg = config or ObservationConfig()

    # Group telemetry by (subsystem, parameter)
    groups: dict[tuple[str, str], list[TelemetryRecord]] = {}
    for r in inputs.telemetry:
        groups.setdefault((r.subsystem, r.parameter), []).append(r)

    subsystem_map = {s.id: s for s in inputs.subsystems}

    all_detections: list[tuple[TelemetryRecord, str, float | None, str, str]] = []
    # tuple: (record, obs_type, threshold, severity, param_key)

    for (subsystem_id, param), records in groups.items():
        records = sorted(records, key=lambda r: r.timestamp)
        if not records:
            continue
        spec = subsystem_map.get(subsystem_id)
        param_spec = _param_spec(spec, param) if spec else None

        values = [r.value for r in records]
        baseline = _baseline_value(param_spec, values)
        # std from initial stable window
        std = _std(values)

        # 1. threshold violations
        for r, obs_type, thr, sev in _threshold_violations(records, param_spec, baseline, std, cfg):
            src = r.source_id if r.source_id else f"{subsystem_id}:{param}"
            all_detections.append((r, obs_type, thr, sev, f"{subsystem_id}:{param}"))

        # 2. sustained deviations
        for r, obs_type, thr, sev in _sustained_deviations(records, baseline, std, cfg):
            src = r.source_id if r.source_id else f"{subsystem_id}:{param}"
            all_detections.append((r, obs_type, thr, sev, f"{subsystem_id}:{param}"))

        # 3. drift
        for r, obs_type, thr, sev in _cusum_drift(records, baseline, std, cfg):
            src = r.source_id if r.source_id else f"{subsystem_id}:{param}"
            all_detections.append((r, obs_type, thr, sev, f"{subsystem_id}:{param}"))

    # Merge
    # We need to track source_id per detection; rebuild with source
    # Build a richer structure: (record, obs_type, threshold, severity, key, source_id)
    enriched: list[tuple[TelemetryRecord, str, float | None, str, str, str]] = []
    for det in all_detections:
        r, obs_type, thr, sev, key = det
        src = r.source_id if r.source_id else f"{r.subsystem}:{r.parameter}"
        enriched.append((r, obs_type, thr, sev, key, src))

    # Build one Observation per detection first.
    observations: list[Observation] = []
    counters: dict[str, int] = {}
    for r, obs_type, thr, sev, key, src in enriched:
        counters[key] = counters.get(key, 0) + 1
        obs_id = f"obs_{r.subsystem}_{r.parameter}_{counters[key]}".replace(":", "_").replace("-", "_")
        try:
            obs = _make_obs(
                obs_id=obs_id,
                ts=r.timestamp,
                subsystem=r.subsystem,
                obs_type=obs_type,
                description=f"{obs_type} on {r.subsystem}.{r.parameter}: value={r.value}",
                value=r.value,
                threshold=thr,
                severity=sev,
                source_ids=[src],
            )
            observations.append(obs)
        except Exception:
            continue

    # Merge nearby observations of same (subsystem, parameter, obs_type) within window.
    if observations:
        observations.sort(key=lambda o: o.timestamp)
        merged: list[Observation] = [observations[0]]
        for obs in observations[1:]:
            last = merged[-1]
            same = (
                last.subsystem == obs.subsystem
                and last.observation_type == obs.observation_type
            )
            # check same parameter via description prefix (obs_type + subsystem + param)
            time_close = (obs.timestamp - last.timestamp).total_seconds() <= cfg.merge_window_seconds
            if same and time_close:
                sev = _severity_max(last.severity.value, obs.severity.value, cfg.severity_rank)
                merged[-1] = last.model_copy(update={"severity": Severity(sev)})
            else:
                merged.append(obs)
        observations = merged

    # Event-based observations
    observations.extend(_event_observations(inputs.events, cfg))

    # Deduplicate observation_ids
    seen_ids: set[str] = set()
    unique: list[Observation] = []
    for obs in observations:
        if obs.observation_id in seen_ids:
            # append suffix
            i = 2
            new_id = f"{obs.observation_id}_{i}"
            while new_id in seen_ids:
                i += 1
                new_id = f"{obs.observation_id}_{i}"
            # rebuild
            obs = obs.model_copy(update={"observation_id": new_id})
            seen_ids.add(new_id)
        else:
            seen_ids.add(obs.observation_id)
        unique.append(obs)

    return unique
