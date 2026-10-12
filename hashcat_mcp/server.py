"""MCP protocol handling and the nine hashcat tools."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

from . import __version__, log
from .config import (SERVER_NAME, load_config, merge_rockyou,
                     resolve_rules, resolve_wordlist)
from . import jobs

# Advertised protocol version and the set we are willing to echo back during
# negotiation.
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")

INSTRUCTIONS = (
    "hashcat cracking tools: identify / devices / wordlists / merge_rockyou / "
    "start / status / result / stop / potfile. Submit a long-running job with "
    "hashcat_start (returns a job_id), then poll hashcat_status and read "
    "hashcat_result for recovered plains."
)

HASHCAT_MISSING = (
    "[hashcat-mcp] hashcat executable not found. Install hashcat and either set "
    "the HASHCAT_EXE environment variable, add a hashcat_exe entry to config.json, "
    "or put hashcat on your PATH."
)


TOOLS = [
    {
        "name": "hashcat_identify",
        "description": "Identify the hashcat mode number of one or more hashes (runs `hashcat --identify`, no GPU).",
        "inputSchema": {
            "type": "object",
            "properties": {"hash": {"type": "string", "description": "One or more hashes, newline separated."}},
            "required": ["hash"],
        },
    },
    {
        "name": "hashcat_devices",
        "description": "List available GPU/CPU devices and OpenCL backend information (`hashcat -I`).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "hashcat_wordlists",
        "description": "List wordlist files found in the configured wordlist directories; filter by keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {"type": "string", "description": "Optional case-insensitive filename filter."},
                "limit": {"type": "integer", "description": "Maximum entries to return (default 50)."},
            },
        },
    },
    {
        "name": "hashcat_merge_rockyou",
        "description": "Concatenate split rockyou volumes (rockyou-partN) into a single rockyou.txt; returns the existing file if present.",
        "inputSchema": {
            "type": "object",
            "properties": {"source_dir": {"type": "string", "description": "Optional directory of the split parts; auto-detected when omitted."}},
        },
    },
    {
        "name": "hashcat_start",
        "description": "Submit a cracking job (runs in the background and returns a job_id immediately). Supports dictionary (-a 0), mask (-a 3) and rules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hash": {"type": "string", "description": "Hash string(s) to crack (or use hash_file)."},
                "hash_file": {"type": "string", "description": "Path to a hash list file (alternative to hash)."},
                "hash_mode": {"type": "integer", "description": "hashcat mode number, e.g. 0=MD5, 1000=NTLM, 13721=VeraCrypt."},
                "attack_mode": {"type": "integer", "description": "Attack mode, default 0 (dictionary); 3 for mask."},
                "wordlist": {"type": "string", "description": "Wordlist path or keyword (e.g. rockyou); defaults to the merged rockyou."},
                "rules": {"type": "string", "description": "Rules file path or a name inside hashcat's rules/ directory."},
                "mask": {"type": "string", "description": "Mask, used when attack_mode=3, e.g. ?d?d?d?d?d?d."},
                "session": {"type": "string", "description": "Optional session name."},
                "runtime": {"type": "integer", "description": "Optional maximum runtime in seconds."},
                "workload": {"type": "integer", "description": "Optional workload profile 1-4."},
                "extra_args": {"type": "array", "items": {"type": "string"}, "description": "Extra raw hashcat arguments."},
            },
            "required": ["hash_mode"],
        },
    },
    {
        "name": "hashcat_status",
        "description": "Report job state: running/finished, progress, recovered count, speed, devices and cracked plains.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    },
    {
        "name": "hashcat_result",
        "description": "Read the cracked hash:plain results of a job (from the outfile and potfile).",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    },
    {
        "name": "hashcat_stop",
        "description": "Stop a running job.",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
    },
    {
        "name": "hashcat_potfile",
        "description": "Query cracked records in the shared potfile, optionally filtered by mode.",
        "inputSchema": {
            "type": "object",
            "properties": {"hash_mode": {"type": "integer"}, "limit": {"type": "integer"}},
        },
    },
]

TOOL_METHODS = {
    "hashcat_identify": "t_identify",
    "hashcat_devices": "t_devices",
    "hashcat_wordlists": "t_wordlists",
    "hashcat_merge_rockyou": "t_merge_rockyou",
    "hashcat_start": "t_start",
    "hashcat_status": "t_status",
    "hashcat_result": "t_result",
    "hashcat_stop": "t_stop",
    "hashcat_potfile": "t_potfile",
}


class HashcatServer:
    """Holds one :class:`~hashcat_mcp.config.Config` and serves MCP requests."""

    def __init__(self, config):
        self.config = config

    # -- hashcat invocation -------------------------------------------------
    def _run_hc(self, args, timeout=180, cwd=None):
        """Run hashcat synchronously; return ``(returncode, output)``."""
        exe = self.config.hashcat_exe
        if not exe:
            return -2, HASHCAT_MISSING
        try:
            proc = subprocess.run(
                [exe] + args, cwd=cwd or self.config.hashcat_dir,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=timeout,
            )
            return proc.returncode, proc.stdout.decode("utf-8", "replace")
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode("utf-8", "replace")
            return -1, out + "\n[hashcat-mcp] timeout after %ss" % timeout
        except FileNotFoundError:
            return -2, "[hashcat-mcp] hashcat not found: %s" % exe

    # -- tool handlers ------------------------------------------------------
    def t_identify(self, args):
        self.config.ensure_dirs()
        hash_str = args.get("hash", "")
        tmp = os.path.join(self.config.jobs_dir, "_identify.txt")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(str(hash_str).strip() + "\n")
        _rc, out = self._run_hc(["--identify", tmp], timeout=180)
        modes = []
        for line in out.splitlines():
            match = re.match(r"\s*(\d+)\s*\|\s*(.+?)\s*\|", line)
            if match:
                modes.append({"mode": int(match.group(1)), "name": match.group(2).strip()})
        if not modes:
            return {"ok": False, "raw": out[-2000:]}
        return {"ok": True, "matches": modes}

    def t_devices(self, _args):
        rc, out = self._run_hc(["-I"], timeout=120)
        return {"ok": rc >= 0, "output": out[-4000:]}

    def t_wordlists(self, args):
        self.config.ensure_dirs()
        flt = (args.get("filter") or "").lower()
        limit = int(args.get("limit", 50))
        items = []
        seen = set()
        for base in self.config.wordlist_dirs:
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for fname in files:
                    if not fname.lower().endswith(".txt"):
                        continue
                    path = os.path.join(root, fname)
                    if path in seen:
                        continue
                    seen.add(path)
                    if flt and flt not in fname.lower():
                        continue
                    try:
                        size = os.path.getsize(path)
                    except OSError:
                        size = 0
                    items.append({"name": fname, "path": path, "size_mb": round(size / 1048576, 2)})
        items.sort(key=lambda x: x["size_mb"], reverse=True)
        merged = os.path.join(self.config.data_dir, "rockyou.txt")
        return {
            "ok": True,
            "merged_rockyou": merged if os.path.isfile(merged) else None,
            "total": len(items),
            "count": min(len(items), limit),
            "wordlists": items[:limit],
        }

    def t_merge_rockyou(self, args):
        out, err = merge_rockyou(self.config, args.get("source_dir"))
        if not out:
            return {"ok": False, "error": err}
        return {"ok": True, "path": out, "size_mb": round(os.path.getsize(out) / 1048576, 2)}

    def t_start(self, args):
        cfg = self.config
        cfg.ensure_dirs()
        if not cfg.hashcat_exe:
            return {"ok": False, "error": HASHCAT_MISSING}
        hash_mode = args.get("hash_mode")
        if hash_mode is None:
            return {"ok": False, "error": "hash_mode is required"}
        attack_mode = int(args.get("attack_mode", 0))

        job_id = jobs.new_job_id()
        jd = jobs.job_dir(cfg, job_id)
        os.makedirs(jd, exist_ok=True)
        hash_file = os.path.join(jd, "hash.txt")

        if args.get("hash_file"):
            src = args["hash_file"]
            if not os.path.isfile(src):
                return {"ok": False, "error": "hash_file not found: %s" % src}
            with open(src, "r", encoding="utf-8", errors="replace") as reader, \
                    open(hash_file, "w", encoding="utf-8") as writer:
                writer.write(reader.read())
        elif args.get("hash"):
            with open(hash_file, "w", encoding="utf-8") as handle:
                handle.write(str(args["hash"]).strip() + "\n")
        else:
            return {"ok": False, "error": "provide hash or hash_file"}

        notes = []
        cmd = [cfg.hashcat_exe, "-m", str(int(hash_mode)), "-a", str(attack_mode), hash_file]
        if attack_mode == 3:
            mask = args.get("mask")
            if not mask:
                return {"ok": False, "error": "mask required for attack_mode 3"}
            cmd.append(mask)
        else:
            wordlist, err = resolve_wordlist(cfg, args.get("wordlist"))
            if not wordlist:
                return {"ok": False, "error": err}
            cmd.append(wordlist)
            if err:
                notes.append(err)
            rules, rerr = resolve_rules(cfg, args.get("rules"))
            if rerr:
                return {"ok": False, "error": rerr}
            if rules:
                cmd += ["-r", rules]

        out_file = os.path.join(jd, "out.txt")
        cmd += ["-o", out_file, "--potfile-path", cfg.potfile,
                "--status", "--status-json", "--status-timer=1"]
        if args.get("session"):
            cmd += ["--session", str(args["session"])]
        if args.get("runtime"):
            cmd += ["--runtime", str(int(args["runtime"]))]
        if args.get("workload"):
            cmd += ["-w", str(int(args["workload"]))]
        for extra in (args.get("extra_args") or []):
            cmd.append(str(extra))

        log_file = os.path.join(jd, "log.txt")
        try:
            proc = jobs.spawn_detached(cmd, cfg.hashcat_dir, log_file)
        except FileNotFoundError:
            return {"ok": False, "error": "hashcat not found: %s" % cfg.hashcat_exe}
        except Exception as exc:
            return {"ok": False, "error": "failed to start hashcat: %s" % exc}

        state = {
            "job_id": job_id, "pid": proc.pid, "hash_mode": int(hash_mode),
            "attack_mode": attack_mode, "hash_file": hash_file, "out_file": out_file,
            "log_file": log_file, "potfile": cfg.potfile, "cmd": cmd,
            "started": time.time(), "stopped": False,
        }
        jobs.write_state(cfg, job_id, state)
        return {"ok": True, "job_id": job_id, "pid": proc.pid, "cmd": cmd, "notes": notes}

    def t_status(self, args):
        cfg = self.config
        job_id = args.get("job_id")
        state = jobs.read_state(cfg, job_id)
        if not state:
            return {"ok": False, "error": "unknown job_id: %s" % job_id}
        alive = jobs.process_alive(state.get("pid")) and not state.get("stopped")
        log_text = jobs.read_text(state.get("log_file"), tail=20000)
        status = jobs.parse_status_json(log_text)
        result = {
            "ok": True, "job_id": job_id,
            "state": "running" if alive else "finished",
            "elapsed_s": round(time.time() - state.get("started", time.time()), 1),
            "cracked": jobs.cracked_lines(state),
        }
        if status:
            progress = status.get("progress") or [0, 0]
            current, total = (progress + [0, 0])[:2]
            recovered = status.get("recovered_hashes") or [0, 0]
            result.update({
                "status_code": status.get("status"),
                "progress": [current, total],
                "percent": round(100.0 * current / total, 2) if total else None,
                "recovered": [recovered[0], recovered[1]] if len(recovered) == 2 else recovered,
                "devices": [
                    {"name": dev.get("device_name"), "speed_hps": dev.get("speed"),
                     "temp": dev.get("temp"), "util": dev.get("util")}
                    for dev in (status.get("devices") or [])
                ],
            })
        if not alive:
            result["log_tail"] = log_text[-1500:]
        return result

    def t_result(self, args):
        cfg = self.config
        job_id = args.get("job_id")
        state = jobs.read_state(cfg, job_id)
        if not state:
            return {"ok": False, "error": "unknown job_id: %s" % job_id}
        cracked = jobs.cracked_lines(state)
        _rc, out = self._run_hc(
            ["-m", str(state["hash_mode"]), state["hash_file"],
             "--potfile-path", cfg.potfile, "--show"], timeout=120)
        shown = [line.strip() for line in out.splitlines() if line.strip() and ":" in line]
        return {"ok": True, "job_id": job_id, "cracked": cracked, "show": shown}

    def t_stop(self, args):
        cfg = self.config
        job_id = args.get("job_id")
        state = jobs.read_state(cfg, job_id)
        if not state:
            return {"ok": False, "error": "unknown job_id: %s" % job_id}
        if not jobs.process_alive(state.get("pid")):
            state["stopped"] = True
            jobs.write_state(cfg, job_id, state)
            return {"ok": True, "already_finished": True}
        ok, message = jobs.terminate_process(state.get("pid"))
        if not ok:
            return {"ok": False, "error": message}
        state["stopped"] = True
        jobs.write_state(cfg, job_id, state)
        return {"ok": True, "stopped": True}

    def t_potfile(self, args):
        cfg = self.config
        limit = int(args.get("limit", 200))
        if not os.path.isfile(cfg.potfile):
            return {"ok": True, "count": 0, "entries": []}
        entries = [line.rstrip("\n") for line in jobs.read_text(cfg.potfile).splitlines() if line.strip()]
        if args.get("hash_mode") is not None:
            _rc, out = self._run_hc(
                ["-m", str(int(args["hash_mode"])), "--show", "--potfile-path", cfg.potfile],
                timeout=60)
            entries = [line.strip() for line in out.splitlines() if line.strip() and ":" in line]
        return {"ok": True, "count": len(entries), "entries": entries[-limit:]}

    # -- protocol -----------------------------------------------------------
    def _initialize(self, params):
        client_version = params.get("protocolVersion")
        version = client_version if client_version in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
        return {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": INSTRUCTIONS,
        }

    def _tools_call(self, mid, params):
        name = params.get("name")
        arguments = params.get("arguments") or {}
        method = TOOL_METHODS.get(name)
        handler = getattr(self, method, None) if method else None
        if handler is None:
            return _rpc(mid, {"content": [{"type": "text", "text": "unknown tool: %s" % name}],
                              "isError": True})
        try:
            result = handler(arguments)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            is_error = isinstance(result, dict) and result.get("ok") is False
        except Exception as exc:
            text = "tool error: %s: %s" % (type(exc).__name__, exc)
            is_error = True
        return _rpc(mid, {"content": [{"type": "text", "text": text}], "isError": is_error})

    def handle(self, msg):
        """Map one JSON-RPC message to a response dict (or None for notifications)."""
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            return _rpc(mid, self._initialize(params))
        if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
            return None
        if method == "ping":
            return _rpc(mid, {})
        if method == "tools/list":
            return _rpc(mid, {"tools": TOOLS})
        if method == "tools/call":
            return self._tools_call(mid, params)
        if mid is not None:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "method not found: %s" % method}}
        return None

    def run(self):
        _configure_stdio()
        self.config.ensure_dirs()
        log("started; version=%s hashcat=%s data=%s"
            % (__version__, self.config.hashcat_exe, self.config.data_dir))
        for raw in _iter_messages(sys.stdin.buffer):
            try:
                msg = json.loads(raw)
            except Exception as exc:
                log("bad json:", exc)
                continue
            try:
                response = self.handle(msg)
            except Exception as exc:
                log("handler crash:", exc)
                mid = msg.get("id") if isinstance(msg, dict) else None
                response = ({"jsonrpc": "2.0", "id": mid,
                             "error": {"code": -32603, "message": str(exc)}}
                            if mid is not None else None)
            if response is not None:
                _send(response)


def _rpc(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _configure_stdio():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _iter_messages(stream):
    """Yield JSON strings from a binary stream.

    Accepts both newline-delimited JSON-RPC (current MCP stdio transport) and
    legacy ``Content-Length`` framing, so it fits a wider range of clients.
    """
    while True:
        line = stream.readline()
        if not line:
            return
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(b"content-length:"):
            try:
                length = int(stripped.split(b":", 1)[1].strip())
            except Exception:
                return
            while True:
                header = stream.readline()
                if header in (b"", b"\r\n", b"\n"):
                    break
            body = stream.read(length)
            if not body:
                return
            yield body.decode("utf-8", "replace")
        else:
            yield stripped.decode("utf-8", "replace")


def _send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv=None):
    server = HashcatServer(load_config(argv))
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    return 0
