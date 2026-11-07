# Prometheus — Mission Autopsy

Reconstructs why a spacecraft mission failed: telemetry, event logs, subsystem
specifications and an injected fault go in; a ranked, evidence-tagged causal
explanation comes out.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then set GROQ_API_KEY and the model names
pytest -q
```

Smoke-test the LLM wiring and inspect the CLI:

```bash
prometheus --help
prometheus llm-ping
ruff check .
```

> `.env`, `AGENTS.md` and `PROGRESS.md` are gitignored. Never commit the key.

## Pipeline

Stages run in this order and are never reordered or merged:

1. ingest and normalize
2. observation extraction
3. temporal causal graph
4. hypothesis agents — Proposer → Prosecutor → Skeptic → Judge
5. evidence-tagged report

An evaluation harness sits alongside and is the only code allowed to read
ground truth. Every claim is labeled **EVIDENCE** (cites observation IDs),
**INFERENCE** (names the graph edges used) or **SPECULATION** (unsupported).

Subsystems: `power`, `thermal`, `comms`, `adcs`.
