"""onepass: each defect the tests claim to catch, planted in the code as it would be written, one at a
time; both test files run; restored. Run from OspreyFlow_Core, OSPREY_TEST_CADDY set, ports pinned closed."""
import subprocess, sys
from pathlib import Path

KEY, SITE = Path("harness/access_key.py"), Path("harness/site.py")
PLANTS = [
    ("the pass host-only again (no Domain)", KEY, '"{cookie}; Domain={{args[0]}}; Path=/; \'', '"{cookie}; Path=/; \''),
    ("the pass for the domain above the deployment", SITE,
     'f"\\t\\timport osprey_access_pass_set {host}",', 'f"\\t\\timport osprey_access_pass_set {host.split(\'.\', 1)[1]}",'),
    ("a key file from before the amendment refused", KEY,
     "    if text not in (snippet(user, hashed, token), _before_amendment_42(user, hashed, token)):",
     "    if text != snippet(user, hashed, token):"),
    ("a key file from before the amendment carried unchanged", KEY,
     "                replace_whole(staged, text, mode=0o600)", "                shutil.copy2(source, staged)"),
    ("the pass given without the key (any request on the base)", SITE,
     '        "\\t@osprey_answered {",\n        *unasked,\n        *basic,', '        "\\t@osprey_answered {",\n        *basic,'),
]
TESTS = ["../OspreyFlow_Build/tests/harness/test_access_key.py", "../OspreyFlow_Build/tests/harness/test_access_key_proxy.py"]
for what, path, old, new in PLANTS:
    original = path.read_text(encoding="utf-8")
    assert original.count(old) == 1, f"plant not found: {what}"
    path.write_text(original.replace(old, new), encoding="utf-8")
    try:
        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TESTS], capture_output=True, text=True)
        tail = [l for l in done.stdout.splitlines() if l.startswith("FAILED") or " passed" in l or " failed" in l]
        print(f"## {what}: {'RED' if done.returncode else 'GREEN (the tests missed it)'}")
        for line in tail:
            print("  " + line.split(" - ")[0])
    finally:
        path.write_text(original, encoding="utf-8")
