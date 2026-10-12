"""Job lifecycle and portable process management for hashcat-mcp.

The three process helpers -- :func:`process_alive`, :func:`terminate_process`
and :func:`spawn_detached` -- hide the platform differences:

* Windows uses ``taskkill`` and ``CREATE_*`` process-creation flags.
* POSIX uses ``os.kill`` / process groups.
* If a platform-specific API is unavailable the code degrades to a generic
  ``os.kill``-based path instead of raising.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
from typing import List, Optional, Tuple

from . import log

# Windows process-creation flags (only referenced on Windows).
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

_BATCH_EXTENSIONS = (".bat", ".cmd")


# ---------------------------------------------------------------------------
# Portable process helpers
# ---------------------------------------------------------------------------

def process_alive(pid) -> bool:
    """Return True if *pid* is still running. Never raises."""
    if not pid:
        return False
    if os.name == "nt":
        alive = _windows_process_alive(pid)
        if alive is not None:
            return alive
        # Windows API unavailable -> fall through to the generic probe.
    return _generic_process_alive(pid)


def _windows_process_alive(pid):
    """Return True/False, or None if the Windows API cannot be used."""
    try:
        import ctypes
    except Exception:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
    except Exception:
        return None
    try:
        handle = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def _generic_process_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    except Exception:
        return False
    return True


def terminate_process(pid, timeout: int = 30) -> Tuple[bool, Optional[str]]:
    """Stop a process and its children. Returns ``(ok, message)``."""
    if not pid:
        return False, "no pid"
    if os.name == "nt":
        result = _windows_terminate(pid, timeout)
        if result is not None:
            return result
        # taskkill / Windows API missing -> degrade to the generic path.
    return _generic_terminate(pid)


def _windows_terminate(pid, timeout):
    """Use taskkill on Windows; return None to request the generic fallback."""
    system_root = os.environ.get("SystemRoot") or os.environ.get("windir") or ""
    taskkill = os.path.join(system_root, "System32", "taskkill.exe") if system_root else ""
    if not taskkill or not os.path.isfile(taskkill):
        taskkill = shutil.which("taskkill") or ""
    if not taskkill:
        return None
    try:
        subprocess.run(
            [taskkill, "/PID", str(int(pid)), "/T", "/F"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=timeout,
        )
        return True, None
    except FileNotFoundError:
        return None
    except Exception as exc:  # pragma: no cover - platform specific
        return False, str(exc)


def _generic_terminate(pid) -> Tuple[bool, Optional[str]]:
    """Signal a process, preferring its process group when available."""
    try:
        int_pid = int(pid)
    except (TypeError, ValueError):
        return False, "invalid pid"
    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
        try:
            os.killpg(os.getpgid(int_pid), signal.SIGTERM)
            return True, None
        except ProcessLookupError:
            return True, "already finished"
        except Exception:
            pass  # e.g. not a group leader; fall back to a single kill.
    try:
        os.kill(int_pid, signal.SIGTERM)
        return True, None
    except ProcessLookupError:
        return True, "already finished"
    except Exception as exc:
        return False, str(exc)


def spawn_detached(cmd: List[str], cwd: Optional[str], log_path: str):
    """Start *cmd* in the background, capturing stdout+stderr to *log_path*.

    Returns the :class:`subprocess.Popen` object.
    """
    log_fh = open(log_path, "wb")
    kwargs = dict(cwd=cwd, stdin=subprocess.DEVNULL,
                  stdout=log_fh, stderr=subprocess.STDOUT)
    try:
        if os.name == "nt":
            flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
            # A real executable can be fully detached. Batch wrappers
            # (.bat/.cmd) lose their inherited stdio handles under
            # DETACHED_PROCESS, so they keep the console-less group instead.
            if not cmd[0].lower().endswith(_BATCH_EXTENSIONS):
                flags |= DETACHED_PROCESS
            kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(cmd, **kwargs)
    finally:
        log_fh.close()


# ---------------------------------------------------------------------------
# Job state
# ---------------------------------------------------------------------------

def new_job_id() -> str:
    return "job_" + time.strftime("%Y%m%d_%H%M%S") + "_" + str(int(time.time() * 1000) % 1000)


def job_dir(cfg, job_id: str) -> str:
    return os.path.join(cfg.jobs_dir, job_id)


def read_text(path: Optional[str], tail: Optional[int] = None) -> str:
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            data = handle.read()
    except Exception as exc:
        return "[hashcat-mcp] read error: %s" % exc
    return data[-tail:] if tail else data


def read_state(cfg, job_id: Optional[str]):
    if not job_id:
        return None
    path = os.path.join(job_dir(cfg, job_id), "state.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def write_state(cfg, job_id: str, state: dict) -> None:
    directory = job_dir(cfg, job_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "state.json"), "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def parse_status_json(log_text: str):
    """Return the last ``--status-json`` object found in hashcat's output."""
    best = None
    for line in log_text.splitlines():
        stripped = line.strip().strip("\r")
        if stripped.startswith("{") and "session" in stripped:
            try:
                best = json.loads(stripped)
            except Exception:
                pass
    return best


def cracked_lines(state: dict) -> List[str]:
    lines: List[str] = []
    out_file = state.get("out_file")
    if out_file and os.path.isfile(out_file):
        for line in read_text(out_file).splitlines():
            if line.strip() and ":" in line:
                lines.append(line.strip())
    return lines
