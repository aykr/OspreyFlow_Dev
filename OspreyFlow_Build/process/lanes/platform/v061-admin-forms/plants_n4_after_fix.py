import subprocess, sys, pathlib
root = pathlib.Path("/Users/ayankar/dev/osprey-wt/slice-AD1a")
f = root / "OspreyFlow_Core/services/api/model_admin.py"
orig = f.read_text()
name = sys.argv[1]
def sub(text, a, b):
    assert a in text, a
    return text.replace(a, b, 1)
CALL = '''            # No listing of the gateway's keys is asked for here or anywhere in the Conduit
'''
LIST = '''            await self._gateway._call("GET", "/key/list?return_full_object=true&page=1&size=100")
'''
LISTROW = '''            _rows = (await self._gateway._call("GET", "/key/list?return_full_object=true&page=1&size=100")).json()["keys"]
'''
if name == "PN4a":   # the listing put back at the reconcile (short call, nothing read)
    new = sub(orig, CALL, LIST + CALL)
elif name == "PN4k":  # the listing put back, and each key_name logged where it is read
    new = sub(orig, CALL, LISTROW + '            for _r in _rows:\n                log.info("listed %s", _r.get("key_name"))\n' + CALL)
elif name == "PN4s":  # the listing put back; a key's last four put into the words of a refusal
    new = sub(orig, CALL, LISTROW + '            globals()["_LAST"] = str(_rows[0].get("key_name"))[-4:]\n' + CALL)
    new = sub(new, '''            raise self._refused(resp, "the engine's limits' removal")''',
              '''            raise ModelAdminRefused("refused " + globals().get("_LAST", ""))''')
elif name == "PN4r":  # the route skipped: remove_engine does not delete the engine's key
    new = sub(orig, "            await self._gateway.delete_engine_key(name)\n            async with self._intending(name, by):", "            async with self._intending(name, by):")
else:
    raise SystemExit("unknown plant")
f.write_text(new)
try:
    r = subprocess.run("cd %s/OspreyFlow_Core && ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9 UV_PYTHON=3.12 UV_PROJECT_ENVIRONMENT=$HOME/dev/osprey-acceptance/AD1a uv run --frozen pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider --tb=no -rfp ../OspreyFlow_Build/tests/services/api/test_model_key_paths.py -k n4 2>&1 | grep -E '^(FAILED|PASSED)|passed|failed|rror'" % root, shell=True, capture_output=True, text=True)
    print(name); print(r.stdout.replace("../OspreyFlow_Build/tests/services/api/test_model_key_paths.py::", ""))
finally:
    f.write_text(orig)
