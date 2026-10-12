# hashcat-mcp

A small, dependency-free [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server that wraps [hashcat](https://hashcat.net/hashcat/) so **any**
MCP-capable agent or client can identify hashes, inspect devices and wordlists,
submit asynchronous cracking jobs and read the recovered plains.

It is pure Python (standard library only), runs on **Windows, Linux and macOS**,
and speaks standard MCP over stdio (newline-delimited JSON-RPC, with
`Content-Length` framing accepted as well).

The repository ships **no hashcat binary and no wordlists** — you install
hashcat yourself (see [Install hashcat](#install-hashcat)). This keeps the
package small and avoids redistributing third-party binaries.

## Features

- **Nine tools** covering the common hashcat workflow (identify, devices,
  wordlists, merge, start, status, result, stop, potfile).
- **Cross-platform process management** — `taskkill` + `CREATE_*` flags on
  Windows, `os.kill` / process groups on POSIX, with a generic fallback when a
  platform API is missing.
- **Zero hard-coded paths** — hashcat is discovered automatically.
- **UTF-8 safe** — stdio is forced to UTF-8 and invalid bytes never raise.
- **Fully tested without a GPU** — the test-suite drives a fake hashcat stub.

## Requirements

- Python 3.9 or newer.
- hashcat installed and working (for real cracking; not needed for the tests).

## Install

Pick whichever runner you already use:

```bash
# pipx (recommended for CLI tools)
pipx install git+https://github.com/fnalshy/hashcat-mcp.git

# uvx directly from git
uvx --from git+https://github.com/fnalshy/hashcat-mcp.git hashcat-mcp

# plain pip
pip install git+https://github.com/fnalshy/hashcat-mcp.git
```

After installation the `hashcat-mcp` command starts the server on stdio.
You can also run it as a module: `python -m hashcat_mcp`.

## Point it at hashcat

hashcat is located in this order (first hit wins):

1. the `HASHCAT_EXE` environment variable
2. the `--hashcat` CLI option, or the `hashcat_exe` field in `config.json`
3. `hashcat` / `hashcat.exe` on your `PATH`
4. a short list of common install directories

If none is found the tools return an actionable error instead of crashing.
The data directory (job state + shared potfile), wordlist directories, and
`hashcat_dir` follow the same priority: CLI option, then environment variable,
then config file, then a user-writable default (`~/.hashcat-mcp`).

### CLI options

```text
hashcat-mcp [--hashcat PATH] [--hashcat-dir DIR] [--data-dir DIR]
            [--wordlists DIRS] [--config FILE]
```

- `--hashcat` — path to the hashcat executable.
- `--hashcat-dir` — working directory for hashcat (must contain the OpenCL kernels).
- `--data-dir` — where `jobs/` and `hashcat.potfile` live.
- `--wordlists` — `os.pathsep`-separated wordlist directories.
- `--config` — an explicit `config.json` to load.

### config.json (optional)

Copy [`config.example.json`](config.example.json) to `config.json` next to your
working directory (or point at it with `--config`). All fields are optional and
backwards compatible with the original single-file server:

```json
{
  "hashcat_exe": "/opt/hashcat/hashcat",
  "hashcat_dir": "/opt/hashcat",
  "data_dir": "~/.hashcat-mcp",
  "wordlist_dirs": ["~/wordlists", "/usr/share/wordlists"]
}
```

`config.json` is git-ignored so your local paths never end up in a commit.

## Configure your MCP client

Any stdio MCP client works. Ready-to-edit examples live in [`examples/`](examples).

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hashcat": {
      "command": "hashcat-mcp"
    }
  }
}
```

### Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "hashcat": {
      "command": "hashcat-mcp",
      "args": ["--data-dir", "~/.hashcat-mcp"]
    }
  }
}
```

### Generic stdio client (run as a module)

```json
{
  "mcpServers": {
    "hashcat": {
      "command": "python",
      "args": ["-m", "hashcat_mcp"],
      "env": {
        "HASHCAT_EXE": "/opt/hashcat/hashcat",
        "HASHCAT_MCP_DATA": "~/.hashcat-mcp",
        "WORDLIST_DIRS": "~/wordlists"
      }
    }
  }
}
```

`HASHCAT_MCP_DATA` is the preferred environment variable for the data
directory; the legacy `DATA_DIR` is still honoured.

## Tools

| Tool | Purpose |
| --- | --- |
| `hashcat_identify` | Identify the hashcat mode number of one or more hashes (`hashcat --identify`). |
| `hashcat_devices` | List available GPU/CPU devices and OpenCL backend information (`hashcat -I`). |
| `hashcat_wordlists` | List wordlist files in the configured directories; filter by keyword. |
| `hashcat_merge_rockyou` | Concatenate split `rockyou-partN` volumes into one `rockyou.txt`. |
| `hashcat_start` | Submit a cracking job in the background; returns a `job_id` immediately. |
| `hashcat_status` | Report running/finished state, progress, recovered count, speed, devices. |
| `hashcat_result` | Read the cracked `hash:plain` pairs for a job. |
| `hashcat_stop` | Stop a running job. |
| `hashcat_potfile` | Query cracked records in the shared potfile. |

### Typical workflow

1. `hashcat_identify` → learn the `hash_mode`.
2. `hashcat_start` with `hash_mode`, `hash` (or `hash_file`) and a `wordlist`
   (or a `mask` with `attack_mode: 3`) → get a `job_id`.
3. Poll `hashcat_status` until `state` is `finished`.
4. `hashcat_result` → read the recovered plains.

## Install hashcat

- **Windows**: download the hashcat release archive from
  <https://hashcat.net/hashcat/>, extract it somewhere (e.g. under your user
  profile) and either add the folder to `PATH` or set `HASHCAT_EXE` to the
  extracted `hashcat.exe`. Install a recent GPU driver with OpenCL support.
