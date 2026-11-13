"""Starts the real proxy as test_access_key_proxy.py does (Caddy 2.11.4, the rendered Caddyfile, the
helper's key file, a stand-in behind each name), runs chromium_onepass.mjs against it, stops it."""
import subprocess, sys, tempfile
from pathlib import Path
import tests.harness.test_access_key_proxy as t
from harness import access_key

folder = Path(tempfile.mkdtemp())
stand_in = t._stand_in()
port, plain = t._free_port(), t._free_port()
caddyfile = t._caddyfile(folder, port, plain, stand_in.server_address[1])
access_key.set_key(folder, user="demo", ask=lambda _p: t.KEY, hasher=t._hash)
access_key.carry_into(folder, folder)
process = t._run(caddyfile, port)
try:
    here = Path(__file__).parent
    done = subprocess.run(["node", str(here / "chromium_onepass.mjs"), str(port), t.HOST, "demo", t.KEY],
                          capture_output=True, text=True, timeout=120)
    print(done.stdout + done.stderr)
finally:
    process.kill()
    stand_in.shutdown()
