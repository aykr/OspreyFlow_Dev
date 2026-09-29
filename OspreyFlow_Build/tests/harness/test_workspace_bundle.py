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
import time

import pytest

from tools.layout import CORE
from tools.layout import REPO as REPO_ROOT

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

#: **One exemption, exact to the construct — closing pass 13ce, 28 September 2026.**
#: `oidc-client-ts` (added 25 September for PKCE sign-in, `3a508da`) parses a possibly-relative
#: redirect URL against a throwaway base in `UrlUtils.readParams`:
#: `new URL(url, "http://127.0.0.1")[responseMode === "fragment" ? "hash" : "search"]`. That
#: origin is never requested; only the parsed hash or query is read. The bare-origin
#: alternative of `ABSOLUTE_API_URL` matched it, so this test could not pass on any build since
#: that dependency arrived, and nothing ran it (the `deployment-exit-tests` job had not executed
#: since 22 September). Matched as the minified expression **including** its `[…"hash":"search"]`
#: property access, so the same origin anywhere else in the bundle, or with a port, or as a
#: plain string, is still flagged; `test_the_exemption_hides_only_the_library_parsing_base` holds
#: that. A version of the library that changes the expression makes this test red again, which
#: is the safe direction.
LIBRARY_URL_PARSING_BASE = re.compile(
    r'new URL\([\w$]+,"http://127\.0\.0\.1"\)\[[\w$]+==="fragment"\?"hash":"search"\]'
)


def absolute_api_urls(bundle: str) -> list[str]:
    """Every baked-in Conduit-shaped address in `bundle`, less the one library parsing base."""
    return sorted(set(ABSOLUTE_API_URL.findall(LIBRARY_URL_PARSING_BASE.sub("", bundle))))


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
        cwd=CORE,
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

    found = absolute_api_urls(bundle)
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

    assert absolute_api_urls(bundle), (
        "a bundle built with an absolute Conduit address was not flagged, so the check above "
        "cannot detect the defect it exists for"
    )


def test_the_exemption_hides_only_the_library_parsing_base() -> None:
    """Not opt-in: this is the exemption's own red proof and needs no build.

    The library's minified expression, verbatim from the 25 September bundle, is exempt. The same
    origin in every shape a baked Conduit address could take beside it is not: the identical
    `new URL(…)` call without the `hash`/`search` access, the origin with a port, and a bare
    string literal.
    """
    library = 'const n=new URL(r,"http://127.0.0.1")[e==="fragment"?"hash":"search"];'
    assert absolute_api_urls(library) == []

    for baked in (
        'fetch(new URL(p,"http://127.0.0.1"))',
        'new URL(r,"http://127.0.0.1:8000")[e==="fragment"?"hash":"search"]',
        'const base="http://127.0.0.1";',
        'const base="http://localhost:8000";',
    ):
        assert absolute_api_urls(library + baked), f"{baked!r} was hidden by the exemption"


