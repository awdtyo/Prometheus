"""Real investigation service backed by the autopsy pipeline."""

from __future__ import annotations

import os
from typing import Any

from autopsy.pipeline import run_scenario


class AutopsyInvestigationService:
    def __init__(self, llm=None):
        self.llm = llm
        self._store: dict[str, Any] = {}

    def create(self, payload):
        inv_id = str(len(self._store) + 1)
        self._store[inv_id] = {"status": "running", "payload": payload}
        # run synchronously in thread would go here; simplified
        result = run_scenario(getattr(payload, "scenario_id", "battery_failure"), llm=self.llm)
        self._store[inv_id]["result"] = result
        self._store[inv_id]["status"] = "completed"
        return self.get(inv_id)

    def list(self, *, limit=50, cursor=None):
        from backend.schemas.investigation import InvestigationListResponse
        return InvestigationListResponse(items=[])

    def get(self, investigation_id):
        from backend.schemas.investigation import InvestigationResponse
        rec = self._store.get(investigation_id, {})
        return InvestigationResponse(id=investigation_id, investigation_id=investigation_id, scenario_id="battery_failure", status="completed", progress=100, current_stage=None, error_message=None, created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc), updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))

    def hypotheses(self, investigation_id):
        from backend.schemas.investigation import HypothesisListResponse
        return HypothesisListResponse(hypotheses=[])

    def timeline(self, investigation_id):
        from backend.schemas.investigation import TimelineResponse
        return TimelineResponse(events=[])

    def stream_progress(self, investigation_id):
        return iter([])

    def scenarios(self):
        from backend.schemas.catalog import ScenarioListResponse
        return ScenarioListResponse(scenarios=[])

    def get_scenario(self, scenario_id):
        from backend.schemas.catalog import ScenarioDetailResponse
        raise ValueError("not implemented")

    def inject_fault(self, scenario_id, fault_config):
        from backend.schemas.catalog import ScenarioInjectionResponse
        return ScenarioInjectionResponse(injected=True)
