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
     "        unasked.append(f\"\\t\\tnot expression `{{http.request.orig_uri.path}} in [{listed}]`\")",
     "        unasked.append(\"\\t\\tnot path /realms/osprey/*\")"),
    ("the open answers matched on the cleaned path", SITE,
     "        unasked.append(f\"\\t\\tnot expression `{{http.request.orig_uri.path}} in [{listed}]`\")",
     "        unasked.append(f\"\\t\\tnot path {' '.join(OPEN_ON_THE_IDENTITY_PROVIDER)}\")"),
    ("Basic left on the request when its scheme is lower case", SITE,
     '    basic = ["\\t\\theader_regexp Authorization (?i)^basic\\\\s"]',
     '    basic = [\'\\t\\theader Authorization "Basic *"\']'),
    ("any OPTIONS let in, not only a CORS preflight", SITE,
     '        "\\t\\t\\theader Access-Control-Request-Method *",\n', ""),
    ("a CORS preflight asked for the key", SITE,
     '    unasked = [\n        "\\t\\tnot {",\n        "\\t\\t\\tmethod OPTIONS",\n        "\\t\\t\\theader Access-Control-Request-Method *",\n        "\\t\\t}",\n    ]',
     "    unasked = []"),
    ("no noindex", SITE, "        NOINDEX,\n        # Every answer", "        # Every answer"),
    ("a forged pass let in: any value of the cookie", SITE,
     '"\\t\\t\\timport osprey_access_pass", "\\t\\t}"]', '"\\t\\t\\theader Cookie *osprey_pass=*", "\\t\\t}"]'),
    ("the pass sent to every subdomain of the deployment's domain", KEY,
     "f'\\theader @osprey_answered +Set-Cookie \"{cookie}; Path=/;",
     "f'\\theader @osprey_answered +Set-Cookie \"{cookie}; Domain=gate.localhost; Path=/;"),
    ("no log of the attempts", SITE, '        "\\tlog",\n', ""),
    ("a refusal that says why, in its body", SITE, '        "\\t\\tbasic_auth @osprey_locked bcrypt OspreyFlow {",',
     '        "\\t\\thandle_errors {", "\\t\\t\\trespond \\"refused: no pass and no key\\" 401", "\\t\\t}",\n        "\\t\\tbasic_auth @osprey_locked bcrypt OspreyFlow {",'),
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
