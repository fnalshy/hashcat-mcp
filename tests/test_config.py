"""Configuration and path-resolution tests (no hashcat required)."""

import json
import pathlib
import re

from hashcat_mcp.config import Config, default_data_dir, find_hashcat, load_config

PKG_DIR = pathlib.Path(__file__).resolve().parent.parent / "hashcat_mcp"


def test_no_hardcoded_drive_paths():
    """The package must not contain any Windows drive-letter literal."""
    pattern = re.compile(r"[A-Za-z]:\\")
    offenders = []
    for path in PKG_DIR.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append("%s:%d" % (path.name, number))
    assert not offenders, offenders


def test_default_data_dir_is_user_writable():
    resolved = default_data_dir(env={})
    assert "hashcat-mcp" in resolved


def test_env_wins_over_explicit(tmp_path):
    env_exe = tmp_path / "env_hashcat"
    cfg_exe = tmp_path / "cfg_hashcat"
    env_exe.write_text("")
    cfg_exe.write_text("")
    found = find_hashcat(explicit=str(cfg_exe), env={"HASHCAT_EXE": str(env_exe)})
    assert found == str(env_exe)


def test_explicit_used_when_no_env(tmp_path):
    cfg_exe = tmp_path / "cfg_hashcat"
    cfg_exe.write_text("")
    found = find_hashcat(explicit=str(cfg_exe), env={})
    assert found == str(cfg_exe)


def test_hashcat_dir_probed_when_missing(tmp_path):
    hc_dir = tmp_path / "hc"
    hc_dir.mkdir()
    (hc_dir / "hashcat").write_text("")
    (hc_dir / "hashcat.exe").write_text("")
    found = find_hashcat(hashcat_dir=str(hc_dir), env={})
    assert found in (str(hc_dir / "hashcat"), str(hc_dir / "hashcat.exe"))


def test_config_file_then_cli_precedence(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"data_dir": str(tmp_path / "fromfile")}),
                           encoding="utf-8")
    from_file = load_config(argv=["--config", str(config_file)], env={})
    assert from_file.data_dir == str(tmp_path / "fromfile")

    override = load_config(
        argv=["--config", str(config_file), "--data-dir", str(tmp_path / "cli")], env={})
    assert override.data_dir == str(tmp_path / "cli")


def test_env_data_dir_used(tmp_path):
    loaded = load_config(argv=[], env={"HASHCAT_MCP_DATA": str(tmp_path / "envdata")})
    assert loaded.data_dir == str(tmp_path / "envdata")


def test_jobs_dir_and_potfile_paths(tmp_path):
    cfg = Config(data_dir=str(tmp_path / "d"))
    assert cfg.jobs_dir == str(tmp_path / "d" / "jobs")
    assert cfg.potfile == str(tmp_path / "d" / "hashcat.potfile")
