"""The recovery runbook says what a healthy restore's logs end with (R1 on kind, finding 11), so a platform
team reading a restore Job's log knows success when they see it, and the words it quotes are the ones the
restore's own code prints: a reworded message breaks this test, not the runbook's reader."""

from __future__ import annotations

from pathlib import Path

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"

#: Each healthy line as the runbook quotes it, and the source that prints it.
HEALTHY = {
    "restore: set <set> verified, every part; nothing writing": (
        "services/api/platform_backup.py", 'restore: set {set_id} verified, every part; nothing writing'),
    "restore-graph: <database> restored from the set, checked and put in place; the old one removed": (
        "deploy/backups/restore-graph.sh", "restore-graph: $db restored from the set, checked and put in place; the old one removed"),
    "restore: ClickHouse restored from set <set>": (
        "services/api/platform_backup.py", "restore: ClickHouse restored from set {set_id}"),
    "restore: ingest put back from set <set>": (
        "services/api/platform_backup.py", "restore: {', '.join(names)} put back from set {set_id}"),
}  # fmt: skip


def _cloud_platform_section() -> str:
    text = (CORE / "deploy" / "RUNBOOK.md").read_text(encoding="utf-8")
    return text[text.index("## The `cloud-platform` profile") :]


def test_the_runbook_says_what_a_healthy_restore_s_logs_end_with() -> None:
    section = _cloud_platform_section()
    assert "**A healthy restore.**" in section
    healthy = section[section.index("**A healthy restore.**") :].split("\n\n", 1)[0]
    for quoted in HEALTHY:
        assert f"`{quoted}`" in healthy, quoted
    assert "stack trace" in healthy


def test_each_healthy_line_is_one_the_restore_prints() -> None:
    for quoted, (source, printed) in HEALTHY.items():
        assert printed in (CORE / source).read_text(encoding="utf-8"), (quoted, source)


def test_a_restore_ends_when_what_it_started_is_ready() -> None:
    """R1 on kind, finding 13: step 4 scaled each writer back and waited for ArcadeDB alone, so the
    runbook ended while the Conduit was still starting: the first request after it was a 503 at the
    door. Each one started again is waited for, before the backups resume."""
    section = _cloud_platform_section()
    step = section[section.index("# 4. Only when every Job finished") :]
    step = step[: step.index("```")]
    scale = step.index("scale deployment/<each one noted>")
    waits = step.index("rollout status deployment/<each one noted>")
    resume = step.index('"suspend":false')
    assert scale < waits < resume
