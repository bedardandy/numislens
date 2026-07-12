"""NumisLens tiered photo identification/grading pipeline (Phase 4).

Pure REST client of the daemon + LAN GPU endpoints. The gate NEVER writes a
guessed value; disagreements escalate. See gate.py for the shipped rules.
"""

from __future__ import annotations

from .config import VisionConfig, load_config
from .pipeline import identify

__all__ = ["VisionConfig", "load_config", "identify"]
