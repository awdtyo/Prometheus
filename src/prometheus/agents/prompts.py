"""Compact prompt builders for the four hypothesis agents.

Every prompt carries only observations, graph summaries and spec excerpts—never
raw telemetry. The builders are deterministic functions so the response cache
sees byte-identical prompts across runs.
"""

from __future__ import annotations

from datetime import datetime

from prometheus.contracts import (
    Dependency,
    GraphDocument,
    GraphEdge,
    Hypothesis,
    Observation,
    ObservationSet,
    ObservationSource,
    ProsecutorReport,
    RankedHypothesis,
    RootCauseLabel,
    SkepticReport,
)

__all__ = [
    "judge_prompt",
    "proposer_prompt",
    "prosecutor_prompt",
    "skeptic_prompt",
]

_ROOT_CAUSE_HINTS: dict[RootCauseLabel, str] = {
    RootCauseLabel.BATTERY_DEGRADATION: (
        "SOC and bus voltage fall together; the source cannot hold the bus"
    ),
    RootCauseLabel.POWER_DISTRIBUTION_FAULT: (
        "bus/current regulation is inconsistent without a source-charge deficit"
    ),
    RootCauseLabel.LOAD_SHED: "load power/current drop after a protection alarm",
    RootCauseLabel.HEATER_STUCK_ON: "heater power stays high while temperature departs",
    RootCauseLabel.THERMAL_CONTROL_FAILURE: (
        "temperature changes not explained by heater power"
    ),
    RootCauseLabel.REACTION_WHEEL_FRICTION: (
        "wheel current/temperature rise with pointing error"
    ),
    RootCauseLabel.ATTITUDE_CONTROL_FAULT: (
        "attitude error without a wheel or power anomaly"
    ),
    RootCauseLabel.TRANSMITTER_FAULT: "tx power, downlink and SNR degrade together",
    RootCauseLabel.ANTENNA_POINTING_LOSS: "downlink/SNR fall with attitude error",
    RootCauseLabel.COMMS_HARDWARE_FAULT: (
        "comms degrades without a tx-power or pointing cause"
    ),
    RootCauseLabel.SENSOR_FAULT: "one channel contradicts its physical neighbours",
    RootCauseLabel.UNKNOWN: "none of the above fits",
}


