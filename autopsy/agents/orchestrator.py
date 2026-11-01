from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from autopsy.agents.models import (
    AgentError,
    ProposerOutput,
    ProsecutorOutput,
    SkepticOutput,
)
from autopsy.llm.client import LLMClient
from autopsy.llm.config import ModelName
from autopsy.schemas.evidence import Evidence
from autopsy.schemas.graph import Graph
from autopsy.schemas.hypotheses import Hypothesis
from autopsy.schemas.observations import Observation
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.subsystems import SubsystemSpec


PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


@dataclass
class AgentConfig:
    max_llm_calls: int = 12
    concurrency: int = 4
    revision_round: bool = True


ProgressCb = Callable[[str, str, float], None]


def _context_for(graph, observations, events, specs) -> str:
    nodes = [f"{n.node_id}: {n.label}" for n in graph.nodes]
    obs = [f"{o.observation_id} ({o.subsystem})" for o in observations]
    evs = [f"{e.event_id} ({e.subsystem})" for e in events]
    specfacts = []
    if isinstance(specs, dict):
        for sid, s in specs.items():
            specfacts.append(f"{sid}: deps={s.dependencies}")
    else:
        for s in specs:
            specfacts.append(f"{s.id}: deps={s.dependencies}")
    return "NODES:\n" + "\n".join(nodes) + "\nOBS:\n" + "\n".join(obs) + "\nEVENTS:\n" + "\n".join(evs) + "\nSPECS:\n" + "\n".join(specfacts)


def _validate_ids(obj, valid_ids: set[str]):
    # validate hypothesis causal_chain and evidence source_ids
    if isinstance(obj, Hypothesis):
        for nid in obj.causal_chain:
            if nid not in valid_ids:
                raise ValueError(f"unknown id {nid}")
    if isinstance(obj, Evidence):
        if obj.source_id not in valid_ids:
            raise ValueError(f"unknown source_id {obj.source_id}")


def generate_hypotheses(graph, observations, events, specs, llm, config=None, progress=None) -> tuple[list[Hypothesis], list[Evidence]]:
    cfg = config or AgentConfig()
    progress = progress or (lambda s, m, f: None)
    client = llm if isinstance(llm, LLMClient) else LLMClient() if False else None
    # llm may be LLMClient or have complete_json
    if not hasattr(llm, "complete_json"):
        client = LLMClient()
    else:
        client = llm

    valid_ids = set(n.node_id for n in graph.nodes) | set(o.observation_id for o in observations) | set(e.event_id for e in events)

    ctx = _context_for(graph, observations, events, specs)
    calls = {"n": 0}

    def call(model, system, user, rmodel, max_tokens=1024):
        if calls["n"] >= cfg.max_llm_calls:
            raise AgentError("budget exceeded")
        calls["n"] += 1
        return client.complete_json(model=model, system=system, user=user, response_model=rmodel, max_tokens=max_tokens)

    # Proposer
    progress("proposing", "Proposing hypotheses", 0.1)
    proposer_prompt = _load_prompt("proposer.md")
    proposer_out = call(ModelName.REASONING, proposer_prompt, ctx, ProposerOutput)
    hyps = proposer_out.hypotheses

    all_evidence: list[Evidence] = []

    # Prosecutor + Skeptic per hypothesis in parallel with bounded concurrency
    sem = asyncio.Semaphore(cfg.concurrency)

    async def process_one(h: Hypothesis):
        nonlocal all_evidence
        async with sem:
            # prosecutor
            progress("prosecuting", f"Prosecuting {h.hypothesis_id}", 0.3)
            pros_prompt = _load_prompt("prosecutor.md")
            pros_user = ctx + "\nHYPOTHESIS:\n" + h.model_dump_json()
            try:
                pros_out = call(ModelName.FAST, pros_prompt, pros_user, ProsecutorOutput)
            except Exception as e:
                raise AgentError(f"prosecutor failed: {e}") from e
            for ev in pros_out.evidence:
                _validate_ids(ev, valid_ids)
            # skeptic
            progress("skepticking", f"Skepticking {h.hypothesis_id}", 0.5)
            skep_prompt = _load_prompt("skeptic.md")
            skep_user = ctx + "\nHYPOTHESIS:\n" + h.model_dump_json()
            try:
                skep_out = call(ModelName.ALT, skep_prompt, skep_user, SkepticOutput)
            except Exception as e:
                raise AgentError(f"skeptic failed: {e}") from e
            for ev in skep_out.evidence:
                _validate_ids(ev, valid_ids)
                ev.supports_or_contradicts = ev.supports_or_contradicts  # keep
            all_evidence.extend(pros_out.evidence)
            all_evidence.extend(skep_out.evidence)
            h.evidence_ids = [e.evidence_id for e in pros_out.evidence]
            h.contradiction_ids = [e.evidence_id for e in skep_out.evidence]

    async def run_all():
        await asyncio.gather(*[process_one(h) for h in hyps])

    asyncio.run(run_all())

    progress("done", "Complete", 1.0)
    return hyps, all_evidence
