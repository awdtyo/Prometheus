"""Unit normalization to Prometheus's canonical units.

Canonical units are SI-style where the source uses a non-SI variant: Celsius
becomes kelvin and kilobits per second become bits per second. Logarithmic
units (dB, dBW) and dimensionless indicators (%) are canonical as-is. Every
conversion records the original unit so the quality report can show it.

Unknown units are kept unchanged rather than guessed, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class UnitConversion:
    """A linear conversion from a source unit to its canonical unit."""

    original: str
    canonical: str
    factor: float = 1.0
    offset: float = 0.0
    known: bool = True

    @property
    def is_identity(self) -> bool:
        return self.original == self.canonical and self.factor == 1.0 and self.offset == 0.0

    def apply(self, values: np.ndarray) -> np.ndarray:
        """Convert values; identity conversions are returned unchanged."""
        if self.is_identity:
            return values
        return values * self.factor + self.offset

    def apply_scalar(self, value: float) -> float:
        """Convert a single scalar, used for nominal ranges."""
        return value * self.factor + self.offset

    def describe(self) -> str:
        """Human-readable conversion, e.g. ``C -> K``."""
        return f"{self.original} -> {self.canonical}"


_CONVERSIONS: dict[str, UnitConversion] = {
    # Temperature: SI is kelvin.
    "C": UnitConversion("C", "K", offset=273.15),
    "°C": UnitConversion("°C", "K", offset=273.15),
    "K": UnitConversion("K", "K"),
    # Telemetry rate: SI is bit/s.
    "kbps": UnitConversion("kbps", "bit/s", factor=1000.0),
    "Mbps": UnitConversion("Mbps", "bit/s", factor=1_000_000.0),
    # Already canonical.
    "V": UnitConversion("V", "V"),
    "A": UnitConversion("A", "A"),
    "W": UnitConversion("W", "W"),
    "%": UnitConversion("%", "%"),
    "dB": UnitConversion("dB", "dB"),
    "dBW": UnitConversion("dBW", "dBW"),
    "deg": UnitConversion("deg", "deg"),
    "rpm": UnitConversion("rpm", "rpm"),
    "s": UnitConversion("s", "s"),
    "bit/s": UnitConversion("bit/s", "bit/s"),
}


def conversion_for(unit: str) -> UnitConversion:
    """Return the conversion for ``unit``, or an identity for unknown units."""
    known = _CONVERSIONS.get(unit.strip())
    if known is not None:
        return known
    cleaned = unit.strip()
    return UnitConversion(cleaned, cleaned, known=False)
