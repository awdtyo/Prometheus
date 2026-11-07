"""Command-line interface.

Phase 0 exposes ``llm-ping``; Phase 1 adds ``sim generate``. Later phases add
pipeline commands here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from pydantic import BaseModel, Field

from prometheus import __version__
from prometheus.config import ConfigError, get_settings
from prometheus.contracts import SUBSYSTEMS
from prometheus.ingest import IngestError, ingest_run
from prometheus.llm.client import LLMClient, LLMError
from prometheus.sim import (
    ScenarioError,
    available_scenarios,
    load_scenario,
    simulate,
    write_run,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Prometheus — Mission Autopsy: reconstruct why a spacecraft mission failed.",
)

sim_app = typer.Typer(
    no_args_is_help=True,
    help="Generate synthetic missions with injected faults and hidden ground truth.",
)
app.add_typer(sim_app, name="sim")


class PingAnswer(BaseModel):
    """Schema for the ``llm-ping`` smoke test."""

    status: str = Field(description="Always the literal string 'ok'.")
    echo: str = Field(description="A short phrase proving the model responded.")


@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        False, "--version", help="Show the installed Prometheus version and exit."
    ),
) -> None:
    """Global options."""
    if version:
        typer.echo(f"prometheus {__version__}")
        raise typer.Exit()


@app.command("llm-ping")
def llm_ping(
    model: str | None = typer.Option(
        None, "--model", help="Override the configured model for this call."
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache", help="Bypass the on-disk response cache."
    ),
) -> None:
    """Send one small, real request to Groq and report tokens used."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    if not settings.groq_api_key:
        typer.secho(
            "GROQ_API_KEY is not set. Copy .env.example to .env and add your key.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        target_model = model or settings.require_model()
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    client = LLMClient(settings=settings, cache_enabled=not no_cache)
    prompt = (
        "This is a connectivity check. Reply with status \"ok\" and echo one short "
        "phrase (at most ten words) describing what you are."
    )
    try:
        answer = client.complete_json(prompt, PingAnswer, model=target_model, max_tokens=500)
    except (LLMError, ConfigError) as exc:
        typer.secho(f"LLM call failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps({"model": target_model, **answer.model_dump()}))
    typer.echo(f"usage: {client.stats.summary()}")


@app.command("ingest")
def ingest(
    run_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        help="Mission directory containing specs.yaml and the telemetry CSVs.",
    ),
) -> None:
    """Normalize one mission and print a summary plus its data-quality report."""
    try:
        result = ingest_run(run_dir)
    except IngestError as exc:
        typer.secho(f"ingest failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    spec = result.spec
    typer.echo(f"run: {result.run_dir}")
    typer.echo(f"scenario: {spec.scenario}  seed: {spec.seed}")
    typer.echo(
        f"time: {result.timeline[0].isoformat()} -> {result.timeline[-1].isoformat()}"
    )
    typer.echo(
        f"duration: {spec.duration_s:.0f}s  timestamps: {len(result.timeline)} (union)"
    )
    typer.echo(
        f"channels: {len(result.series)}  dependencies: {len(spec.dependencies)}  "
        f"events: {len(result.events)}"
    )
    typer.echo("")
    typer.echo(
        f"{'subsystem':<9} {'file':<24} {'rows':>5} {'channels':>8} {'interval':>8}"
    )
    for subsystem in SUBSYSTEMS:
        layout = spec.subsystems[subsystem]
        typer.echo(
            f"{subsystem.value:<9} {layout.file:<24} "
            f"{result.rows_by_subsystem[subsystem]:>5} {len(layout.channels):>8} "
            f"{layout.sample_interval_s:>7.0f}s"
        )

    aligned = result.aligned()
    typer.echo("")
    typer.echo(
        f"aligned view: {aligned.frame.shape[0]} x {aligned.frame.shape[1]} "
        "(union timeline, ffill within 1.0x native interval; see observed mask)"
    )
    typer.echo("")
    typer.echo(result.quality.render())


@sim_app.command("generate")
def sim_generate(
    scenario: str = typer.Argument(
        ..., help="Scenario name, e.g. battery_voltage_drop."
    ),
    seed: int = typer.Option(7, "--seed", "-s", min=0, help="RNG seed for the run."),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Output directory (default: data/generated/<scenario>_<seed>).",
    ),
    ground_truth_out: Path | None = typer.Option(
        None,
        "--ground-truth-out",
        help="Ground-truth directory (default: data/ground_truth/<scenario>_<seed>).",
    ),
) -> None:
    """Generate one synthetic mission and its hidden ground truth."""
    settings = get_settings()
    try:
        definition = load_scenario(scenario)
    except ScenarioError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        typer.echo(f"available scenarios: {', '.join(available_scenarios())}")
        raise typer.Exit(code=1) from exc

    run = simulate(definition, seed)
    out_dir = out or settings.data_dir / "generated" / f"{scenario}_{seed}"
    truth_dir = ground_truth_out or settings.data_dir / "ground_truth" / f"{scenario}_{seed}"
    written = write_run(run, out_dir, truth_dir)

    typer.echo(f"generated {scenario} (seed {seed})")
    for path in written.files:
        typer.echo(f"  {path}")
    typer.echo(f"  {written.ground_truth_path}  [ground truth: eval only]")
    truth = run.ground_truth
    root = truth["root_cause"]
    chain = truth["causal_chain"]
    typer.echo(f"root cause: {root['subsystem']} / {root['type']}")
    typer.echo(
        f"chain: {len(chain)} steps from {chain[0]['onset_s']:.0f}s "
        f"to {chain[-1]['onset_s']:.0f}s"
    )
    distractor = truth["distractor"]
    typer.echo(
        f"distractor: {distractor['type']} via {distractor['subsystem']}/"
        f"{distractor['channel']} at {distractor['start_s']:.0f}s (not causal)"
    )


if __name__ == "__main__":  # pragma: no cover
    app()
