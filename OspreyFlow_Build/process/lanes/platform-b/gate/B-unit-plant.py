"""gate-b B: each defect the helper's, preflight's and the host pass's tests claim to catch, planted in
the code as it would be written, one at a time; `test_access_key.py` run against each; restored. Run
from OspreyFlow_Core with the ports pinned closed."""

import subprocess
import sys
from pathlib import Path

KEY = Path("harness/access_key.py")
CHECK = Path("harness/preflight/access_key.py")
SITE = Path("harness/site.py")
SCHEMA = Path("packages/schemas/deployment.py")
PLANTS = [
    ("the key file written readable by every account (644)", KEY,
     "os.fchmod(handle.fileno(), 0o600)", "os.fchmod(handle.fileno(), 0o644)"),
    ("the helper says the hash it wrote", KEY,
     '        f"The key\'s hash is written to {target}', '        f"The key\'s hash {hashed} is written to {target}'),
    ("the two answers never compared", KEY, "    if first != again:\n", "    if False:\n"),
    ("a short key accepted", KEY, "    if len(first.strip()) < SHORTEST:", "    if len(first.strip()) < 1:"),
    ("a file others may read accepted", KEY, "    if mode & 0o077:", "    if False:"),
    ("preflight quotes the file it refuses", CHECK,
     "        return failed(NAME, what_is_wrong=str(refused), what_to_do=_SET)",
     "        return failed(NAME, what_is_wrong=f\"{refused}: {path.read_text()}\", what_to_do=_SET)"),
    ("the pass carried to every host", SITE,
     "        directory = _PASSES.get(name)\n", "        directory = next(iter(_PASSES.values()), None)\n"),
    ("the key allowed on any profile", SCHEMA,
     "        if self.network.access_key and self.profile is not Profile.SMALL:",
     "        if False:"),
    ("a set key never carried into place", KEY,
     "    for source in (out_dir / PENDING_FILE, out_dir / ACCESS_KEY_FILE):",
     "    for source in (out_dir / ACCESS_KEY_FILE,):"),
]
TEST = "../OspreyFlow_Build/tests/harness/test_access_key.py"
for what, path, old, new in PLANTS:
    original = path.read_text(encoding="utf-8")
    assert original.count(old) == 1, f"plant not found: {what}"
    path.write_text(original.replace(old, new), encoding="utf-8")
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST],
                              capture_output=True, text=True)
        tail = [l for l in done.stdout.splitlines() if l.startswith(("FAILED", "ERROR")) or " passed" in l or " failed" in l]
        print(f"## {what}: {'RED' if done.returncode else 'GREEN (the test missed it)'}")
        for line in tail:
            print("  " + line.split(" - ")[0])
    finally:
        path.write_text(original, encoding="utf-8")