def _offset(seconds: float) -> str:
    sign = "+" if seconds >= 0 else "-"
    total = int(round(abs(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"


def _signal(observation: Observation) -> str:
    return observation.channel or "event"


def _detail(observation: Observation) -> str:
    # Telemetry provenance ("method=...") adds length without helping the
    # agents reason; event and alarm text is the useful part.
    if observation.source is not ObservationSource.EVENT or not observation.detail:
        return ""
    return observation.detail[:70].replace("\n", " ")


def observation_table(
    observations: ObservationSet,
    origin: datetime,
) -> str:
    """Render one compact line per observation."""
    lines: list[str] = []
    for observation in observations.observations:
        seconds = (observation.t_start - origin).total_seconds()
        detail = _detail(observation)
        suffix = f" | {detail}" if detail else ""
        lines.append(
            f"{observation.id} {observation.subsystem.value} {_signal(observation)} "
            f"{observation.kind.value} t={_offset(seconds)} "
            f"mag={observation.magnitude:.4g} {observation.severity.value} "
            f"conf={observation.confidence:.2f}{suffix}"
        )
    return "\n".join(lines)


def graph_table(
    graph: GraphDocument,
    *,
    limit: int = 26,
) -> str:
    """Render the strongest graph edges, plus a count of what was omitted."""
    by_id = {node.id: node for node in graph.nodes}
    edges = sorted(graph.edges, key=lambda edge: (-edge.edge_score, edge.id))[:limit]
    lines: list[str] = []
    for edge in edges:
        source = by_id[edge.source]
        target = by_id[edge.target]
        source_name = source.channel or "event"
        target_name = target.channel or "event"
        lines.append(
            f"{edge.id} {edge.source}->{edge.target} "
            f"{source_name}->{target_name} spec={'yes' if edge.spec_support else 'no'} "
            f"lag={edge.onset_lag_s:.0f}s r={edge.correlation:.2f} "
            f"p={edge.p_value:.3f} score={edge.edge_score:.2f}"
        )
    omitted = len(graph.edges) - len(edges)
    if omitted > 0:
        lines.append(f"... {omitted} weaker edges omitted")
    return "\n".join(lines)


def spec_table(dependencies: list[Dependency]) -> str:
    """Render the declared cross-subsystem couplings."""
    return "\n".join(
        f"{dependency.source.value}->{dependency.target.value} "
        f"lag={dependency.lag_min_s:.0f}-{dependency.lag_max_s:.0f}s: "
        f"{dependency.mechanism}"
        for dependency in dependencies
    )


def _taxonomy_table() -> str:
    return "\n".join(
        f"- {label.value}: {hint}" for label, hint in _ROOT_CAUSE_HINTS.items()
    )


def proposer_prompt(
    *,
    duration_s: float,
    observations: ObservationSet,
    graph: GraphDocument | None,
    dependencies: list[Dependency],
    origin: datetime,
    feedback: list[str] | None = None,
) -> str:
    """Build the Proposer's prompt.

    ``graph`` is ``None`` in the ``--no-graph`` ablation; the prompt then tells
    the model that edges are unavailable and must be empty. The simulated
    scenario name is deliberately excluded: it would reveal the injected fault
    and turn the competition into a lookup.
    """
    mode = "graph" if graph is not None else "observations-only (no graph)"
    sections = [
        "You are the Proposer in a spacecraft fault investigation.",
        f"Mission duration={duration_s:.0f}s, mode={mode}.",
        "",
        "OBSERVATIONS",
        observation_table(observations, origin),
        "",
        "SPEC DEPENDENCIES",
        spec_table(dependencies),
        "",
    ]
    if graph is not None:
        sections.extend(
            [
                "GRAPH (strongest edges; every edge ID exists)",
                graph_table(graph),
                "",
            ]
        )
    else:
        sections.extend(
            [
                "GRAPH",
                "No graph is available in this ablation. Every hypothesis must have "
                "edges=[].",
                "",
            ]
        )
    sections.extend(
        [
            "ROOT-CAUSE TAXONOMY (root_cause must be one of these values)",
            _taxonomy_table(),
            "",
            "RULES",
            "1. Propose 4 to 6 competing hypotheses with distinct root_cause labels. "
            "Cover different mechanisms (supply, distribution, control/actuator, "
            "sensor) rather than variations of one story.",
            "2. chain: 3 to 6 observation IDs, earliest first. Start with an early "
            "high-severity symptom of root_subsystem (power: bus voltage/SOC/current; "
            "thermal: heater power/temperature; comms: downlink/SNR/tx power; adcs: "
            "attitude/wheel). The first observation must belong to root_subsystem.",
            "3. edges: only IDs from GRAPH. Cite an edge for each consecutive chain "
            "pair where one exists; never cite an edge that points backward. A "
            "long-lag edge that jumps from an early symptom to a late consequence is "
            "usually indirect; prefer paths through intermediate channels. In "
            "observations-only mode edges must be [].",
            "4. Prefer sustained steps and cross-subsystem consequences; a "
            "two-observation chain is rarely enough. A brief early spike that ends "
            "may be a distractor.",
            "5. summary <=200 chars; rationale 1-2 sentences tying the chain to the "
            "evidence.",
            "6. Never invent observation IDs, edge IDs or values.",
            "",
        ]
    )
    if feedback:
        sections.append("PREVIOUS ATTEMPT REJECTED:")
        sections.extend(f"- {item}" for item in feedback)
        sections.append(
            "Return a corrected batch of 3 to 6 hypotheses that uses only the IDs above."
        )
    return "\n".join(sections)


def _hypothesis_chain(hypothesis: Hypothesis, observations: dict[str, Observation]) -> str:
    parts: list[str] = []
    for observation_id in hypothesis.chain:
        observation = observations[observation_id]
        parts.append(f"{observation_id}({_signal(observation)})")
    return " -> ".join(parts)


def _prosecutor_block(
    hypothesis: Hypothesis,
    report: ProsecutorReport,
    observations: dict[str, Observation],
    edges_by_id: dict[str, GraphEdge],
) -> str:
    edge_lines: list[str] = []
    for edge_id in report.edge_ids:
        edge = edges_by_id.get(edge_id)
        if edge is None:
            continue
        edge_lines.append(
            f"{edge_id} {edge.source}->{edge.target} "
            f"r={edge.correlation:.2f} p={edge.p_value:.3f} "
            f"score={edge.edge_score:.2f} spec={'yes' if edge.spec_support else 'no'}"
        )
    support = "; ".join(edge_lines) if edge_lines else "none"
    return (
        f"{hypothesis.id} root_cause={hypothesis.root_cause.value} "
        f"summary={hypothesis.summary}\n"
        f"  chain: {_hypothesis_chain(hypothesis, observations)}\n"
        f"  supporting observations: {', '.join(report.observation_ids) or 'none'}\n"
        f"  supporting edges: {support}\n"
        f"  deterministic mean edge score: {report.mean_edge_score:.2f}"
    )


def prosecutor_prompt(
    *,
    hypotheses: list[Hypothesis],
    reports: dict[str, ProsecutorReport],
    observations: dict[str, Observation],
    edges_by_id: dict[str, GraphEdge],
) -> str:
    """Build the Prosecutor's prompt; evidence IDs are already fixed by code."""
    blocks = [
        _prosecutor_block(
            hypothesis, reports[hypothesis.id], observations, edges_by_id
        )
        for hypothesis in hypotheses
    ]
    return "\n\n".join(
        [
            "You are the Prosecutor. For each hypothesis, write one short paragraph "
            "(at most two sentences) that articulates the supporting evidence listed.",
            "The supporting observations and edges were retrieved by deterministic "
            "code. Do not invent IDs, values or mechanisms, and do not include "
            "OBS-/EDGE- identifiers in your prose.",
            "Return exactly one item per hypothesis_id.",
            "",
            "\n\n".join(blocks),
        ]
    )


def _skeptic_block(
    hypothesis: Hypothesis,
    report: SkepticReport,
    observations: dict[str, Observation],
) -> str:
    contradictions = "\n".join(
        f"    - {item.code.value}: {item.detail}"
        for item in report.contradictions
    ) or "    - none"
    unexplained = [
        item
        for contradiction in report.contradictions
        if contradiction.code.value == "unexplained_high_severity"
        for item in contradiction.observation_ids
    ]
    return (
        f"{hypothesis.id} root_cause={hypothesis.root_cause.value} "
        f"summary={hypothesis.summary}\n"
        f"  chain: {_hypothesis_chain(hypothesis, observations)}\n"
        f"  deterministic contradictions:\n{contradictions}\n"
        f"  unexplained high-severity observations: "
        f"{', '.join(unexplained) or 'none'}\n"
        f"  code-computed contradiction penalty: {report.penalty:.2f}"
    )


def skeptic_prompt(
    *,
    hypotheses: list[Hypothesis],
    reports: dict[str, SkepticReport],
    observations: dict[str, Observation],
) -> str:
    """Build the Skeptic's prompt; the penalty is explicitly code-owned."""
    blocks = [
        _skeptic_block(hypothesis, reports[hypothesis.id], observations)
        for hypothesis in hypotheses
    ]
    return "\n\n".join(
        [
            "You are the Skeptic. Deterministic checks have already run and their "
            "contradictions and penalty are fixed.",
            "For each hypothesis, give up to two alternative explanations that could "
            "account for the unexplained observations without contradicting the data.",
            "Do not change or restate the penalty as a number, and do not invent IDs. "
            "Return exactly one item per hypothesis_id.",
            "",
            "\n\n".join(blocks),
        ]
    )


def _judge_block(
    ranked: RankedHypothesis,
    observations: dict[str, Observation],
) -> str:
    score = ranked.score
    skeptic = ranked.skeptic
    contradictions = "; ".join(
        f"{item.code.value}: {item.detail}" for item in skeptic.contradictions
    ) or "none"
    alternatives = "; ".join(skeptic.alternatives) or "none"
    return (
        f"{ranked.hypothesis.id} rank={ranked.rank} total={score.total:.3f} "
        f"margin={ranked.margin_to_next:.3f} root_cause="
        f"{ranked.hypothesis.root_cause.value}\n"
        f"  chain: {_hypothesis_chain(ranked.hypothesis, observations)}\n"
        f"  components: temporal={score.temporal_consistency:.2f} "
        f"spec={score.spec_consistency:.2f} statistical={score.statistical_support:.2f} "
        f"coverage={score.observation_coverage:.2f} penalty="
        f"{score.contradiction_penalty:.2f}\n"
        f"  prosecutor: {ranked.prosecutor.summary}\n"
        f"  skeptic contradictions: {contradictions}\n"
        f"  alternative explanations: {alternatives}"
    )


def judge_prompt(
    *,
    ranked: list[RankedHypothesis],
    observations: dict[str, Observation],
) -> str:
    """Build the Judge's prompt; every score is already fixed by code."""
    blocks = [_judge_block(item, observations) for item in ranked]
    return "\n\n".join(
        [
            "You are the Judge. Code has already computed every score, component "
            "and rank. Write one short rationale (at most two sentences) per "
            "hypothesis explaining the ranking.",
            "Use only the evidence and contradictions listed. Do not propose or alter "
            "any score, and do not include OBS-/EDGE- identifiers in your prose.",
            "Return exactly one item per hypothesis_id.",
            "",
            "\n\n".join(blocks),
        ]
    )
