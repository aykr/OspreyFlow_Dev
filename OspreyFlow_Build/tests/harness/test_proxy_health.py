"""The front proxy's own health check passes against the real Caddy, on HTTPS as on HTTP —
ADR-114 Amendment 4, `spec/05_DEPLOYMENT.md` §3b.

Found 14 October 2026 installing the chart in a real cluster: on an HTTPS address the check asked
`http://127.0.0.1:80/healthz`, Caddy redirected it to HTTPS, and HTTPS to a bare address has no
certificate, so the proxy never became healthy — in a cluster, or in Lite or Small on HTTPS. Nothing
had run the check against Caddy itself. This does: the pinned image, the rendered Caddyfile, and the
exact command the compose file and the chart run. A name's plain-HTTP request must still go to
HTTPS, or health would have been bought by giving up the redirect.
"""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

import pytest
from harness.render import compose_services, service_images
from harness.site import PROXY_IMAGE, render_caddyfile

from schemas.deployment import OspreyConfig


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    if check:
        assert done.returncode == 0, done.stderr or done.stdout
    return done


@pytest.mark.parametrize("origin", ["https://osprey.localhost", "http://osprey.localhost"])
def test_the_proxys_health_check_passes_against_caddy(origin: str, tmp_path: Path) -> None:
    config = OspreyConfig.model_validate({"network": {"public_origin": origin}})
    proxy = compose_services(config, service_images(config))["proxy"]
    check = proxy["healthcheck"]["test"]
    assert check[0] == "CMD"
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text(render_caddyfile(config), encoding="utf-8")
    name = f"osprey-test-proxy-{uuid.uuid4().hex[:8]}"
    user = ["--user", proxy["user"]] if "user" in proxy else []
    env = [f"--env={k}={v}" for k, v in proxy.get("environment", {}).items()]
    _docker("run", "-d", "--name", name, *user, *env,
            "-v", f"{caddyfile}:/etc/caddy/Caddyfile:ro", PROXY_IMAGE)  # fmt: skip
    try:
        for _ in range(30):
            done = _docker("exec", name, *check[1:], check=False)
            if done.returncode == 0:
                break
            time.sleep(1)
        assert done.returncode == 0, (done.stdout + done.stderr)[-400:]
        if origin.startswith("https"):
            head = "GET / HTTP/1.0\\r\\nHost: osprey.localhost\\r\\n\\r\\n"
            request = f"printf '{head}' | nc 127.0.0.1 80"
            answer = _docker("exec", name, "sh", "-c", request).stdout
            assert answer.startswith("HTTP/1.0 308"), answer[:200]
            assert "Location: https://osprey.localhost/" in answer
    finally:
        _docker("rm", "-f", name, check=False)
