"""hashcat-mcp: a cross-platform, stdlib-only stdio MCP server for hashcat.

The package exposes nine tools that identify hashes, inspect devices and
wordlists, submit asynchronous cracking jobs and read their results.
"""

import sys as _sys

__version__ = "2.0.0"
__all__ = ["__version__", "log"]


def log(*args):
    """Write a diagnostic line to stderr (never to stdout, which carries MCP)."""
    print("[hashcat-mcp]", *args, file=_sys.stderr, flush=True)
