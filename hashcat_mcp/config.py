"""Configuration discovery and path resolution for hashcat-mcp.

No machine-specific paths are baked into this module. ``hashcat`` is located
in this order:

1. the ``HASHCAT_EXE`` environment variable
2. the ``--hashcat`` CLI option or the ``hashcat_exe`` config-file field
3. ``hashcat`` / ``hashcat.exe`` found on ``PATH``
4. a short list of common install directories

The ``data_dir`` (jobs + shared potfile) and ``wordlist_dirs`` follow the same
priority: CLI option, then environment variable, then config file, then a
user-writable default.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

SERVER_NAME = "hashcat-mcp"
CONFIG_FILENAME = "config.json"

_HASHCAT_NAMES = ("hashcat", "hashcat.exe")


def _common_hashcat_dirs() -> List[str]:
    """Generic install locations, built without hardcoding any drive letter."""
    dirs = [
        "/usr/local/bin",
        "/usr/bin",
        "/opt/homebrew/bin",
        "/opt/homebrew/opt/hashcat/bin",
        "/opt/hashcat",
        "/opt/hashcat/bin",
        "/usr/share/hashcat",
        os.path.join(os.path.expanduser("~"), "hashcat"),
        os.path.join(os.path.expanduser("~"), "tools", "hashcat"),
    ]
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if base:
            dirs.append(os.path.join(base, "hashcat"))
    return dirs


def default_data_dir(env: Optional[Dict[str, str]] = None) -> str:
    """User-writable default location for jobs and the shared potfile."""
    env = os.environ if env is None else env
    for key in ("HASHCAT_MCP_DATA", "DATA_DIR"):
        if env.get(key):
            return os.path.expanduser(os.path.expandvars(env[key]))
    return os.path.join(os.path.expanduser("~"), ".hashcat-mcp")


def find_hashcat(explicit: Optional[str] = None,
                 hashcat_dir: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Return a usable hashcat executable path, or ``None`` if none is found."""
    env = os.environ if env is None else env

    # 1. environment variable, then 2. explicit config/CLI value.
    for candidate in (env.get("HASHCAT_EXE"), explicit):
        if candidate:
            candidate = os.path.expanduser(os.path.expandvars(candidate))
            if os.path.isfile(candidate):
                return candidate

    # 3. PATH lookup.
    for name in _HASHCAT_NAMES:
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return found

    # 4. common install directories.
    dirs: List[str] = []
    for base in (hashcat_dir, env.get("HASHCAT_DIR")):
        if base:
            dirs.append(os.path.expanduser(os.path.expandvars(base)))
    dirs.extend(_common_hashcat_dirs())
    for base in dirs:
        for name in _HASHCAT_NAMES:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                return candidate
    return None


@dataclass
class Config:
    """Resolved runtime configuration."""

    hashcat_exe: Optional[str] = None
    hashcat_dir: Optional[str] = None
    data_dir: str = ""
    wordlist_dirs: List[str] = field(default_factory=list)
    config_file: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.data_dir:
            self.data_dir = default_data_dir()
        self.data_dir = os.path.abspath(os.path.expanduser(self.data_dir))
        if self.hashcat_exe:
            self.hashcat_exe = os.path.abspath(os.path.expanduser(self.hashcat_exe))
        if not self.hashcat_dir and self.hashcat_exe:
            self.hashcat_dir = os.path.dirname(self.hashcat_exe)
        elif self.hashcat_dir:
            self.hashcat_dir = os.path.abspath(os.path.expanduser(self.hashcat_dir))
        self.wordlist_dirs = [
            os.path.abspath(os.path.expanduser(os.path.expandvars(p)))
            for p in self.wordlist_dirs
        ]

    @property
    def jobs_dir(self) -> str:
        return os.path.join(self.data_dir, "jobs")

    @property
    def potfile(self) -> str:
        return os.path.join(self.data_dir, "hashcat.potfile")

    def ensure_dirs(self) -> None:
        os.makedirs(self.jobs_dir, exist_ok=True)

    def to_dict(self) -> dict:
        return {
            "hashcat_exe": self.hashcat_exe,
            "hashcat_dir": self.hashcat_dir,
            "data_dir": self.data_dir,
            "wordlist_dirs": list(self.wordlist_dirs),
            "config_file": self.config_file,
        }


def _read_config_file(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _config_candidates(explicit: Optional[str],
                       env: Dict[str, str]) -> List[str]:
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    for key in ("HASHCAT_MCP_DATA", "DATA_DIR"):
        if env.get(key):
            candidates.append(os.path.join(env[key], CONFIG_FILENAME))
    candidates.append(os.path.join(os.getcwd(), CONFIG_FILENAME))
    return candidates


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hashcat-mcp",
        description="Cross-platform stdio MCP server wrapping hashcat.",
    )
    parser.add_argument("--hashcat", metavar="PATH",
                        help="Path to the hashcat executable.")
    parser.add_argument("--hashcat-dir", metavar="DIR",
                        help="Working directory for hashcat (holds OpenCL kernels).")
    parser.add_argument("--data-dir", metavar="DIR",
                        help="Directory for job state and the shared potfile.")
    parser.add_argument("--wordlists", metavar="DIRS",
                        help="Wordlist directories separated by os.pathsep.")
    parser.add_argument("--config", metavar="FILE",
                        help="Explicit config.json to load.")
    return parser


