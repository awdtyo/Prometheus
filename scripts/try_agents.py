import os
from pathlib import Path
from autopsy.ingest.loaders import load_scenario, load_subsystem_specs
from autopsy.observations.extractor import extract_observations
from autopsy.graph.builder import build_graph
from autopsy.agents.orchestrator import generate_hypotheses, AgentConfig
from autopsy.llm.client import LLMClient

scenario = load_scenario("battery_failure")
specs = load_subsystem_specs("configs/subsystems")
obs = extract_observations(scenario.telemetry, scenario.events)
graph = build_graph(obs, scenario.events, scenario.telemetry, specs)
llm = LLMClient()
hyps, evs = generate_hypotheses(graph, obs, scenario.events, specs, llm, config=AgentConfig())
out = Path("data/debug")
out.mkdir(parents=True, exist_ok=True)
(out / "hypotheses.json").write_text("\n".join(h.model_dump_json() for h in hyps))
(out / "evidence.json").write_text("\n".join(e.model_dump_json() for e in evs))
print("done", len(hyps), len(evs))
