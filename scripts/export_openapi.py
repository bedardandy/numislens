#!/usr/bin/env python3
"""Export the daemon's OpenAPI spec to surfaces/openapi.json WITHOUT a server.

This is the single integration artifact every non-Claude surface consumes
(ChatGPT Actions, Gemini Gem). It is generated from the daemon in-process
(`create_app().openapi()`) — no uvicorn, no network — so it can never drift from
a running server's routes.

Post-processing done here (FastAPI does not emit these because auth is enforced
by a plain dependency, not a declared security scheme):

  * add a ``bearerAuth`` HTTP-bearer security scheme;
  * require it on every ``/api/v1`` operation (all of them need the token);
  * add a ``servers`` entry with a Tailnet placeholder URL to fill in.

Sanity assertions (fail loud): every path is under ``/api/v1``, the expected
count is present (20 original routes + quick-add = 21 unique templates... see
EXPECTED_PATHS below), quick-add is present, and every operation carries the
bearer requirement.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "surfaces" / "openapi.json"

# Placeholder base URL — replace YOUR-TAILNET-NAME with your tailnet host. The
# daemon binds localhost/Tailscale only; cloud assistants reach it through the
# Tailscale Funnel with the bearer token (see surfaces/README.md).
SERVER_URL = "https://numislens.YOUR-TAILNET-NAME.ts.net"

# The daemon exposed 22 unique path templates after Phase 5; Phase 6 added
# GET /api/v1/watch/status and POST /api/v1/watch/digest (24); Phase 4 adds the
# vision writeback PATCH /api/v1/coins/{accession} (same template as GET, so it
# is not a new path) — the new path count comes from... nothing: PATCH reuses
# the existing /api/v1/coins/{accession} template. Count stays 24. Assert the
# real number so an accidental route drop/add is caught at export time.
EXPECTED_PATH_COUNT = 24


def build_spec() -> dict:
    from numislens_daemon.app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_path=Path(tmp) / "export.db", token="export-placeholder")
        spec = app.openapi()

    # 1. bearerAuth security scheme.
    components = spec.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes.setdefault(
        "bearerAuth",
        {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Daemon bearer token. Send as: Authorization: Bearer <token>."
            ),
        },
    )

    # 2. Require bearerAuth on every /api/v1 operation.
    for path, item in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method, operation in item.items():
            if method.lower() not in {
                "get", "post", "put", "patch", "delete", "options", "head",
            }:
                continue
            operation["security"] = [{"bearerAuth": []}]

    # 3. servers placeholder.
    spec["servers"] = [
        {"url": SERVER_URL, "description": "NumisLens daemon over Tailscale (edit host)"}
    ]

    return spec


def assert_spec(spec: dict) -> None:
    paths = spec["paths"]
    non_api = [p for p in paths if not p.startswith("/api/v1")]
    assert not non_api, f"unexpected non-/api/v1 paths: {non_api}"
    assert len(paths) == EXPECTED_PATH_COUNT, (
        f"expected {EXPECTED_PATH_COUNT} paths, got {len(paths)}: "
        f"{sorted(paths)}"
    )
    assert "/api/v1/coins/quick" in paths, "quick-add path missing from spec"
    assert "bearerAuth" in spec["components"]["securitySchemes"]

    unsecured: list[str] = []
    for path, item in paths.items():
        for method, operation in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not operation.get("security"):
                unsecured.append(f"{method.upper()} {path}")
    assert not unsecured, f"/api/v1 operations without security: {unsecured}"


def main() -> int:
    spec = build_spec()
    assert_spec(spec)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUTPUT.relative_to(REPO_ROOT)} — "
        f"{len(spec['paths'])} paths, all /api/v1 secured with bearerAuth"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