- **Linux**: `apt install hashcat` (Debian/Ubuntu), `pacman -S hashcat`
  (Arch), or build from the release archive. Ensure the OpenCL runtime is
  present (`ocl-icd-libopencl1`, plus your vendor's ICD).
- **macOS**: `brew install hashcat`.

### Wordlists

This project does not ship wordlists. Good starting points:

- `rockyou.txt` — available in Kali (`/usr/share/wordlists/rockyou.txt`).
- The split rockyou volumes (`rockyou-partN`) can be concatenated with the
  `hashcat_merge_rockyou` tool.
- hashcat itself ships a tiny `example.dict` next to the binary, used as a
  fallback default when no rockyou is configured.

## Development and tests

The test-suite uses a fake hashcat stub, so it needs neither a GPU nor a real
hashcat binary:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Lint/format choices are intentionally unopinionated; the only CI gate is
`pytest` on Ubuntu.

## Troubleshooting

- **`hashcat executable not found`** — set `HASHCAT_EXE`, add `hashcat_exe` to
  `config.json`, or put hashcat on `PATH`.
- **`No devices found` / OpenCL errors** — install/refresh your GPU driver and
  OpenCL runtime. `hashcat_devices` shows what hashcat can see.
- **Jobs finish instantly** — check the job `log_tail` returned by
  `hashcat_status`; a missing wordlist or an unrecognised mode usually explains it.
- **Windows: nothing captured in the job log** — hashcat is spawned with
  `CREATE_NO_WINDOW`; the log is written to `<data_dir>/jobs/<job_id>/log.txt`.

## License

MIT — see [LICENSE](LICENSE).

## 中文说明

`hashcat-mcp` 把 hashcat 封装为标准的 stdio MCP server，纯标准库实现，可在
Windows / Linux / macOS 运行，供任意支持 MCP 的客户端（Claude Desktop、Cursor、
Cline、Windsurf、Yan Agent 等）调用。仓库不含 hashcat 二进制与字典，需自行安装
（见上文）。安装：`pipx install .` 或 `uvx --from . hashcat-mcp`。配置：环境变量
`HASHCAT_EXE / HASHCAT_MCP_DATA / WORDLIST_DIRS`，或 `config.json`，或 CLI 参数。
长任务用 `hashcat_start` 拿到 `job_id`，再轮询 `hashcat_status`，用
`hashcat_result` 取回明文。
