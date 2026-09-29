"""`harness/geospatial.py`'s own docstring makes a specific, checkable claim: importing
`scripts.build_local_basemap` or `scripts.verify_map` pulls in `services`/`adapters` modules as an
unavoidable side effect, and `scripts.geo_local_provider` does not. Proven here directly, in a
subprocess with a fresh `sys.modules` each time — importing any of these three inside *this* test
process would be contaminated by whatever another test module already imported first, which is
exactly the kind of "passes here, fails in the real container" gap `CLAUDE.md` rule 15 warns
about; the subprocess is what keeps this test honest about the real, cold-start case."""

from __future__ import annotations

import ast
import os
import subprocess
import sys

from tools.layout import REPO as _REPO_ROOT

#: `pyproject.toml`'s own `[tool.pytest.ini_options] pythonpath = ["packages"]` puts this repo
#: root and `packages/` on *this* process's `sys.path` — a pytest-internal mechanism, not the
#: `PYTHONPATH` environment variable, so a spawned subprocess inherits neither by default. Found
#: running `make test` for real (the Makefile's own bare `.venv/bin/pytest`, no `PYTHONPATH=`
#: prefix): this test passed under a manual `PYTHONPATH=.:packages pytest ...` invocation and
#: failed under the real one, exactly the "passes here, fails for real" gap this file's own
#: docstring already warns about — so the subprocess's own environment is set explicitly here,
#: never left to inherit whatever the parent happened to export.

_SUBPROCESS_ENV = {**os.environ, "PYTHONPATH": f"{_REPO_ROOT}:{_REPO_ROOT / 'packages'}"}


def _services_or_adapters_modules_loaded_by(import_statement: str) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys\n{import_statement}\n"
            "print(sorted(m for m in sys.modules if m.startswith(('services', 'adapters'))))",
        ],
        capture_output=True,
        text=True,
        env=_SUBPROCESS_ENV,
        check=True,
    )
    modules = ast.literal_eval(result.stdout.strip())
    assert isinstance(modules, list)
    return modules


def test_geo_local_provider_pulls_in_no_services_or_adapters_module() -> None:
    """The claim `harness/geospatial.py` relies on to import this module safely inside the
    harness image."""
    loaded = _services_or_adapters_modules_loaded_by("import scripts.geo_local_provider")
    assert loaded == []


def test_build_local_basemap_does_pull_in_services_and_adapters() -> None:
    """The planted-violation half of the same claim, `CLAUDE.md` rule 15's own discipline: if this
    ever returned `[]` too, `harness/geospatial.py`'s own reason for refusing to wire
    `build_local_basemap` directly would no longer hold, and the 501 in
    `test_webapp_geospatial.py::test_build_basemap_refuses_with_the_real_reason` would be a stale
    refusal, not a real one."""
    loaded = _services_or_adapters_modules_loaded_by("import scripts.build_local_basemap")
    assert any(m.startswith("services.ingest") for m in loaded)
    assert any(m.startswith("adapters.graph_arcadedb") for m in loaded)


def test_verify_map_does_pull_in_services() -> None:
    loaded = _services_or_adapters_modules_loaded_by("import scripts.verify_map")
    assert "services.api.mapconfig_loader" in loaded
    assert "services.api.tier4_registration" in loaded
