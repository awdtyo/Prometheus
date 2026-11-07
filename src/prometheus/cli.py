"""Command-line interface.

Phase 0 exposes ``llm-ping``; later phases add pipeline commands here.
"""

from __future__ import annotations

import json
import logging

import typer
from pydantic import BaseModel, Field

from prometheus import __version__
from prometheus.config import ConfigError, get_settings
from prometheus.llm.client import LLMClient, LLMError

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Prometheus — Mission Autopsy: reconstruct why a spacecraft mission failed.",
)


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


if __name__ == "__main__":  # pragma: no cover
    app()
