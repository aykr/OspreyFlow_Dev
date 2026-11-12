"""gate-b B: each defect the real-proxy test claims to catch, planted in the code under test as it
would be written, one at a time; the test file run against each; the code restored. Run from
OspreyFlow_Core with OSPREY_TEST_CADDY set and the ports pinned closed."""

import subprocess
import sys
from pathlib import Path

SITE = Path("harness/site.py")
KEY = Path("harness/access_key.py")
PLANTS = [
    ("no gate: the key's handlers never added", SITE,
     "        if gate:\n            handlers = _behind_the_key(", "        if False:\n            handlers = _behind_the_key("),
    ("the pass given for any Basic, checked or not", KEY,
     "header @osprey_answered +Set-Cookie", "header @osprey_basic +Set-Cookie"),
    ("the key left on the request to the service behind", SITE,
     '        "\\t\\trequest_header @osprey_basic -Authorization",\n', ""),
    ("the pass ignored", SITE,
     '    unasked += ["\\t\\tnot {", "\\t\\t\\timport osprey_access_pass", "\\t\\t}"]\n', ""),
    ("the whole realm left open on the identity provider", SITE,
     "        unasked.append(f\"\\t\\tnot path {' '.join(OPEN_ON_THE_IDENTITY_PROVIDER)}\")",
     "        unasked.append(\"\\t\\tnot path /realms/osprey/*\")"),
    ("a CORS preflight asked for the key", SITE,
     '    unasked = ["\\t\\tnot method OPTIONS"]', "    unasked = []"),
    ("no noindex", SITE, "        NOINDEX,\n        \"\\t@osprey_locked {\",", "        \"\\t@osprey_locked {\","),
]
TEST = "../OspreyFlow_Build/tests/harness/test_access_key_proxy.py"
for what, path, old, new in PLANTS:
    original = path.read_text(encoding="utf-8")
    assert original.count(old) == 1, f"plant not found: {what}"
    path.write_text(original.replace(old, new), encoding="utf-8")
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST],
                              capture_output=True, text=True)
        tail = [l for l in done.stdout.splitlines() if l.startswith("FAILED") or " passed" in l or " failed" in l]
        print(f"## {what}: {'RED' if done.returncode else 'GREEN (the test missed it)'}")
        for line in tail:
            print("  " + line.split(" - ")[0])
    finally:
        path.write_text(original, encoding="utf-8")
