"""Render a graph document as a self-contained static HTML page.

The visualization is inline SVG: no server, no JavaScript and no network
resources. Time runs left to right and subsystems occupy fixed lanes, so the
temporal ordering rule is visible at a glance.
"""

from __future__ import annotations

import html
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from prometheus.contracts import SUBSYSTEMS, GraphDocument, Observation

__all__ = ["render_html"]

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_WIDTH = 1160
_LEFT = 132
_RIGHT = 28
_TOP = 54
_LANE_HEIGHT = 96
_RADIUS = 7

_COLORS = {
    "power": "#2563eb",
    "thermal": "#dc2626",
    "comms": "#059669",
    "adcs": "#7c3aed",
}


def _offset(seconds: float) -> str:
    sign = "+" if seconds >= 0 else "-"
    total = int(round(abs(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"


def _x_positions(document: GraphDocument) -> dict[str, float]:
    starts = [node.t_start.timestamp() for node in document.nodes]
    if not starts:
        return {}
    first, last = min(starts), max(starts)
    span = last - first
    positions: dict[str, float] = {}
    for node in document.nodes:
        fraction = 0.5 if span <= 0 else (node.t_start.timestamp() - first) / span
        positions[node.id] = _LEFT + fraction * (_WIDTH - _LEFT - _RIGHT)
    return positions


def _lane_positions(document: GraphDocument) -> dict[str, float]:
    by_subsystem: dict[str, list[Observation]] = {
        subsystem.value: [] for subsystem in SUBSYSTEMS
    }
    for node in document.nodes:
        by_subsystem[node.subsystem.value].append(node)

    positions: dict[str, float] = {}
    for lane_index, subsystem in enumerate(SUBSYSTEMS):
        lane_center = _TOP + lane_index * _LANE_HEIGHT
        members = sorted(
            by_subsystem[subsystem.value],
            key=lambda node: (node.t_start, node.id),
        )
        spacing = 20.0 if len(members) <= 1 else min(20.0, 64.0 / (len(members) - 1))
        for rank, node in enumerate(members):
            positions[node.id] = lane_center + (rank - (len(members) - 1) / 2) * spacing
    return positions


def _node_label(node: Observation) -> str:
    if node.channel is not None:
        return node.channel.split(".", 1)[1]
    return f"event {node.id}"


def _tooltip(node: Observation, first_epoch: float) -> str:
    offset = _offset(node.t_start.timestamp() - first_epoch)
    channel = node.channel or "event log"
    return (
        f"{node.id} · {channel} · {node.kind.value} · {offset}\n"
        f"magnitude {node.magnitude:.4g} · {node.severity.value} · "
        f"confidence {node.confidence:.2f}"
    )


def _edge_tooltip(edge, by_id: dict[str, Observation]) -> str:
    return (
        f"{edge.id} · {by_id[edge.source].channel or edge.source} → "
        f"{by_id[edge.target].channel or edge.target}\n"
        f"spec={edge.spec_support} · onset lag {edge.onset_lag_s:.0f} s · "
        f"xcorr {edge.xcorr_lag_s if edge.xcorr_lag_s is not None else 'n/a'} s · "
        f"r={edge.correlation:.2f} · p={edge.p_value:.3f} · "
        f"score={edge.edge_score:.2f}"
    )


def _label_anchor(x: float) -> str:
    """Anchor labels on the inner side so nothing is clipped at the right edge."""
    return "end" if x > _WIDTH - _RIGHT - 120 else "start"


def _label_x(x: float) -> float:
    """Label offset matching :func:`_label_anchor`."""
    return x - 10 if _label_anchor(x) == "end" else x + 10


def _svg(document: GraphDocument) -> str:
    if not document.nodes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="80"></svg>'

    first_epoch = min(node.t_start.timestamp() for node in document.nodes)
    xs = _x_positions(document)
    ys = _lane_positions(document)
    height = _TOP + (len(SUBSYSTEMS) - 1) * _LANE_HEIGHT + 64
    by_id = {node.id: node for node in document.nodes}

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_WIDTH}" height="{height}" '
        f'viewBox="0 0 {_WIDTH} {height}" role="img" aria-label="Temporal causal graph">',
        "<defs>",
        '<marker id="arrow-spec" markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,4.5 L0,9 z" fill="#2f6fdd"/></marker>',
        '<marker id="arrow-data" markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
        'orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L9,4.5 L0,9 z" fill="#d97706"/></marker>',
        "</defs>",
        f'<rect x="0" y="0" width="{_WIDTH}" height="{height}" fill="#ffffff"/>',
    ]

    for lane_index, subsystem in enumerate(SUBSYSTEMS):
        lane_y = _TOP + lane_index * _LANE_HEIGHT
        parts.append(
            f'<line x1="{_LEFT - 14}" y1="{lane_y}" x2="{_WIDTH - _RIGHT}" '
            f'y2="{lane_y}" stroke="#e6ebf2" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="16" y="{lane_y + 4}" font-size="12" font-weight="600" '
            f'fill="{_COLORS[subsystem.value]}">{subsystem.value}</text>'
        )

    for edge in document.edges:
        source = by_id.get(edge.source)
        target = by_id.get(edge.target)
        if source is None or target is None:
            continue
        x1, y1 = xs[edge.source], ys[edge.source]
        x2, y2 = xs[edge.target], ys[edge.target]
        same_lane = abs(y1 - y2) < 1.0
        curve = 18.0 if same_lane else 8.0
        mx = (x1 + x2) / 2.0
        my = (y1 + y2) / 2.0 - curve
        spec = edge.spec_support
        color = "#2f6fdd" if spec else "#d97706"
        dash = "" if spec else ' stroke-dasharray="7 5"'
        width = 1.0 + 2.2 * edge.edge_score
        opacity = 0.32 + 0.58 * edge.edge_score
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} Q {mx:.1f} {my:.1f} {x2:.1f} {y2:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{width:.2f}" '
            f'opacity="{opacity:.2f}"{dash} marker-end="url(#arrow-{"spec" if spec else "data"})">'
            f"<title>{html.escape(_edge_tooltip(edge, by_id))}</title></path>"
        )

    for node in document.nodes:
        x, y = xs[node.id], ys[node.id]
        color = _COLORS[node.subsystem.value]
        if node.channel is None:
            size = _RADIUS + 1
            parts.append(
                f'<polygon points="{x:.1f},{y - size:.1f} {x + size:.1f},{y:.1f} '
                f'{x:.1f},{y + size:.1f} {x - size:.1f},{y:.1f}" fill="#ffffff" '
                f'stroke="{color}" stroke-width="1.6">'
                f"<title>{html.escape(_tooltip(node, first_epoch))}</title></polygon>"
            )
        else:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{_RADIUS}" fill="{color}" '
                f'stroke="#ffffff" stroke-width="1.4">'
                f"<title>{html.escape(_tooltip(node, first_epoch))}</title></circle>"
            )
        parts.append(
            f'<text x="{_label_x(x):.1f}" y="{y + 4:.1f}" font-size="10" '
            f'text-anchor="{_label_anchor(x)}" fill="#3d4759">'
            f"{html.escape(_node_label(node))}</text>"
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _rows(document: GraphDocument) -> list[dict[str, str]]:
    by_id = {node.id: node for node in document.nodes}

    def label(node_id: str) -> str:
        node = by_id[node_id]
        name = node.channel or "event"
        return f"{name} ({node_id})"

    rows: list[dict[str, str]] = []
    for edge in sorted(document.edges, key=lambda item: (-item.edge_score, item.id)):
        rows.append(
            {
                "id": edge.id,
                "source_label": label(edge.source),
                "target_label": label(edge.target),
                "spec": "yes" if edge.spec_support else "no",
                "onset_lag": f"{edge.onset_lag_s:.0f}",
                "xcorr_lag": (
                    f"{edge.xcorr_lag_s:.0f}" if edge.xcorr_lag_s is not None else "n/a"
                ),
                "correlation": f"{edge.correlation:.2f}",
                "p_value": f"{edge.p_value:.3f}",
                "support": f"{edge.statistical_support:.2f}",
                "score": f"{edge.edge_score:.2f}",
            }
        )
    return rows


def render_html(
    document: GraphDocument,
    path: str | Path,
    *,
    grid_s: float = 60.0,
) -> Path:
    """Write a self-contained HTML visualization and return its path."""
    environment = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template("graph.html.j2")
    spec_count = sum(edge.spec_support for edge in document.edges)
    payload = template.render(
        title=f"Prometheus graph · {document.scenario}",
        scenario=document.scenario,
        mission=document.mission,
        seed=document.seed,
        grid_s=f"{grid_s:g}",
        node_count=len(document.nodes),
        edge_count=len(document.edges),
        spec_count=spec_count,
        data_count=len(document.edges) - spec_count,
        svg=_svg(document),
        rows=_rows(document),
    )
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload + "\n", encoding="utf-8")
    return target
