#!/usr/bin/env python3
"""A tiny stand-in for hashcat used by the test-suite.

It never touches a GPU. Behaviour is driven by the arguments the server builds:

* ``--identify <file>`` -> prints a couple of ``mode | name | ...`` rows
* ``-I``                -> prints a fake device listing
* ``--show``            -> prints the potfile contents (or a fixed record)
* anything else         -> a cracking job: writes the outfile, appends to the
                           potfile, emits a ``--status-json`` line and then
                           optionally sleeps (``FAKE_HASHCAT_SLEEP`` seconds).
"""

import json
import os
import sys
import time

HASH = "8743b52063cd84097a65d1633f5c74f5"
PLAIN = "hello"


def _take(argv, flag):
    try:
        return argv[argv.index(flag) + 1]
    except (ValueError, IndexError):
        return None


def main():
    argv = sys.argv[1:]

    if "--identify" in argv:
        print("0 | MD5 | Raw Hash")
        print("1000 | NTLM | Raw Hash")
        return 0

    if "-I" in argv or "--backend-info" in argv:
        print("hashcat (v0.0.0) fake backend")
        print("OpenCL Platform #1: Fake Platform")
        print("  Device #1: Fake CPU 1/1")
        return 0

    if "--show" in argv:
        pot = _take(argv, "--potfile-path")
        if pot and os.path.isfile(pot):
            with open(pot, encoding="utf-8") as handle:
                sys.stdout.write(handle.read())
        else:
            print("%s:%s" % (HASH, PLAIN))
        return 0

    record = "%s:%s" % (HASH, PLAIN)
    out_file = _take(argv, "-o")
    pot = _take(argv, "--potfile-path")
    if out_file:
        with open(out_file, "w", encoding="utf-8") as handle:
            handle.write(record + "\n")
    if pot:
        with open(pot, "a", encoding="utf-8") as handle:
            handle.write(record + "\n")

    print(json.dumps({
        "session": "fake",
        "status": 5,
        "progress": [1, 1],
        "recovered_hashes": [1, 1],
        "devices": [{"device_name": "Fake GPU", "speed": 1234567, "temp": 42, "util": 99}],
    }))
    sys.stdout.flush()

    sleep_for = float(os.environ.get("FAKE_HASHCAT_SLEEP", "0") or 0)
    if sleep_for > 0:
        time.sleep(sleep_for)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
