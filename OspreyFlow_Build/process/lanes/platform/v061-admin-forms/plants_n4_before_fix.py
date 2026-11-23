"""Apply one plant to services/api/model_admin.py (argument: name), run the N4 cases, restore the file."""
import subprocess, sys, pathlib
root = pathlib.Path("/Users/ayankar/dev/osprey-wt/slice-AD1a")
f = root / "OspreyFlow_Core/services/api/model_admin.py"
orig = f.read_text()
name = sys.argv[1]
def sub(a, b):
    assert a in orig, a
    return orig.replace(a, b, 1)
if name == "PN4k_before":   # current code: key_name logged where the listing is read
    new = sub('                token = str(dict(row).get("token") or "")\n',
              '                token = str(dict(row).get("token") or "")\n                log.info("listed %s", dict(row).get("key_name"))\n')
elif name == "PN4s_before":  # current code: the stale key's last four put into the words of a refusal
    new = sub('                    stale.append(token)\n',
              '                    stale.append(token)\n                    stale_name = str(dict(row).get("key_name") or "")\n')
    new = new.replace('                raise self._refused(resp, "an old engine key\'s removal")',
              '                raise ModelAdminRefused("refused " + stale_name[-4:])', 1)
else:
    raise SystemExit("unknown plant")
f.write_text(new)
try:
    r = subprocess.run("cd %s/OspreyFlow_Core && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=$HOME/dev/osprey-acceptance/AD1a uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider --tb=no -rfp ../OspreyFlow_Build/tests/services/api/test_model_key_paths.py -k n4 2>&1 | grep -E '^(FAILED|PASSED)|passed|failed'" % root, shell=True, capture_output=True, text=True)
    print(name); print(r.stdout)
finally:
    f.write_text(orig)
