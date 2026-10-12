"""Tool behaviour tests driven by the fake hashcat stub (no GPU)."""

import json
import time

from hashcat_mcp.config import Config
from hashcat_mcp.server import HashcatServer

HASH = "8743b52063cd84097a65d1633f5c74f5"


def call(server, name, arguments=None):
    response = server.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    })
    payload = json.loads(response["result"]["content"][0]["text"])
    return payload, response


def _wait_cracked(server, job_id, timeout=15):
    deadline = time.time() + timeout
    payload = None
    while time.time() < deadline:
        payload, _ = call(server, "hashcat_status", {"job_id": job_id})
        if payload.get("cracked"):
            return payload
        time.sleep(0.2)
    return payload


def test_identify(server):
    payload, _ = call(server, "hashcat_identify", {"hash": HASH})
    assert payload["ok"]
    modes = {match["mode"] for match in payload["matches"]}
    assert {0, 1000} <= modes


def test_devices(server):
    payload, _ = call(server, "hashcat_devices", {})
    assert payload["ok"]
    assert "Fake" in payload["output"]


def test_wordlists(tmp_path):
    wordlists = tmp_path / "wordlists"
    wordlists.mkdir()
    (wordlists / "rockyou.txt").write_text("a\n", encoding="utf-8")
    (wordlists / "other.txt").write_text("b\n", encoding="utf-8")
    cfg = Config(hashcat_exe="__none__", data_dir=str(tmp_path / "data"),
                 wordlist_dirs=[str(wordlists)])
    payload, _ = call(HashcatServer(cfg), "hashcat_wordlists", {"filter": "rock"})
    assert payload["ok"]
    assert payload["total"] == 1
    assert payload["wordlists"][0]["name"] == "rockyou.txt"


def test_merge_rockyou(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    (parts / "rockyou-part1.txt").write_bytes(b"one\n")
    (parts / "rockyou-part2.txt").write_bytes(b"two\n")
    cfg = Config(hashcat_exe="__none__", data_dir=str(tmp_path / "data"))
    payload, _ = call(HashcatServer(cfg), "hashcat_merge_rockyou",
                      {"source_dir": str(parts)})
    assert payload["ok"]
    with open(payload["path"], "rb") as handle:
        assert handle.read() == b"one\ntwo\n"


def test_start_status_result(server, tmp_path):
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("password\n", encoding="utf-8")
    started, _ = call(server, "hashcat_start",
                      {"hash": HASH, "hash_mode": 0, "wordlist": str(wordlist)})
    assert started["ok"], started
    job_id = started["job_id"]

    _wait_cracked(server, job_id)
    status, _ = call(server, "hashcat_status", {"job_id": job_id})
    assert status["ok"]
    assert status["state"] in ("running", "finished")
    assert any("hello" in entry for entry in status["cracked"])

    result, _ = call(server, "hashcat_result", {"job_id": job_id})
    assert result["ok"]
    assert any("hello" in entry for entry in result["cracked"])
    assert any("hello" in entry for entry in result["show"])


def test_stop_running_job(server, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_HASHCAT_SLEEP", "30")
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("password\n", encoding="utf-8")
    started, _ = call(server, "hashcat_start",
                      {"hash": HASH, "hash_mode": 0, "wordlist": str(wordlist)})
    assert started["ok"], started
    job_id = started["job_id"]
    time.sleep(0.5)

    running, _ = call(server, "hashcat_status", {"job_id": job_id})
    assert running["state"] == "running"

    stopped, _ = call(server, "hashcat_stop", {"job_id": job_id})
    assert stopped["ok"]
    time.sleep(0.5)
    finished, _ = call(server, "hashcat_status", {"job_id": job_id})
    assert finished["state"] == "finished"


def test_hashcat_missing(tmp_path):
    cfg = Config(hashcat_exe=None, data_dir=str(tmp_path / "data"))
    server = HashcatServer(cfg)
    started, _ = call(server, "hashcat_start",
                      {"hash": HASH, "hash_mode": 0, "wordlist": "whatever"})
    assert started["ok"] is False
    assert "hashcat" in started["error"].lower()

    identified, _ = call(server, "hashcat_identify", {"hash": HASH})
    assert identified["ok"] is False

    devices, _ = call(server, "hashcat_devices", {})
    assert devices["ok"] is False


def test_unknown_job(server):
    for name in ("hashcat_status", "hashcat_result", "hashcat_stop"):
        payload, _ = call(server, name, {"job_id": "does-not-exist"})
        assert payload["ok"] is False
        assert "unknown job_id" in payload["error"]


def test_potfile(server, tmp_path):
    wordlist = tmp_path / "words.txt"
    wordlist.write_text("password\n", encoding="utf-8")
    started, _ = call(server, "hashcat_start",
                      {"hash": HASH, "hash_mode": 0, "wordlist": str(wordlist)})
    _wait_cracked(server, started["job_id"])
    payload, _ = call(server, "hashcat_potfile", {})
    assert payload["ok"]
    assert payload["count"] >= 1
