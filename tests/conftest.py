"""Shared fixtures for the hashcat-mcp test-suite."""

import os
import pathlib
import sys

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hashcat_mcp.config import Config  # noqa: E402
from hashcat_mcp.server import HashcatServer  # noqa: E402


def make_launcher(directory):
    """Copy the stub and wrap it in a runnable launcher for this OS."""
    stub_src = TESTS_DIR / "fake_hashcat.py"
    stub_dst = pathlib.Path(directory) / "fake_hashcat.py"
    stub_dst.write_text(stub_src.read_text(encoding="utf-8"), encoding="utf-8")
    if os.name == "nt":
        launcher = pathlib.Path(directory) / "fake_hashcat.cmd"
        launcher.write_text('@echo off\r\n"%s" "%s" %%*\r\n' % (sys.executable, stub_dst),
                            encoding="utf-8")
    else:
        launcher = pathlib.Path(directory) / "fake_hashcat"
        launcher.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, stub_dst),
                            encoding="utf-8")
        launcher.chmod(0o755)
    return launcher


@pytest.fixture
def fake_hashcat(tmp_path):
    return make_launcher(tmp_path)


@pytest.fixture
def config(tmp_path, fake_hashcat):
    return Config(hashcat_exe=str(fake_hashcat), data_dir=str(tmp_path / "data"))


@pytest.fixture
def server(config):
    return HashcatServer(config)
