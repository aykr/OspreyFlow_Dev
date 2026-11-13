"""Each refusal branch removed in turn, at its own site; the domain and kind tests run; restored."""
import pathlib, subprocess, sys
repo = pathlib.Path(sys.argv[1]); core = repo / "OspreyFlow_Core"
FIX = repo / "OspreyFlow_Build/tests/fixtures/cloud_platform/s3_standin.py"
PROFILE = core / "harness/cloud_platform/profile.yaml"
PLANTS = [
    ("role (the domain's access policy)", FIX, '        if who not in domain["roles"]:', '        if False:'),
    ("service (signed for another service)", FIX, '        if service_of and service != service_of:', '        if False:'),
    ("region", FIX, '        if region != self.region:', '        if False:'),
    ("session token", FIX, '            if headers.get("x-amz-security-token") != principal.token:', '            if False:'),
    ("unsigned (the domain's own refusal)", FIX, '        if not headers.get("authorization"):\n            refuse(', '        if False:\n            refuse('),
    ("skew (five minutes for es)", FIX, '        if service == "es" and abs(self.clock() - when) > DOMAIN_SKEW:', '        if False:'),
    ("size (10 MiB)", FIX, '        if len(raw_body) > DOMAIN_MAX_BODY:', '        if False:'),
    ("egress (9200 among the managed ports)", PROFILE, '  managed_ports: [5432, 6379]', '  managed_ports: [5432, 6379, 9200]'),
]
tests = ["../OspreyFlow_Build/tests/test_r1_opensearch_standin.py", "../OspreyFlow_Build/tests/test_r1_kind_standins.py"]
env = {"PATH": "/usr/bin:/bin", "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "PYTHONPATH": ".:packages:../OspreyFlow_Build", "HOME": str(pathlib.Path.home())}
for what, path, old, new in PLANTS:
    text = path.read_text()
    assert text.count(old) == 1, (what, old)
    path.write_text(text.replace(old, new))
    try:
        done = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p", "no:cacheprovider", "-q", "-rf", *tests],
                              cwd=core, env=env, capture_output=True, text=True)
    finally:
        path.write_text(text)
    lines = [l.split(" - ")[0].replace("../OspreyFlow_Build/", "") for l in done.stdout.splitlines() if l.startswith("FAILED") or " passed" in l or " failed" in l]
    print(f"Plant: {what}:")
    print("\n".join(lines) or done.stdout[-500:])
    print()
