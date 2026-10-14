"""The workspace's nginx reaches the Conduit wherever the deployment runs — compose's network or a
Kubernetes cluster (`spec/05_DEPLOYMENT.md` §3b, ADR-114 Amendment 13).

Found 14 October 2026 installing the chart in a real cluster: the configuration named Docker's own
DNS (`resolver 127.0.0.11`), which a Kubernetes pod does not have, so every `/v1` request answered
502. Now the resolver is the container's own (`/etc/resolv.conf`, through the nginx image's
`NGINX_ENTRYPOINT_LOCAL_RESOLVERS`) and the Conduit's name is `OSPREY_CONDUIT_HOST` — `api` on
compose, the Service's full name on a cluster, since nginx's resolver applies no search domain.

Run against the workspace image itself, built from this checkout (Docker's cache makes a rebuild
quick), and a stand-in Conduit answering `/healthz` on a Docker network under both names.
"""

from __future__ import annotations

import re
import subprocess
import time
import uuid

import pytest
from harness.render import REPO_ROOT

WORKSPACE = REPO_ROOT / "apps" / "workspace"
TEMPLATE = WORKSPACE / "nginx.conf.template"


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=120, check=False
    )
    if check:
        assert done.returncode == 0, done.stderr or done.stdout
    return done


def _dockerfile_runtime() -> tuple[str, dict[str, str]]:
    text = (WORKSPACE / "Dockerfile").read_text(encoding="utf-8")
    runtime = text[text.rindex("FROM nginx:") :]
    image = runtime.split()[1]
    env = dict(re.findall(r"^ENV (\w+)=(\S+)", runtime, flags=re.MULTILINE))
    copied = "COPY apps/workspace/nginx.conf.template /etc/nginx/templates/default.conf.template"
    assert copied in runtime
    assert "USER nginx" in runtime
    return image, env


def test_the_image_takes_its_resolver_from_the_container_and_names_the_conduit_by_setting() -> None:
    _, env = _dockerfile_runtime()
    assert env == {"NGINX_ENTRYPOINT_LOCAL_RESOLVERS": "1", "OSPREY_CONDUIT_HOST": "api"}
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "resolver 127.0.0.11" not in template
    assert template.count("resolver ${NGINX_LOCAL_RESOLVERS}") == 2
    assert template.count("http://${OSPREY_CONDUIT_HOST}:8000") == 2


@pytest.fixture(scope="module")
def workspace_image() -> str:
    tag = "osprey-test-workspace:proxy"
    _docker("build", "-q", "-f", str(WORKSPACE / "Dockerfile"), "-t", tag, str(REPO_ROOT))
    return tag


@pytest.mark.parametrize("conduit", ["api", "api.osprey.svc.cluster.local"])
def test_the_workspace_reaches_the_conduit_by_the_name_it_is_given(
    conduit: str, workspace_image: str
) -> None:
    tag = uuid.uuid4().hex[:8]
    network, stand_in, nginx = (f"osprey-test-{part}-{tag}" for part in ("net", "api", "ws"))
    _docker("network", "create", network)
    try:
        # A stand-in Conduit: answers `/healthz` with a word the test looks for.
        _docker("run", "-d", "--name", stand_in, "--network", network, "--network-alias", conduit,
                "python:3.12-slim", "python", "-c",
                "import http.server as h\n"
                "class A(h.BaseHTTPRequestHandler):\n"
                "  def do_GET(s):\n"
                "    s.send_response(200); s.end_headers(); s.wfile.write(b'conduit-alive')\n"
                "h.HTTPServer(('', 8000), A).serve_forever()")  # fmt: skip
        named = [] if conduit == "api" else [f"--env=OSPREY_CONDUIT_HOST={conduit}"]
        _docker("run", "-d", "--name", nginx, "--network", network, *named, workspace_image)
        answer = None
        for _ in range(30):
            answer = _docker("exec", nginx, "wget", "-q", "-O", "-",
                             "http://127.0.0.1:8080/healthz", check=False)  # fmt: skip
            if answer.returncode == 0:
                break
            time.sleep(1)
        assert answer is not None and answer.stdout == "conduit-alive", (
            answer.stderr if answer else "",
            _docker("logs", nginx, check=False).stderr[-600:],
        )
    finally:
        _docker("rm", "-f", stand_in, nginx, check=False)
        _docker("network", "rm", network, check=False)
