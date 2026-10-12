"""``python -m hashcat_mcp`` entry point."""

from .server import main

if __name__ == "__main__":
    raise SystemExit(main())
