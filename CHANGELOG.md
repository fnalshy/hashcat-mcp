# Changelog

All notable changes to this project are documented here. This project aims to
follow [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-10-12

First public, cross-platform release. Complete rewrite of the original
single-file, Windows-only server.

### Added

- `hashcat_mcp/` package split into `config`, `jobs`, `server` and `__main__`.
- Cross-platform process helpers `process_alive()`, `terminate_process()` and
  `spawn_detached()`; POSIX uses `os.kill`/process groups, Windows uses
  `taskkill` and `CREATE_*` flags, each with a generic fallback.
- hashcat discovery through `HASHCAT_EXE` → config file → `PATH` → common
  install directories, with an actionable error when it cannot be found.
- CLI options `--hashcat`, `--hashcat-dir`, `--data-dir`, `--wordlists`,
  `--config`.
- `Content-Length` framing support alongside newline-delimited JSON-RPC.
- `pipx` / `uvx` friendly packaging with a `hashcat-mcp` console script and
  `python -m hashcat_mcp`.
- `pytest` suite driven by a fake hashcat stub (no GPU, no real binary).
- Client configuration examples, GitHub Actions CI, MIT license.

### Changed

- stdio is forced to UTF-8 and invalid bytes in hashcat output are replaced
  rather than raising.
- `config.json` fields remain backwards compatible; `DATA_DIR` is still read,
  with `HASHCAT_MCP_DATA` as the preferred equivalent.

## [1.0.0]

Internal, single-file, Windows-only server. Not released to the public.
