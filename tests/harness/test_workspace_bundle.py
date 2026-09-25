"""The built Glass bundle carries no address for the Conduit.

`05_DEPLOYMENT.md` §2.6 item 1, the owner's decision of 25 September 2026. The workspace image's
own nginx proxies `/v1` and the delta WebSocket to the Conduit on the internal network, so the
bundle issues relative paths and is portable across every deployment unchanged.

**Why this needs a test rather than a code review.** Vite inlines `import.meta.env.VITE_*` at build
time, which means the address is fixed when the *image* is built and is invisible to everything
afterwards — no deployment, no operator and no runtime check can see or change it. That is exactly
how the previous version failed: `App.tsx` read
`import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"`, the Dockerfile set nothing, and
every image built from it shipped `http://localhost:8000` baked into the JavaScript. Nothing was
wrong in the source; the default was simply the development one, and no test looked at the artefact.

So the assertion is made against the **built bundle**, not against the source or the Dockerfile.
A test reading `App.tsx` would have passed throughout the failure it exists to prevent.

**The planted violation is the real shape** (`CLAUDE.md` rule 15): a build with
`VITE_API_BASE_URL` set to an absolute URL, which is precisely what the image did before and what
a well-meaning `--build-arg` would reintroduce. Not a hand-written string injected into a fixture —
the check has to fail on the artefact the real pipeline emits.

This is a build-and-inspect test and it is slow (an `npm ci` plus a Vite build), so it is skipped
unless `OSPREY_TEST_BUNDLE=1` is set, and it is wired into the `deployment-exit-tests` CI job
rather than the fast one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "apps" / "workspace"

requires_opt_in = pytest.mark.skipif(
    os.environ.get("OSPREY_TEST_BUNDLE") != "1",
    reason="OSPREY_TEST_BUNDLE is not 1 — this builds the Glass with Vite and takes minutes",
)

#: An absolute `http(s)://…` immediately followed by a `/v1` path, or a bare origin with a port,
#: is what a baked-in Conduit address looks like in the emitted JavaScript. Deliberately narrow:
#: the bundle legitimately contains absolute URLs for map tile providers and for documentation
#: links, and a pattern that flagged every `https://` would be a gate nobody could keep green.
ABSOLUTE_API_URL = re.compile(
    r"https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?|https?://[^\"'`\s]+/v1/"
)


def _build(env: dict[str, str]) -> str:
    """Builds the Glass and returns every emitted JavaScript file concatenated.

    The whole `dist` tree, not `index.html` alone: Vite emits the application into hashed chunks
    under `assets/`, and that is where an inlined environment value lands.
    """
    out = WORKSPACE / "dist"
    if out.exists():
        shutil.rmtree(out)
    completed = subprocess.run(  # noqa: S603
        ["npm", "run", "build", "--workspace", "apps/workspace"],
        cwd=REPO_ROOT,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, f"the Glass did not build:\n{completed.stderr[-2000:]}"
    sources = sorted(out.rglob("*.js")) + sorted(out.rglob("*.html"))
    assert sources, "the build emitted no JavaScript"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in sources)


@requires_opt_in
def test_the_bundle_built_for_a_deployment_contains_no_absolute_api_url() -> None:
    """Green. `VITE_API_BASE_URL=""` — what `apps/workspace/Dockerfile` sets — leaves the bundle
    with relative `/v1/…` paths and no origin at all."""
    bundle = _build({"VITE_API_BASE_URL": ""})

    found = sorted(set(ABSOLUTE_API_URL.findall(bundle)))
    assert not found, (
        "the built bundle carries an absolute API address, so every deployment made from this "
        f"image would send requests there regardless of where its Conduit is: {found}"
    )
    assert "/v1/" in bundle, (
        "the bundle contains no /v1 path at all, so this test is passing because it is looking at "
        "the wrong thing rather than because the bundle is correct"
    )


@requires_opt_in
def test_the_same_check_fails_for_a_bundle_built_with_an_absolute_url() -> None:
    """Red, against the real shape: the build this image used to do.

    `VITE_API_BASE_URL=http://localhost:8000` is not an invented violation — it is the value
    `App.tsx`'s own `??` default supplied to every image built before 25 September 2026, and it is
    what a `--build-arg` would put back. If this case ever passes, the check above has stopped
    being able to see the thing it was written for.
    """
    bundle = _build({"VITE_API_BASE_URL": "http://localhost:8000"})

    assert ABSOLUTE_API_URL.search(bundle), (
        "a bundle built with an absolute Conduit address was not flagged, so the check above "
        "cannot detect the defect it exists for"
    )
