# hashcat-mcp

一个轻量、无第三方依赖的 [Model Context Protocol](https://modelcontextprotocol.io)
（MCP）服务器，把 [hashcat](https://hashcat.net/hashcat/) 封装成标准工具，使**任意**
支持 MCP 的 Agent/客户端都能识别哈希、查看设备与字典、提交异步破解任务，并读取已还原的明文。

纯 Python 标准库实现，可在 **Windows / Linux / macOS** 运行，通过 stdio 讲标准 MCP
（按行分隔的 JSON-RPC；同时兼容 `Content-Length` 分帧，以适配更多客户端）。

仓库**不包含** hashcat 二进制与任何字典，需使用者自行安装（见
[安装 hashcat](#安装-hashcat)）。这样可以保持包体积小，并避免再分发第三方二进制。

英文说明见文末 [English](#english)。

## 特性

- **9 个工具**覆盖常见 hashcat 工作流（识别、设备、字典、合并、启动、状态、结果、停止、potfile）。
- **跨平台进程管理** —— Windows 使用 `taskkill` + `CREATE_*` 标志，POSIX 使用
  `os.kill` / 进程组；平台 API 缺失时降级而不是报错。
- **零硬编码路径** —— 自动发现 hashcat。
- **UTF-8 安全** —— stdio 强制 UTF-8，hashcat 输出中的非法字节不会抛异常。
- **测试不依赖 GPU** —— 测试套件用假 hashcat 桩驱动。

## 环境要求

- Python 3.9 或更高版本。
- 已安装可用的 hashcat（真实破解时需要；跑测试不需要）。

## 安装

按你已有的运行器任选其一：

```bash
# pipx（推荐用于命令行工具）
pipx install git+https://github.com/fnalshy/hashcat-mcp.git

# uvx，直接从 git 运行
uvx --from git+https://github.com/fnalshy/hashcat-mcp.git hashcat-mcp

# 普通 pip
pip install git+https://github.com/fnalshy/hashcat-mcp.git
```

安装后，`hashcat-mcp` 命令即在 stdio 上启动服务器。也可以用模块方式运行：
`python -m hashcat_mcp`。

## 定位 hashcat

按以下顺序查找 hashcat（命中即止）：

1. 环境变量 `HASHCAT_EXE`
2. 命令行参数 `--hashcat`，或 `config.json` 中的 `hashcat_exe` 字段
3. `PATH` 中的 `hashcat` / `hashcat.exe`
4. 一小份常见安装目录

若都找不到，工具会返回可操作的错误提示，而不是崩溃。数据目录（任务状态 + 共享 potfile）、
字典目录、`hashcat_dir` 采用同样的优先级：命令行参数 → 环境变量 → 配置文件 →
用户可写默认值（`~/.hashcat-mcp`）。

### 命令行参数

```text
hashcat-mcp [--hashcat PATH] [--hashcat-dir DIR] [--data-dir DIR]
            [--wordlists DIRS] [--config FILE]
```

- `--hashcat` —— hashcat 可执行文件路径。
- `--hashcat-dir` —— hashcat 的工作目录（需包含 OpenCL 内核）。
- `--data-dir` —— `jobs/` 与 `hashcat.potfile` 所在目录。
- `--wordlists` —— 以 `os.pathsep` 分隔的字典目录列表。
- `--config` —— 显式指定要加载的 `config.json`。

### config.json（可选）

把 [`config.example.json`](config.example.json) 复制为工作目录下的 `config.json`
（或用 `--config` 指向它）。所有字段都是可选的，并与最初的单文件版本向后兼容：

```json
{
  "hashcat_exe": "/opt/hashcat/hashcat",
  "hashcat_dir": "/opt/hashcat",
  "data_dir": "~/.hashcat-mcp",
  "wordlist_dirs": ["~/wordlists", "/usr/share/wordlists"]
}
```

`config.json` 已被 git 忽略，本机路径不会进入提交。

## 配置 MCP 客户端

任意 stdio MCP 客户端都可使用。可编辑的样例见 [`examples/`](examples)。

### Claude Desktop

`claude_desktop_config.json`：

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

`.cursor/mcp.json`：

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

### 通用 stdio 客户端（以模块方式运行）

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

`HASHCAT_MCP_DATA` 是数据目录的首选环境变量；旧的 `DATA_DIR` 仍然受支持。

## 工具

| 工具 | 用途 |
| --- | --- |
| `hashcat_identify` | 识别一个或多个哈希的 hashcat 模式编号（`hashcat --identify`）。 |
| `hashcat_devices` | 列出可用的 GPU/CPU 设备与 OpenCL 后端信息（`hashcat -I`）。 |
| `hashcat_wordlists` | 列出已配置字典目录中的字典文件；可按关键字过滤。 |
| `hashcat_merge_rockyou` | 把分卷 `rockyou-partN` 按序合并为单个 `rockyou.txt`。 |
| `hashcat_start` | 后台提交一次破解任务；立即返回 `job_id`。 |
| `hashcat_status` | 查询运行中/已结束、进度、已恢复数、速度、设备。 |
| `hashcat_result` | 读取任务的 `hash:明文` 结果。 |
| `hashcat_stop` | 停止一个正在运行的任务。 |
| `hashcat_potfile` | 查询共享 potfile 中已破解的记录。 |

### 典型流程

1. `hashcat_identify` → 得到 `hash_mode`。
2. `hashcat_start`，传入 `hash_mode`、`hash`（或 `hash_file`）与 `wordlist`
   （或用 `mask` + `attack_mode: 3`）→ 得到 `job_id`。
3. 轮询 `hashcat_status`，直到 `state` 为 `finished`。
4. `hashcat_result` → 读取已还原的明文。

## 安装 hashcat

- **Windows**：从 <https://hashcat.net/hashcat/> 下载发行包，解压到某处（例如用户目录），
  把该目录加入 `PATH`，或把 `HASHCAT_EXE` 指向解压出的 `hashcat.exe`。请安装支持
  OpenCL 的新版显卡驱动。
- **Linux**：`apt install hashcat`（Debian/Ubuntu）、`pacman -S hashcat`（Arch），
  或用发行包自行编译。确保存在 OpenCL 运行时（`ocl-icd-libopencl1`，以及厂商 ICD）。
- **macOS**：`brew install hashcat`。

### 字典

本项目不附带字典。常见起点：

- `rockyou.txt` —— Kali 中自带（`/usr/share/wordlists/rockyou.txt`）。
- 分卷 rockyou（`rockyou-partN`）可用 `hashcat_merge_rockyou` 工具合并。
- hashcat 自身在二进制旁带有一个很小的 `example.dict`，在未配置 rockyou 时作为兜底默认字典。

## 开发与测试

测试套件使用假 hashcat 桩，既不需要 GPU，也不需要真实 hashcat 二进制：

```bash
python -m pip install -e ".[test]"
python -m pytest
```

对 lint/格式工具不做强制约定；CI 的唯一门禁是在 Ubuntu 上跑 `pytest`。

## 常见问题

- **`hashcat executable not found`** —— 设置 `HASHCAT_EXE`，或在 `config.json` 里
  加 `hashcat_exe`，或把 hashcat 加入 `PATH`。
- **`No devices found` / OpenCL 报错** —— 安装/更新显卡驱动与 OpenCL 运行时。
  `hashcat_devices` 可显示 hashcat 能看到什么。
- **任务瞬间结束** —— 查看 `hashcat_status` 返回的 `log_tail`；通常是缺字典或模式无法识别。
- **Windows：任务日志为空** —— hashcat 以 `CREATE_NO_WINDOW` 派生；日志写在
  `<data_dir>/jobs/<job_id>/log.txt`。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。

---

## English

A small, dependency-free [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server that wraps [hashcat](https://hashcat.net/hashcat/) so any
MCP-capable agent or client can identify hashes, inspect devices and wordlists,
submit asynchronous cracking jobs and read the recovered plains.

Pure Python (standard library only), running on **Windows, Linux and macOS**,
speaking standard MCP over stdio (newline-delimited JSON-RPC, with
`Content-Length` framing accepted as well). The repository ships **no hashcat
binary and no wordlists** — you install hashcat yourself.

### Features

- Nine tools covering the common hashcat workflow (identify, devices,
  wordlists, merge, start, status, result, stop, potfile).
- Cross-platform process management — `taskkill` + `CREATE_*` flags on Windows,
  `os.kill` / process groups on POSIX, with a generic fallback when a platform
  API is missing.
- Zero hard-coded paths — hashcat is discovered automatically.
- UTF-8 safe — stdio is forced to UTF-8 and invalid bytes never raise.
- Fully tested without a GPU — the test-suite drives a fake hashcat stub.

### Install

```bash
pipx install git+https://github.com/fnalshy/hashcat-mcp.git
# or
uvx --from git+https://github.com/fnalshy/hashcat-mcp.git hashcat-mcp
# or
pip install git+https://github.com/fnalshy/hashcat-mcp.git
```

### Point it at hashcat

hashcat is located in this order (first hit wins): the `HASHCAT_EXE`
environment variable → the `--hashcat` option or `hashcat_exe` config field →
`hashcat`/`hashcat.exe` on `PATH` → a short list of common install directories.
If none is found the tools return an actionable error instead of crashing.

### Client configuration

```json
{
  "mcpServers": {
    "hashcat": {
      "command": "hashcat-mcp"
    }
  }
}
```

Also works as a module: `python -m hashcat_mcp`. See [`examples/`](examples) for
Claude Desktop, Cursor and generic stdio variants.

### Tools

`hashcat_identify`, `hashcat_devices`, `hashcat_wordlists`,
`hashcat_merge_rockyou`, `hashcat_start`, `hashcat_status`, `hashcat_result`,
`hashcat_stop`, `hashcat_potfile`.

Submit a long-running job with `hashcat_start` (returns a `job_id`), poll
`hashcat_status`, then read `hashcat_result` for the recovered plains.

### Development

```bash
python -m pip install -e ".[test]"
python -m pytest
```

### License

MIT — see [LICENSE](LICENSE).
