from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from autopsy.schemas.inputs import InvestigationInputs


def _seeded(seed: int):
    random.seed(seed)
    np.random.seed(seed)


def generate_scenario(scenario_id: str, seed: int = 20260314, out_dir: str = "fixtures") -> dict[str, str]:
    _seeded(seed)
    # Minimal: copy battery_failure style? We'll generate a simple telemetry CSV + events JSON
    base = datetime(2026, 3, 14, 8, 0, tzinfo=timezone.utc)
    interval = 60
    n = 60
    subs = ["eps", "tcs", "adcs", "comms", "obc"]
    params = {"eps": ["bus_voltage", "battery_soc"], "tcs": ["battery_temp"], "adcs": ["pointing_error"], "comms": ["link_margin"], "obc": ["cpu_load"]}
    rows = []
    for i in range(n):
        ts = base + timedelta(seconds=i * interval)
        for s in subs:
            for p in params[s]:
                val = 100.0 + random.gauss(0, 1)
                # fault onset at i=10 for eps
                if s == "eps" and p == "bus_voltage" and i >= 10:
                    val -= 2.0 * (i - 10) * 0.1
                rows.append([ts.isoformat(), s, p, round(val, 3), "V" if "voltage" in p else "x", f"{s}_{p}"])
    tel_path = Path(out_dir) / "telemetry" / f"{scenario_id}.csv"
    tel_path.parent.mkdir(parents=True, exist_ok=True)
    with tel_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "subsystem", "parameter", "value", "unit", "source_id"])
        w.writerows(rows)
    events = [{"timestamp": (base + timedelta(seconds=10 * interval)).isoformat(), "subsystem": "eps", "event_type": "battery_cell_imbalance", "description": "imbalance", "severity": "medium"}]
    ev_path = Path(out_dir) / "events" / f"{scenario_id}.json"
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(events, indent=2))
    return {"telemetry": str(tel_path), "events": str(ev_path)}
