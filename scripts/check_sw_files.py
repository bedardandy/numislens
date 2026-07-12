#!/usr/bin/env python3
"""Verify service worker precache /js URLs match JS files on disk (bidirectional)."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    public = root / "public"
    sw_path = public / "sw.js"

    text = sw_path.read_text(encoding="utf-8")
    listed_urls = re.findall(r"""['"](/js/[^'"]+)['"]""", text)
    listed = {url.lstrip("/") for url in listed_urls}

    js_root = public / "js"
    on_disk: set[str] = set()
    for path in js_root.rglob("*.js"):
        rel = path.relative_to(public).as_posix()
        on_disk.add(rel)

    missing_on_disk = listed - on_disk
    unlisted = on_disk - listed

    if not missing_on_disk and not unlisted:
        n = len(listed)
        print(f"PASS: sw.js precache /js list matches disk ({n} files)")
        return 0

    print("FAIL: sw.js precache /js list mismatch")
    print(f"missing_on_disk: {', '.join(sorted(missing_on_disk)) or '(none)'}")
    print(f"unlisted: {', '.join(sorted(unlisted)) or '(none)'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
