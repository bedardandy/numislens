"""Tests for set manifest validation."""

from pathlib import Path

import pytest

from numislens_core.manifests import ManifestError, load_manifest, validate_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETS_DIR = REPO_ROOT / "core" / "sets"


@pytest.fixture
def minimal_manifest() -> dict:
    return {
        "id": "test-set",
        "name": "Test Set",
        "composition_ref": "90% silver dollar",
        "slots": [{"year": 1921, "mint": "P"}],
    }


def test_minimal_manifest_valid(minimal_manifest):
    assert validate_manifest(minimal_manifest) is minimal_manifest


@pytest.mark.parametrize(
    "filename",
    [
        "washington-quarters-1932-1964.json",
        "lincoln-wheat-1909-1958.json",
        "morgan-dollars-1878-1921.json",
        "peace-dollars-1921-1935.json",
    ],
)
def test_real_manifests_load(filename):
    manifest = load_manifest(SETS_DIR / filename)
    assert len(manifest["slots"]) > 0


def test_missing_year_raises(minimal_manifest):
    minimal_manifest["slots"] = [{"mint": "P"}]
    with pytest.raises(ManifestError, match="missing required field 'year'"):
        validate_manifest(minimal_manifest)


def test_bad_mint_raises(minimal_manifest):
    minimal_manifest["slots"] = [{"year": 1921, "mint": "X"}]
    with pytest.raises(ManifestError, match="invalid mint 'X'"):
        validate_manifest(minimal_manifest)


def test_duplicate_slot_raises(minimal_manifest):
    minimal_manifest["slots"] = [
        {"year": 1921, "mint": "P"},
        {"year": 1921, "mint": "P"},
    ]
    with pytest.raises(ManifestError, match="duplicate slot"):
        validate_manifest(minimal_manifest)


def test_empty_slots_raises(minimal_manifest):
    minimal_manifest["slots"] = []
    with pytest.raises(ManifestError, match="non-empty list"):
        validate_manifest(minimal_manifest)


def test_non_string_id_raises(minimal_manifest):
    minimal_manifest["id"] = 123
    with pytest.raises(ManifestError, match="'id' must be a non-empty string"):
        validate_manifest(minimal_manifest)
