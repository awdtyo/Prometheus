"""Typed errors raised while loading configuration and fixtures."""


class IngestError(Exception):
    """A configuration file or fixture could not be read or validated.

    Loaders translate file-system, YAML, CSV, JSON, and Pydantic failures into
    this error so callers do not need to depend on those libraries' exception
    types.
    """
