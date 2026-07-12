"""NumisLens core: SQLite ledger for a coin collection."""

from .db import connect, init_db, migrate
from .ledger import (
    CoinNotFound,
    Ledger,
    LedgerError,
    LocationNotFound,
    MoveConflict,
    SetNotFound,
    SlotError,
    UnknownSeries,
)
from .manifests import ManifestError, load_manifest, validate_manifest
from .report import build_appraisal_report, face_value_cents

__version__ = "0.1.0"
__all__ = [
    "connect",
    "init_db",
    "migrate",
    "__version__",
    "Ledger",
    "LedgerError",
    "CoinNotFound",
    "LocationNotFound",
    "SetNotFound",
    "SlotError",
    "MoveConflict",
    "UnknownSeries",
    "load_manifest",
    "validate_manifest",
    "ManifestError",
    "build_appraisal_report",
    "face_value_cents",
]
