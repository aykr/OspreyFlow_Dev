"""The meter's own check (rule 15): planted tests of the shapes the live suites take, run through pytest with
``-p t1_meter``, and what the meter wrote compared against what each one did. Run it as
``.venv/bin/python ../OspreyFlow_Build/process/lanes/admin/t1/check_t1_meter.py`` from OspreyFlow_Core; it exits
non-zero, naming the miss, when the meter fails to see a sleep, an asyncio sleep or a store's connection.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent

PLANTED = '''
import asyncio, socket, time

def test_sleeps():
    time.sleep(0.2)

def test_polls_with_asyncio():
    async def poll():
        for _ in range(4):
            await asyncio.sleep(0.05)
    asyncio.run(poll())

def test_reaches_a_store():
    async def reach():
        r, w = await asyncio.open_connection("127.0.0.1", {port})
        w.close()
    asyncio.run(reach())

def test_needs_nothing():
    assert 1 + 1 == 2
'''


def main() -> int:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    threading.Thread(target=lambda: [listener.accept() for _ in range(4)], daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "test_planted.py").write_text(PLANTED.replace("{port}", str(port)))
        out = Path(tmp) / "meter.jsonl"
        env = {**os.environ, "OSPREY_T1_METER": str(out), "PYTHONPATH": str(HERE)}
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "t1_meter", "-p", "no:randomly", "-p", "no:cacheprovider",
                        str(Path(tmp) / "test_planted.py")], cwd=tmp, env=env, check=True)
        got = {json.loads(l)["nodeid"].split("::")[1]: json.loads(l) for l in out.read_text().splitlines()}
    misses = []
    if not 0.18 <= got["test_sleeps"]["sleep_s"] <= 0.5:
        misses.append(f"time.sleep not seen: {got['test_sleeps']}")
    if got["test_polls_with_asyncio"]["sleeps"] != 4:
        misses.append(f"asyncio.sleep not seen: {got['test_polls_with_asyncio']}")
    if port not in got["test_reaches_a_store"]["ports"]:
        misses.append(f"the store's connection not seen: {got['test_reaches_a_store']}")
    if got["test_needs_nothing"]["ports"] or got["test_needs_nothing"]["sleeps"]:
        misses.append(f"a test that did nothing was charged: {got['test_needs_nothing']}")
    if set(got["test_sleeps"]["phases"]) != {"setup", "call", "teardown"}:
        misses.append(f"phases missing: {got['test_sleeps']}")
    for m in misses:
        print("MISS:", m)
    print("t1_meter check:", "red" if misses else "green")
    return 1 if misses else 0


if __name__ == "__main__":
    raise SystemExit(main())
