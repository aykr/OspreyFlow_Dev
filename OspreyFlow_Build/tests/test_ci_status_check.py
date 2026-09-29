"""`tools/ci_status_check.py`'s own proof — round 13cg.

Each case fixes a fake GitHub API transport (`httpx.MockTransport`, no extra dependency and no
respx) at one of the four states `latest_ci_status` has to tell apart, then asserts it reported
that one and no other. The case that matters most on this repository, as found this round, is
`test_no_check_runs_at_all_is_never_run_not_a_pass`: an empty `check_runs` array is what
`total_count: 0` on the real repository looks like through this exact endpoint, and it must not be
read as "nothing to report, so pass."
"""

from __future__ import annotations

import httpx

from tools.ci_status_check import latest_ci_status


def _client(check_runs: list[dict[str, object]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"total_count": len(check_runs), "check_runs": check_runs})

    return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))


def _run(name: str, status: str, conclusion: str | None) -> dict[str, object]:
    return {"name": name, "status": status, "conclusion": conclusion}


def test_no_check_runs_at_all_is_never_run_not_a_pass() -> None:
    """The real state this module was built for: zero check runs, not a zero-length list of
    passing ones. `is_green` must be false — the opposite reading is exactly what let the real
    repository's silence go unnoticed."""
    with _client([]) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert status.state == "never_run"
    assert not status.is_green


def test_a_still_running_check_run_is_pending_not_green() -> None:
    runs = [_run("lint", "completed", "success"), _run("test", "in_progress", None)]
    with _client(runs) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert status.state == "pending"
    assert "test" in status.detail
    assert not status.is_green


def test_a_failed_check_run_is_reported_by_name() -> None:
    runs = [
        _run("lint", "completed", "success"),
        _run("trivy", "completed", "failure"),
        _run("bundle", "completed", "failure"),
    ]
    with _client(runs) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert status.state == "failed"
    assert "trivy" in status.detail and "bundle" in status.detail
    assert "lint" not in status.detail
    assert not status.is_green


def test_neutral_and_skipped_conclusions_do_not_count_as_failures() -> None:
    """A job a path filter or a matrix leg legitimately did not run is not evidence of anything
    broken — the same distinction `ABSOLUTE_API_URL`'s own narrow pattern draws for a different
    gate (round 13cde's harness-image finding is the other side of over-broad matching)."""
    runs = [
        _run("lint", "completed", "success"),
        _run("optional-check", "completed", "neutral"),
        _run("matrix-leg-not-applicable", "completed", "skipped"),
    ]
    with _client(runs) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert status.state == "success"
    assert status.is_green


def test_all_green_reports_success() -> None:
    runs = [_run("lint", "completed", "success"), _run("test", "completed", "success")]
    with _client(runs) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert status.state == "success"
    assert status.is_green


def test_pagination_is_followed() -> None:
    """A ref with more check runs than one page — `ci.yml` alone has more than twenty jobs — must
    not silently stop at page one and report success on a partial, accidentally-all-green sample."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path + "?" + (request.url.query.decode() or ""))
        if "page=2" not in (request.url.query.decode() or ""):
            return httpx.Response(
                200,
                json={"check_runs": [_run("lint", "completed", "success")]},
                headers={
                    "link": (
                        '<https://api.github.com/x?page=2>; rel="next", '
                        '<https://api.github.com/x?page=9>; rel="last"'
                    )
                },
            )
        return httpx.Response(200, json={"check_runs": [_run("trivy", "completed", "failure")]})

    with httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    ) as client:
        status = latest_ci_status("ospreyflow", "ospreyflow-dev", "deadbeef", client=client)
    assert len(calls) == 2
    assert status.state == "failed"
    assert "trivy" in status.detail
