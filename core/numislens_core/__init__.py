"""NumisLens core: SQLite ledger for a coin collection."""

from .db import connect, init_db, migrate
from .ledger import (
    CoinNotFound,
    Ledger,
    LedgerError,
    LocationNotFound,
    SetNotFound,
    SlotError,
)
from .manifests import ManifestError, load_manifest, validate_manifest

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
    "load_manifest",
    "validate_manifest",
    "ManifestError",
]
