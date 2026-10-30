"""Version metadata that works with or without the optional domain package."""

from importlib.metadata import PackageNotFoundError, version

_FALLBACK_VERSION = "0.1.0"


def get_core_version() -> str:
    """Return the ``autopsy`` package version, falling back to the API version.

    The backend is deliberately runnable before the domain package is installed
    so the mock service layer can be developed and tested in isolation.
    """
    try:
        from autopsy import __version__ as core_version
    except ImportError:
        pass
    else:
        return str(core_version)

    try:
        return version("mission-autopsy")
    except PackageNotFoundError:
        return _FALLBACK_VERSION