@requires_opt_in
def test_a_production_build_fails_with_the_dev_bearer_token_set() -> None:
    """`06_DECISIONS.md` ADR-050: "the VITE_DEV_BEARER_TOKEN path survives only for `npm run dev`.
    A production build with it set fails the build." The planted violation is the real shape (rule
    15): the variable present at `vite build` — an environment variable, not a source edit — which
    is exactly what a well-meaning `--build-arg` would reintroduce, the same class of mistake
    `test_the_same_check_fails_for_a_bundle_built_with_an_absolute_url` above guards against for
    the Conduit's own address.
    """
    completed = subprocess.run(  # noqa: S603
        ["npm", "run", "build", "--workspace", "apps/workspace"],
        cwd=CORE,
        env={**os.environ, "VITE_DEV_BEARER_TOKEN": "fake-dev-token"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0, (
        "a production build with VITE_DEV_BEARER_TOKEN set exited 0 — the fence in "
        "apps/workspace/vite.config.ts did not fire"
    )
    assert "VITE_DEV_BEARER_TOKEN" in completed.stderr


@requires_opt_in
def test_a_production_build_succeeds_with_no_dev_bearer_token() -> None:
    """Green beside the red above — the fence must not block an ordinary build."""
    _build({"VITE_API_BASE_URL": ""})


@requires_opt_in
def test_the_workspace_serves_with_no_conduit_reachable_at_all() -> None:
    """The Glass is static and must come up whether or not the Conduit is there.

    **Found on the first golden path after the proxy was added.** A literal
    `proxy_pass http://api:8000` makes nginx resolve `api` once while loading its configuration and
    refuse to start if it cannot — `[emerg] host not found in upstream "api"`. The workspace starts
    before the Conduit, so nginx exited, the container restarted, and `docker compose up --wait`
    reported the workspace unhealthy and failed the whole deploy.

    That is a start-order race, but the invariant underneath it is larger and is what this asserts:
    a deployment whose Conduit is down or still starting must still serve the workspace. Once
    ADR-050's sign-in exists, this is the difference between a user seeing a sign-in screen and
    seeing nothing at all.

    `CLAUDE.md` rule 12 — the test that fails if it regresses is this one, and it runs the **real
    image on a network with no `api` on it**, because the failure was in nginx's start-up
    behaviour and no assertion about the config file's text would have caught it. A check that
    `proxy_pass` contains a `$` would pass against a config that was broken some other way.
    """
    image = "osprey/workspace:bundle-test"
    built = subprocess.run(  # noqa: S603
        ["docker", "build", "-f", "apps/workspace/Dockerfile", "-t", image, "."],
        cwd=CORE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, f"the workspace image did not build:\n{built.stderr[-2000:]}"

    container = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", "-d", "-P", image],
        capture_output=True,
        text=True,
        check=False,
    )
    assert container.returncode == 0, container.stderr
    cid = container.stdout.strip()
    try:
        # No `api` exists on this container's network — that is the whole point. If nginx resolved
        # its upstream at start-up, it is already dead and the exec below cannot run.
        for _ in range(30):
            probe = subprocess.run(  # noqa: S603
                ["docker", "exec", cid, "wget", "-q", "-O", "-", "http://127.0.0.1:8080/"],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.returncode == 0:
                break
            time.sleep(1)
        assert probe.returncode == 0, (
            "the workspace does not serve its own index with no Conduit reachable: "
            f"{(probe.stderr or probe.stdout)[:400]}"
        )
        assert "<div id=" in probe.stdout or "<script" in probe.stdout, (
            f"served something that is not the Glass: {probe.stdout[:200]}"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)  # noqa: S603


@requires_opt_in
def test_the_proxied_liveness_route_answers_for_the_conduit_not_the_glass() -> None:
    """`/healthz` must reach the Conduit, or it reports the opposite of the truth.

    **Found by reading what `harness.apply` printed.** It prints a Conduit health URL on the
    workspace's own port, and that URL returned the Glass's `index.html` with a 200 — because
    `/healthz` is not under `/v1`, so it fell through to the single-page-application route. A
    health check that answers 200 for a dead Conduit is worse than one that 404s: the 404 is
    obviously wrong and the 200 is quietly wrong.

    This runs the workspace image with **no Conduit on its network**, so a correct proxy must fail
    to reach one — 502 or 504 — and an incorrect one serves HTML with a 200. Asserting the failure
    rather than the success is what makes this test possible without standing up a whole
    deployment, and it is the more useful direction anyway: the defect was a false *success*.
    """
    image = "osprey/workspace:bundle-test"
    built = subprocess.run(  # noqa: S603
        ["docker", "build", "-f", "apps/workspace/Dockerfile", "-t", image, "."],
        cwd=CORE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0, f"the workspace image did not build:\n{built.stderr[-2000:]}"

    container = subprocess.run(  # noqa: S603
        ["docker", "run", "--rm", "-d", image], capture_output=True, text=True, check=False
    )
    assert container.returncode == 0, container.stderr
    cid = container.stdout.strip()
    try:
        status = ""
        for _ in range(30):
            probe = subprocess.run(  # noqa: S603
                [
                    "docker",
                    "exec",
                    cid,
                    "wget",
                    "-q",
                    "-S",
                    "-O",
                    "/dev/null",
                    "http://127.0.0.1:8080/healthz",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            status = probe.stderr
            if "HTTP/" in status:
                break
            time.sleep(1)

        assert "HTTP/" in status, f"nginx never answered /healthz at all: {status[:300]}"
        assert " 200 " not in status, (
            "/healthz answered 200 with no Conduit on the network, so it is being served by the "
            f"single-page-application fallback rather than proxied: {status[:300]}"
        )
        assert " 502 " in status or " 504 " in status, (
            f"/healthz did not fail as a proxy failure, so it is not proxied: {status[:300]}"
        )
    finally:
        subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)  # noqa: S603
