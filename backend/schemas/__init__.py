"""Pydantic request/response DTOs for the HTTP API.

API schemas are intentionally separate from ``autopsy`` domain models so the
wire contract can evolve without coupling the core package to HTTP.
"""
