"""Detector registry.

Each detector module exposes ``DETECTORS``, a list of callables that take a
:class:`mdgoat.models.Document` and return an iterable of
:class:`mdgoat.models.Finding`.
"""

from __future__ import annotations

from typing import Callable, Iterable, List

from ..models import Document, Finding
from . import artifacts, efficiency, security, structure

Detector = Callable[[Document], Iterable[Finding]]

ALL_DETECTORS: List[Detector] = (
    list(security.DETECTORS)
    + list(artifacts.DETECTORS)
    + list(structure.DETECTORS)
    + list(efficiency.DETECTORS)
)

__all__ = ["ALL_DETECTORS", "Detector"]