def load_config(argv: Optional[List[str]] = None,
                env: Optional[Dict[str, str]] = None) -> Config:
    """Build a :class:`Config` from CLI args, environment and config file."""
    env = os.environ if env is None else env
    args = build_arg_parser().parse_args(argv)

    file_cfg: Dict = {}
    used_file: Optional[str] = None
    for candidate in _config_candidates(args.config, env):
        if os.path.isfile(candidate):
            file_cfg = _read_config_file(candidate)
            used_file = candidate
            break

    data_dir = (args.data_dir
                or env.get("HASHCAT_MCP_DATA")
                or env.get("DATA_DIR")
                or file_cfg.get("data_dir")
                or default_data_dir(env))

    if args.wordlists:
        wordlists = [p for p in args.wordlists.split(os.pathsep) if p]
    elif env.get("WORDLIST_DIRS"):
        wordlists = [p for p in env["WORDLIST_DIRS"].split(os.pathsep) if p]
    elif file_cfg.get("wordlist_dirs"):
        wordlists = list(file_cfg["wordlist_dirs"])
    else:
        wordlists = []

    hashcat_dir = (args.hashcat_dir
                   or env.get("HASHCAT_DIR")
                   or file_cfg.get("hashcat_dir"))

    hashcat_exe = find_hashcat(
        explicit=args.hashcat or file_cfg.get("hashcat_exe"),
        hashcat_dir=hashcat_dir,
        env=env,
    )

    return Config(
        hashcat_exe=hashcat_exe,
        hashcat_dir=hashcat_dir,
        data_dir=data_dir,
        wordlist_dirs=wordlists,
        config_file=used_file,
    )


# ---------------------------------------------------------------------------
# Wordlist / rules resolution
# ---------------------------------------------------------------------------

def merge_rockyou(cfg: Config,
                  src_dir: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Concatenate numbered rockyou part files into ``data_dir/rockyou.txt``."""
    out = os.path.join(cfg.data_dir, "rockyou.txt")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out, None

    if not src_dir:
        candidates = []
        for base in cfg.wordlist_dirs:
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                if any(f.lower().startswith("rockyou-part") for f in files):
                    candidates.append(root)
        src_dir = candidates[0] if candidates else None

    if not src_dir or not os.path.isdir(src_dir):
        return None, "rockyou source dir not found"

    parts = [f for f in os.listdir(src_dir)
             if re.match(r"(?i)rockyou-part\d+", f)]

    def _key(name: str) -> int:
        match = re.search(r"(\d+)", name)
        return int(match.group(1)) if match else 0

    parts.sort(key=_key)
    os.makedirs(cfg.data_dir, exist_ok=True)
    with open(out, "wb") as writer:
        for name in parts:
            with open(os.path.join(src_dir, name), "rb") as reader:
                shutil.copyfileobj(reader, writer, length=1 << 20)
    return out, None


def resolve_wordlist(cfg: Config,
                     name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a wordlist keyword or path to an absolute file path."""
    if name:
        name = os.path.expanduser(os.path.expandvars(name))
        if os.path.isfile(name):
            return name, None
        low = name.lower()
        found: List[str] = []
        for base in cfg.wordlist_dirs:
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for fname in files:
                    if fname.lower().endswith(".txt") and low in fname.lower():
                        found.append(os.path.join(root, fname))
            if found:
                break
        if not found and "rockyou" in low:
            out = os.path.join(cfg.data_dir, "rockyou.txt")
            if os.path.isfile(out):
                return out, None
        if found:
            found.sort(key=os.path.getsize, reverse=True)
            return found[0], None
        return None, "wordlist not found for '%s'" % name

    out = os.path.join(cfg.data_dir, "rockyou.txt")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out, None
    merged, err = merge_rockyou(cfg)
    if merged:
        return merged, None
    if cfg.hashcat_dir:
        example = os.path.join(cfg.hashcat_dir, "example.dict")
        if os.path.isfile(example):
            return example, "default rockyou unavailable (%s); using example.dict" % err
    return None, err or "no default wordlist configured"


def resolve_rules(cfg: Config,
                  name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a rules file path or a bare name inside hashcat's rules/ dir."""
    if not name:
        return None, None
    name = os.path.expanduser(os.path.expandvars(name))
    if os.path.isfile(name):
        return name, None
    if cfg.hashcat_dir:
        for candidate in (os.path.join(cfg.hashcat_dir, "rules", name),
                          os.path.join(cfg.hashcat_dir, "rules", name + ".rule")):
            if os.path.isfile(candidate):
                return candidate, None
    return None, "rules file not found: %s" % name
