from __future__ import annotations

import sys


def main() -> None:
    from .config import load_config

    try:
        load_config()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
