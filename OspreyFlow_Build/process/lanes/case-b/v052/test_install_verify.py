"""The step 6 verifier (install_verify.py), offline: every poc manifest entry becomes a check, an entry
with no check stops the run before anything runs, and a deployment missing any one listed item fails.

Run from OspreyFlow_Core (the manifest's own package):

    .venv/bin/python -m pytest -c ../OspreyFlow_Build/pytest.ini -p no:cacheprovider \
        ../OspreyFlow_Build/process/lanes/case-b/v052/
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import install_verify as iv
from harness.cloud_platform.manifest import load


def candidate() -> dict[str, Any]:
    """The manifest as it stands at the candidate: every step rendered, no `pending` left. The OpenSearch domain's
    egress placeholder goes, as 3a took it out (platform's 1d914fe: the domain is reached on the managed networks,
    not an egress host); a placeholder left in fails (test_an_egress_placeholder_fails_without_probing)."""
    m = iv.without_pending(load())
    m["egress"] = {h: e for h, e in m["egress"].items() if not h.startswith("<")}
    return m


#: The candidate's commit, as the copy's HEAD names it; the render tags ours with it (render.git_sha) and, before
#: the checkout is tagged, writes the release as `dev-<git rev-parse --short>` (release.checkout_version).
CANDIDATE = "0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d"
OLD_COMMIT = "1111111111111111111111111111111111111111"  # v0.5.1's


class Fake:
    """A deployment that has exactly what the manifest lists, in the manifest's own terms; `drop`
    takes one listed item away the way a real deployment lacks it (absent, not ready, never reached)."""

    def __init__(self, m: dict[str, Any]) -> None:
        self.m = m
        self.dropped: set[str] = set()
        self.reaches_anything = False
        self.offline = False
        self.differences: list[str] = []

    def drop(self, entry: str) -> Fake:
        self.dropped.add(entry)
        return self

    def workload(self, name: str) -> dict[str, Any] | None:
        if f"workloads.{name}" in self.dropped:
            return None
        w = self.m["workloads"][name]
        return {
            "kind": w["kind"], "desired": w["count"], "ready": w["count"], "image": w["image"],
            "requests": w["requests"], "limits": w["limits"], "probe": w["readiness"] != "none",
            "updated": w["count"], "settled": True, "current": "version" not in self.dropped,
            "replicas": w["count"], "available": w["count"], "unavailable": 0, "revisions_match": True,
            "tag": CANDIDATE if self.m["images"][w["image"]]["ours"] else None,
        }

    def init_container(self, key: str) -> dict[str, Any] | None:
        if f"init_containers.{key}" in self.dropped:
            return None
        return {**self.m["init_containers"][key], "exit_code": 0}

    def job(self, name: str) -> dict[str, Any] | None:
        if f"jobs.{name}" in self.dropped:
            return None
        j = self.m["jobs"][name]
        steps = {s: {"exit_code": 0} for s in j.get("steps", [])}
        if "restore-graph" in j:
            steps["restore-graph"] = {**j["restore-graph"], "exit_code": 0}
        suspended = str(j.get("schedule", "")).startswith("suspended")
        return {"kind": j["kind"], "schedule": "0 0 31 2 *" if suspended else j.get("schedule"),
                "suspended": suspended, "image": j["image"],
                "requests": j["requests"], "limits": j["limits"], "succeeded": 1, "steps": steps,
                "current": True, "tag": CANDIDATE}

    def image_pushed(self, repository: str) -> bool:
        return f"images.{repository}" not in self.dropped

    def candidate(self) -> str | None:
        return CANDIDATE

    def release(self) -> str | None:
        # Read through release_of from the ConfigMap as the chart writes it (configmaps.yaml, `ospreyflow-env`),
        # with the value the render writes before the candidate is tagged (the install test's day).
        version = "v0.5.1" if "release" in self.dropped else f"dev-{CANDIDATE[:7]}"
        return iv.release_of({"kind": "ConfigMap", "metadata": {"name": "ospreyflow-env"},
                              "data": {"OSPREY_RELEASE_VERSION": version, "OSPREY_ENV": "production"}})

    def database_readers(self, database: str) -> set[str]:
        if f"managed.rds.databases.{database}" in self.dropped:
            return set()
        return set(iv.DATABASE_READERS[database])

    def rds_setting(self, name: str) -> str | None:
        if "managed.rds" in self.dropped:
            return None
        return {"max_connections": str(self.m["managed"]["rds"]["max_connections"]),
                "server_version": "16.4"}[name]

    def store_readers(self, store: str) -> set[str]:
        return set() if f"managed.{store}" in self.dropped else set(iv.STORE_READERS[store])

    def bucket_objects(self, bucket: str) -> int:
        return 0 if f"managed.s3.buckets.{bucket}" in self.dropped else 3

    def entra_used(self, registration: str) -> bool:
        return f"entra.{registration}" not in self.dropped

    def connects(self, host: str) -> bool:
        if host.startswith("<"):
            raise LookupError(f"the egress probe gave no answer about the policy: 'dns' ({host})")  # as the real probe
        if host in self.m["egress"]:
            return f"egress.{host}" not in self.dropped
        return self.reaches_anything

    def reachable_outside(self, host: str) -> bool:
        return not self.offline

    def shape(self) -> str:
        return "small" if "shape" in self.dropped else self.m["shape"]

    def render_differences(self) -> list[str]:
        return list(self.differences)


# ---- the plan: every entry checked, or the run stops ------------------------------------------


def test_every_entry_of_the_manifest_has_a_check() -> None:
    m = candidate()
    checks = iv.plan(m)
    ids = {c.entry for c in checks}
    assert set(iv.entries(m)) <= ids
    assert iv.UNLISTED_HOST_CHECK in ids and iv.RENDER_CHECK in ids


#: Collections: a new entry in one gets its own check, so the injection adds an entry with an unknown key.
_COLLECTIONS = {("workloads",), ("init_containers",), ("jobs",), ("images",), ("entra",), ("egress",), ("managed",),
                ("managed", "rds", "databases")}
#: Compared whole, not walked: `requests` and `limits` at run time against the deployment; `readiness` only by
#: the render check (`manifest.differences`), the live check asking only that a probe is there. Items inside
#: lists (`grants`, `app_roles`, `buckets`, `steps`) are not walked here: buckets and steps are checked by name.
_WHOLE = {"requests", "limits", "readiness"}


def _dict_nodes(node: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    found = [path] if isinstance(node, dict) and (not path or path[-1] not in _WHOLE) else []
    if isinstance(node, dict):
        for k, v in node.items():
            found += _dict_nodes(v, (*path, k))
    return found


@pytest.mark.parametrize("path", _dict_nodes(candidate()), ids=lambda p: ".".join(p) or "(top)")
def test_an_unplaced_key_anywhere_in_the_manifest_stops_the_run(path: tuple[str, ...]) -> None:
    """Walked over the YAML itself, not over `entries()`: anything `entries` and `plan` both pass over
    would otherwise agree with itself (the review of 816922f, item 9)."""
    m = candidate()
    node: Any = m
    for k in path:
        node = node[k]
    if path in _COLLECTIONS:
        node["zz-unplaced"] = {"zz_unplaced": 1}
    else:
        node["zz_unplaced"] = 1
    with pytest.raises(iv.NotExercised) as stopped:
        iv.plan(m)
    assert any("zz-unplaced" in line or "zz_unplaced" in line for line in stopped.value.entries), stopped.value.entries


def test_the_real_manifest_names_at_least_what_the_route_lists() -> None:
    """A floor, so `entries` cannot quietly read nothing and agree with itself."""
    ids = set(iv.entries(candidate()))
    for must in ("workloads.api", "workloads.superset", "workloads.report-sync", "images.ospreyflow/api",
                 "managed.rds.databases.superset", "managed.opensearch", "managed.s3.buckets.backups",
                 "entra.report-sync", "egress.login.microsoftonline.com", "jobs.ospreyflow-backup",
                 "init_containers.litellm/litellm-db"):
        assert must in ids, must


@pytest.mark.parametrize(
    ("change", "named"),
    [
        (lambda m: m.__setitem__("queues", {"sqs": {}}), "queues"),
        (lambda m: m["workloads"]["api"].__setitem__("gpu", 1), "workloads.api: gpu"),
        (lambda m: m["managed"]["rds"]["databases"].__setitem__("reports", {}), "managed.rds.databases.reports"),
        (lambda m: m["managed"].__setitem__("sqs", {"queues": 1}), "managed.sqs"),
        (lambda m: m["managed"]["rds"].__setitem__("multi_az", True), "managed.rds: multi_az"),
        (lambda m: m["jobs"]["ospreyflow-backup"].__setitem__("steps", ["ship"]), "jobs.ospreyflow-backup: steps ship"),
        (lambda m: m["entra"].__setitem__("graph", {"kind": "daemon"}), "entra.graph"),
        (lambda m: m["managed"]["s3"]["buckets"].append("exports"), "managed.s3.buckets.exports"),
    ],
)
def test_a_listed_item_with_no_check_stops_the_run(change: Any, named: str) -> None:
    m = candidate()
    change(m)
    with pytest.raises(iv.NotExercised) as stopped:
        iv.plan(m)
    assert any(named in line for line in stopped.value.entries), stopped.value.entries


def test_an_entry_still_pending_stops_the_run_unless_a_dry_run_allows_it() -> None:
    m = load()
    assert any("pending" in line for line in _pending(m)), "the manifest on this branch has pending entries"
    with pytest.raises(iv.NotExercised) as stopped:
        iv.plan(m)
    assert any("still pending" in line for line in stopped.value.entries)
    planned = iv.plan(m, allow_pending=True)
    assert "workloads.superset" not in {c.entry for c in planned}  # left out, and said so by `skipped`
    assert "workloads.superset" in iv.skipped_pending(m)


def _pending(m: dict[str, Any]) -> list[str]:
    return [f"{e} pending" for e in iv.skipped_pending(m)]


# ---- the run: a complete deployment passes, one missing item fails --------------------------------


def test_a_deployment_with_everything_listed_passes() -> None:
    m = candidate()
    results = iv.verify(m, Fake(m))
    assert [r for r in results if not r.ok] == []


@pytest.mark.parametrize("entry", iv.entries(candidate()))
def test_a_deployment_missing_any_one_listed_item_fails_on_it(entry: str) -> None:
    m = candidate()
    results = iv.verify(m, Fake(m).drop(entry))
    failed = [r.entry for r in results if not r.ok]
    assert failed == [entry], failed


def test_an_unlisted_host_reached_fails() -> None:
    m = candidate()
    fake = Fake(m)
    fake.reaches_anything = True
    failed = [r.entry for r in iv.verify(m, fake) if not r.ok]
    assert failed == [iv.UNLISTED_HOST_CHECK]


def test_the_render_differing_from_the_manifest_fails() -> None:
    m = candidate()
    fake = Fake(m)
    fake.differences = ["differs: workloads api count: listed 1, rendered 2"]
    failed = [r for r in iv.verify(m, fake) if not r.ok]
    assert [r.entry for r in failed] == [iv.RENDER_CHECK]
    assert "rendered 2" in failed[0].said


@pytest.mark.parametrize(
    ("field", "value"),
    [("ready", 0), ("desired", 2), ("kind", "StatefulSet"), ("image", "ospreyflow/worker"),
     ("requests", {"cpu": "1", "memory": "2Gi"}), ("limits", {"cpu": "4", "memory": "4Gi"}), ("probe", False)],
)
def test_a_workload_unlike_its_entry_fails(field: str, value: Any) -> None:
    m = candidate()

    class Unlike(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            return {**got, field: value} if got and name == "api" else got

    failed = [r.entry for r in iv.verify(m, Unlike(m)) if not r.ok]
    assert failed == ["workloads.api"]


def test_a_failed_restore_step_fails_its_job() -> None:
    m = candidate()

    class Broken(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            if got and name == "ospreyflow-restore-<set>":
                got = copy.deepcopy(got)
                got["steps"]["restore-graph"]["exit_code"] = 1
            return got

    failed = [r.entry for r in iv.verify(m, Broken(m)) if not r.ok]
    assert failed == ["jobs.ospreyflow-restore-<set>"]


def test_a_cronjob_present_whose_runs_never_succeeded_fails() -> None:
    """The backup's CronJob exists at its schedule and image, but no run of it succeeded."""
    m = candidate()

    class NeverRan(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            return {**got, "succeeded": 0} if got and name == "ospreyflow-backup" else got

    failed = [r for r in iv.verify(m, NeverRan(m)) if not r.ok]
    assert [r.entry for r in failed] == ["jobs.ospreyflow-backup"] and "no run succeeded" in failed[0].said


def _with_search_jobs() -> dict[str, Any]:
    """3a's shape, on main's manifest since 13 November: held-suspended CronJobs, and OpenSearch's signing."""
    m = candidate()
    assert {"ospreyflow-search-rebuild", "ospreyflow-search-drift"} <= set(m["jobs"])
    assert m["managed"]["opensearch"]["signing"] == "sigv4"
    return m


def test_3as_shape_is_planned_and_passes_when_present() -> None:
    m = _with_search_jobs()
    assert {"jobs.ospreyflow-search-rebuild", "jobs.ospreyflow-search-drift"} <= {c.entry for c in iv.plan(m)}
    assert [r for r in iv.verify(m, Fake(m)) if not r.ok] == []


def test_a_cronjob_listed_suspended_that_runs_on_a_schedule_fails() -> None:
    m = _with_search_jobs()

    class Scheduled(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            return {**got, "suspended": False} if got and name == "ospreyflow-search-drift" else got

    failed = [r for r in iv.verify(m, Scheduled(m)) if not r.ok]
    assert [r.entry for r in failed] == ["jobs.ospreyflow-search-drift"] and "not suspended" in failed[0].said


def test_a_suspended_cronjob_never_started_fails() -> None:
    m = _with_search_jobs()

    class NeverStarted(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            return {**got, "succeeded": 0} if got and name == "ospreyflow-search-rebuild" else got

    failed = [r for r in iv.verify(m, NeverStarted(m)) if not r.ok]
    assert [r.entry for r in failed] == ["jobs.ospreyflow-search-rebuild"] and "no run succeeded" in failed[0].said


#: kubectl's status for one copy, RollingUpdate (maxSurge 1, maxUnavailable 0), the candidate's pod crash-looping:
#: the v0.5.1 pod still Ready, the new ReplicaSet's surge pod not (the review of fabb284, N2).
STUCK_STATUS = {"observedGeneration": 4, "replicas": 2, "updatedReplicas": 1, "readyReplicas": 1,
                "availableReplicas": 1, "unavailableReplicas": 1,
                "conditions": [{"type": "Progressing", "status": "True", "reason": "ReplicaSetUpdated"}]}


def _deployment(status: dict[str, Any], image: str = "r/ospreyflow/api@sha256:new") -> dict[str, Any]:
    return {"kind": "Deployment", "metadata": {"name": "api", "generation": 4},
            "spec": {"replicas": 1, "template": {"spec": {"containers": [{"name": "api", "image": image}]}}},
            "status": status}


def test_a_crash_looping_candidate_beside_the_ready_old_pod_fails() -> None:
    m = candidate()
    stuck = iv.read_workload(_deployment(STUCK_STATUS), "r", expected={"ospreyflow/api": "r/ospreyflow/api@sha256:new"})

    class Stuck(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            return {**got, **{k: stuck[k] for k in ("replicas", "updated", "ready", "available", "unavailable", "settled")}} if got and name == "api" else got

    failed = [r for r in iv.verify(m, Stuck(m)) if not r.ok]
    assert [r.entry for r in failed] == ["workloads.api"], failed
    assert "2 replicas" in failed[0].said and "1 unavailable" in failed[0].said


@pytest.mark.parametrize(
    ("change", "said"),
    [({"settled": False}, "not yet rolled out"), ({"ready": 0}, "ready 0"), ({"revisions_match": False}, "revisions differ")],
)
def test_each_unfinished_rollout_reading_alone_fails(change: dict[str, Any], said: str) -> None:
    m = candidate()

    class Unfinished(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            return {**got, **change} if got and name == "arcadedb" else got

    failed = [r for r in iv.verify(m, Unfinished(m)) if not r.ok]
    assert [r.entry for r in failed] == ["workloads.arcadedb"] and said in failed[0].said


#: kubectl's status for a StatefulSet one pod into an update: the old revision's pod still Ready.
STS_MID_UPDATE = {"observedGeneration": 2, "replicas": 1, "readyReplicas": 1, "availableReplicas": 1,
                  "currentRevision": "arcadedb-6d", "updateRevision": "arcadedb-7f"}


def test_a_statefulset_mid_update_fails() -> None:
    m = candidate()
    sts = {"kind": "StatefulSet", "metadata": {"name": "arcadedb", "generation": 2},
           "spec": {"replicas": 1, "template": {"spec": {"containers": [{"name": "arcadedb", "image": "r/arcadedata/arcadedb@sha256:a"}]}}},
           "status": STS_MID_UPDATE}
    got = iv.read_workload(sts, "r", expected={})
    assert got["revisions_match"] is False and got["updated"] == 0

    class MidUpdate(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            have = super().workload(name)
            keys = ("replicas", "updated", "ready", "available", "unavailable", "settled", "revisions_match")
            return {**have, **{k: got[k] for k in keys}} if have and name == "arcadedb" else have

    failed = [r for r in iv.verify(m, MidUpdate(m)) if not r.ok]
    assert [r.entry for r in failed] == ["workloads.arcadedb"], failed


def test_a_workload_still_on_the_old_release_fails_the_version_check() -> None:
    m = candidate()

    class Old(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            return {**got, "current": False} if got and name == "worker" else got

    failed = [r for r in iv.verify(m, Old(m)) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and "worker" in failed[0].said


def test_a_deployment_whose_release_is_another_fails_the_version_check() -> None:
    """The kept render could itself be v0.5.1's: the deployment's own release (OSPREY_RELEASE_VERSION) is held to
    the candidate."""
    m = candidate()
    failed = [r for r in iv.verify(m, Fake(m).drop("release")) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and "v0.5.1" in failed[0].said


def test_the_release_is_read_from_the_env_configmap() -> None:
    assert iv.release_of({"data": {"OSPREY_RELEASE_VERSION": "v0.5.2"}}) == "v0.5.2"
    assert iv.release_of({"data": {}}) is None
    with pytest.raises(LookupError):
        iv.release_of(None)


@pytest.mark.parametrize(
    ("release", "ok"),
    [("v0.5.2", True), ("0.5.2", True), (f"dev-{CANDIDATE[:7]}", True), (f"dev-{CANDIDATE[:12]}", True),
     ("dev-unknown", False), ("v0.5.1", False), ("dev-1234567", False), (f"dev-{CANDIDATE[:4]}", False), (None, False)],
)
def test_the_release_is_the_manifests_version_or_the_candidates_dev_commit(release: str | None, ok: bool) -> None:
    """release.checkout_version: `v0.5.2` when the checkout is tagged, else `dev-<short>`; `dev-unknown` with no git."""
    assert iv.release_matches(release, "v0.5.2", CANDIDATE)[0] is ok


@pytest.mark.parametrize("release", [None, "dev-unknown"])
def test_a_release_not_recorded_or_unknown_fails_the_version_check(release: str | None) -> None:
    m = candidate()

    class Unrecorded(Fake):
        def release(self) -> str | None:
            return iv.release_of({"data": {} if release is None else {"OSPREY_RELEASE_VERSION": release}})

    failed = [r for r in iv.verify(m, Unrecorded(m)) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and (release or "not recorded") in failed[0].said


@pytest.mark.parametrize("tag", ["unknown", "1234567890abcdef1234567890abcdef12345678", "v0.5.2"])
def test_one_of_ours_tagged_with_another_commit_fails_the_version_check(tag: str) -> None:
    """`unknown`: a render with no git and no OSPREY_BUILT_FROM_SHA (render.git_sha)."""
    m = candidate()

    class Other(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            return {**got, "tag": tag} if got and name == "api" else got

    failed = [r for r in iv.verify(m, Other(m)) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and f"api (tagged {tag}" in failed[0].said


@pytest.mark.parametrize("named", [None, "", "0c1d2e3", "v0.5.2"])
def test_no_full_candidate_commit_named_fails_the_version_check(named: str | None) -> None:
    m = candidate()

    class Unnamed(Fake):
        def candidate(self) -> str | None:
            return named

    failed = [r for r in iv.verify(m, Unnamed(m)) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and "no candidate commit named" in failed[0].said


def test_the_live_reading_takes_the_release_from_ospreyflow_env() -> None:
    env = {"kind": "ConfigMap", "metadata": {"name": "ospreyflow-env"}, "data": {"OSPREY_RELEASE_VERSION": "dev-0c1d2e3"}}
    assert _kind({("configmap", "ospreyflow-env"): env}).release() == "dev-0c1d2e3"
    with pytest.raises(LookupError):
        _kind({("configmap", "ospreyflow-files"): env}).release()


def test_a_cronjob_left_on_the_old_release_fails_the_version_check() -> None:
    m = candidate()

    class OldCron(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            return {**got, "current": False} if got and name == "ospreyflow-backup" else got

    failed = [r for r in iv.verify(m, OldCron(m)) if not r.ok]
    assert [r.entry for r in failed] == ["version"] and "ospreyflow-backup" in failed[0].said


#: Our images as the render writes them: tagged with the commit (render.py `{registry}/{service}:{sha}`), pinned
#: by digest after the push (cloud_platform `_Copies`), so `<repository>:<commit>@<digest>`.
SHA = CANDIDATE
API = f"reg/ospreyflow/api:{SHA}@sha256:aa"


def test_the_candidates_reference_is_the_values_pinned_form_not_the_images_list_tag() -> None:
    values = {"workloads": [
        {"name": "api", "image": API, "initContainers": []},
        {"name": "litellm", "image": "reg/berriai/litellm@sha256:bb",
         "initContainers": [{"name": "litellm-db", "image": "reg/postgres@sha256:cc"}]}],
        "backups": {"image": API, "arcadedb": {"image": "reg/arcadedata/arcadedb@sha256:dd"}}}
    expected = iv.references_from_values(values, "reg")
    assert expected == {"ospreyflow/api": API, "berriai/litellm": "reg/berriai/litellm@sha256:bb",
                        "postgres": "reg/postgres@sha256:cc", "arcadedata/arcadedb": "reg/arcadedata/arcadedb@sha256:dd"}
    got = iv.read_workload(_deployment({"observedGeneration": 4, "readyReplicas": 1}, API), "reg", expected=expected)
    assert got["current"]


def test_a_correct_candidate_in_the_renders_shape_passes_the_version_check() -> None:
    """The review of 1f06074, must 1: a tag check on `:<commit>` failed every real install."""
    m = candidate()
    expected = {"ospreyflow/api": API}
    read = iv.read_workload(_deployment({"observedGeneration": 4, "replicas": 1, "readyReplicas": 1, "updatedReplicas": 1,
                                         "availableReplicas": 1}, API), "reg", expected=expected)

    assert read["tag"] == CANDIDATE

    class Rendered(Fake):
        def workload(self, name: str) -> dict[str, Any] | None:
            got = super().workload(name)
            ours = got and got["tag"] is not None
            return {**got, "current": read["current"], "tag": read["tag"] if ours else None} if got else got

    assert [r for r in iv.verify(m, Rendered(m)) if not r.ok and r.entry == "version"] == []


def test_an_init_container_on_the_old_reference_is_not_the_candidate() -> None:
    expected = {"berriai/litellm": "reg/berriai/litellm@sha256:bb", "postgres": "reg/postgres@sha256:new"}
    spec = {"containers": [{"name": "litellm", "image": "reg/berriai/litellm@sha256:bb"}],
            "initContainers": [{"name": "litellm-db", "image": "reg/postgres@sha256:old"}]}
    assert iv.current(spec, "reg", expected) is False
    spec["initContainers"][0]["image"] = "reg/postgres@sha256:new"
    assert iv.current(spec, "reg", expected) is True
    # a main container the render never pinned is not the candidate, whatever the rest
    assert iv.current({"containers": [{"name": "x", "image": "reg/stranger@sha256:zz"}]}, "reg", expected) is False


def test_a_second_container_on_the_old_reference_is_not_the_candidate() -> None:
    expected = {"ospreyflow/api": API, "arcadedata/arcadedb": "reg/arcadedata/arcadedb@sha256:dd"}
    spec = {"containers": [{"name": "restore-analytics", "image": API},
                           {"name": "restore-graph", "image": "reg/arcadedata/arcadedb@sha256:old"}]}
    assert iv.current(spec, "reg", expected) is False


def test_the_shape_is_read_from_the_deployed_configuration() -> None:
    def cm(text: str) -> dict[str, Any]:
        return {"data": {"osprey.yaml": text}}

    assert iv.shape_of(cm("profile: cloud-platform\ncloud_platform:\n  shape: poc\n")) == "poc"
    assert iv.shape_of(cm("profile: cloud-platform\ncloud_platform: {}\n")) == "standard"  # left out at its default
    with pytest.raises(LookupError):
        iv.shape_of(None)


def test_an_offline_node_is_no_evidence_that_egress_is_blocked() -> None:
    """With no route out at all, the unlisted address times out as Calico's refusal would (N5)."""
    m = candidate()
    fake = Fake(m)
    fake.offline = True
    failed = [r for r in iv.verify(m, fake) if not r.ok]
    assert [r.entry for r in failed] == [iv.UNLISTED_HOST_CHECK] and "outside" in failed[0].said


def test_restore_graph_is_checked_even_when_steps_does_not_name_it() -> None:
    m = candidate()
    m["jobs"]["ospreyflow-restore-<set>"]["steps"].remove("restore-graph")

    class Wrong(Fake):
        def job(self, name: str) -> dict[str, Any] | None:
            got = super().job(name)
            if got and name == "ospreyflow-restore-<set>":
                got = copy.deepcopy(got)
                got["steps"]["restore-graph"]["image"] = "ospreyflow/api"
            return got

    failed = [r.entry for r in iv.verify(m, Wrong(m)) if not r.ok]
    assert failed == ["jobs.ospreyflow-restore-<set>"]


def test_a_check_that_exits_as_r1s_shell_does_is_a_failure_not_a_stop() -> None:
    """r1_kind.sh raises SystemExit on a failed command (a BaseException, not an Exception)."""
    m = candidate()

    class Exits(Fake):
        def rds_setting(self, name: str) -> str | None:
            raise SystemExit("kubectl -n platform-managed exec: exit 1")

    results = iv.verify(m, Exits(m))
    assert [r.entry for r in results if not r.ok] == ["managed.rds"]
    assert len(results) == len(iv.plan(m))


def test_max_connections_unlike_the_manifest_fails() -> None:
    m = candidate()

    class Low(Fake):
        def rds_setting(self, name: str) -> str | None:
            return "750" if name == "max_connections" else super().rds_setting(name)

    failed = [r for r in iv.verify(m, Low(m)) if not r.ok]
    assert [r.entry for r in failed] == ["managed.rds"] and "750" in failed[0].said


def test_a_database_reached_only_by_a_stranger_fails() -> None:
    m = candidate()

    class Stranger(Fake):
        def database_readers(self, database: str) -> set[str]:
            return {"workspace"} if database == "litellm" else super().database_readers(database)

    failed = [r.entry for r in iv.verify(m, Stranger(m)) if not r.ok]
    assert failed == ["managed.rds.databases.litellm"]


def test_a_check_that_raises_is_a_failure_not_a_stop() -> None:
    m = candidate()

    class Raises(Fake):
        def bucket_objects(self, bucket: str) -> int:
            if bucket == "media":
                raise RuntimeError("the stand-in answered 503")
            return super().bucket_objects(bucket)

    results = iv.verify(m, Raises(m))
    failed = [r for r in results if not r.ok]
    assert [r.entry for r in failed] == ["managed.s3.buckets.media"] and "503" in failed[0].said
    assert len(results) == len(iv.plan(m))


# ---- the kind observer's readings, in the shapes kubectl and the stores really answer ------------


def test_a_deployment_kubectl_reports_with_no_ready_replicas_is_not_ready() -> None:
    """kubectl leaves `readyReplicas` out altogether when none is ready (not 0)."""
    obj = {"kind": "Deployment", "spec": {"replicas": 1, "template": {"spec": {"containers": [
        {"name": "api", "image": f"localhost:5001/ospreyflow/api:{CANDIDATE}@sha256:ab",
         "resources": {"requests": {"cpu": "500m", "memory": "2Gi"}, "limits": {"cpu": "2", "memory": "4Gi"}},
         "readinessProbe": {"exec": {"command": ["true"]}}}]}}},
        "status": {"replicas": 1, "unavailableReplicas": 1}}
    got = iv.read_workload(obj, "localhost:5001", expected={})
    assert got["ready"] == 0 and got["desired"] == 1 and got["image"] == "ospreyflow/api" and got["probe"]


def test_readers_are_the_workloads_whose_pods_hold_the_sessions() -> None:
    pods = [
        {"metadata": {"labels": {"app.kubernetes.io/name": "api"}}, "status": {"phase": "Running", "podIP": "10.244.0.7"}},
        {"metadata": {"labels": {"app.kubernetes.io/name": "litellm"}}, "status": {"phase": "Running", "podIP": "10.244.0.9"}},
        {"metadata": {"labels": {}}, "status": {"phase": "Running", "podIP": "10.244.0.11"}},
    ]
    rows = "ospreyflow|10.244.0.7\nlitellm|10.244.0.9\nospreyflow|\npostgres|10.244.0.11\n"
    assert iv.readers_from_sessions(rows, "ospreyflow", pods) == {"api"}
    assert iv.readers_from_sessions(rows, "litellm", pods) == {"litellm"}
    assert iv.readers_from_sessions(rows, "superset", pods) == set()


def test_cache_readers_from_valkeys_client_list() -> None:
    pods = [{"metadata": {"labels": {"app.kubernetes.io/name": "worker"}}, "status": {"phase": "Running", "podIP": "10.244.0.8"}}]
    listing = ("id=3 addr=10.244.0.8:51234 laddr=10.244.0.20:6379 fd=8 name= db=0 cmd=brpop\n"
               "id=4 addr=127.0.0.1:40000 laddr=127.0.0.1:6379 fd=9 name= db=0 cmd=client|list\n")
    assert iv.readers_from_client_list(listing, pods) == {"worker"}


def test_a_job_whose_step_failed_reads_as_failed() -> None:
    job = {"metadata": {"name": "ospreyflow-restore-20261125"}, "status": {"failed": 1},
           "spec": {"template": {"spec": {
               "initContainers": [{"name": "verify", "image": "r/ospreyflow/api:x"},
                                  {"name": "restore-graph", "image": "r/arcadedata/arcadedb:26.10.1",
                                   "resources": {"requests": {"cpu": "1"}, "limits": {"cpu": "2"}}}],
               "containers": [{"name": "restore-analytics", "image": "r/ospreyflow/api:x", "resources": {}}]}}}}
    pod = {"status": {"initContainerStatuses": [
        {"name": "verify", "state": {"terminated": {"exitCode": 0}}},
        {"name": "restore-graph", "state": {"terminated": {"exitCode": 2}}}],
        "containerStatuses": [{"name": "restore-analytics", "state": {"waiting": {"reason": "PodInitializing"}}}]}}
    got = iv.read_job(job, [pod], "r")
    assert got["succeeded"] == 0
    assert got["steps"]["verify"]["exit_code"] == 0
    assert got["steps"]["restore-graph"]["exit_code"] == 2
    assert got["steps"]["restore-graph"]["image"] == "arcadedata/arcadedb"
    assert got["steps"]["restore-analytics"]["exit_code"] is None


def test_the_entra_standin_log_names_the_clients_it_granted() -> None:
    """The line platform's signing stand-in writes (lane/platform-v052-standin 73f85ee, r1_kind_servers.py
    `_granted`), its access lines beside it; a refusal writes none."""
    log = ("entra-standin: \"GET /t/v2.0/.well-known/openid-configuration HTTP/1.1\" 200 -\n"
           "entra-standin: granted authorization_code client=aaaa audience=api://bbbb\n"
           "entra-standin: refused client_credentials client=dddd invalid_client\n"
           "entra-standin: granted client_credentials client=eeee audience=api://bbbb\n")
    assert iv.granted_clients(log) == {"aaaa", "eeee"}
    assert iv.granted_audiences(log) == {"api://bbbb"}


def test_a_rollout_reads_from_kubectls_status() -> None:
    got = iv.read_workload(_deployment(STUCK_STATUS), "r", expected={"ospreyflow/api": "r/ospreyflow/api@sha256:new"})
    assert (got["replicas"], got["updated"], got["ready"], got["available"], got["unavailable"]) == (2, 1, 1, 1, 1)
    assert got["settled"] and got["current"]
    behind = _deployment({**STUCK_STATUS, "observedGeneration": 3})
    assert not iv.read_workload(behind, "r", expected={})["settled"]
    old = iv.read_workload(_deployment(STUCK_STATUS), "r", expected={"ospreyflow/api": "r/ospreyflow/api@sha256:old"})
    assert not old["current"]


class FakeR1:
    """r1_kind's kubectl as the cluster answers it: empty output for NotFound (check=False)."""

    NS, MANAGED = "ospreyflow-poc", "platform-managed"

    def __init__(self, objects: dict[tuple[str, ...], Any]) -> None:
        self.objects = objects

    def kubectl(self, *args: str, check: bool = True, stdin: str | None = None) -> str:
        import json

        key = tuple(a for a in args if a not in ("-n", self.NS, "get", "-o", "json"))
        return json.dumps(self.objects[key]) if key in self.objects else ""


def _kind(objects: dict[tuple[str, ...], Any]) -> Any:
    return iv.KindDeployment(FakeR1(objects), registry="r", expected={"ospreyflow/api": "r/ospreyflow/api@sha256:new"},
                             clients={}, api_audiences=set(), bucket_prefix="p-", jobs=["ospreyflow-restore-<set>", "ospreyflow-restore-claims-<set>"])


def test_a_statefulset_is_found_when_no_deployment_has_the_name() -> None:
    sts = {**_deployment({"observedGeneration": 4, "readyReplicas": 1}), "kind": "StatefulSet"}
    assert _kind({("statefulset", "api"): sts}).workload("api")["kind"] == "StatefulSet"
    assert _kind({}).workload("api") is None


def test_the_restore_reading_takes_its_own_job_and_its_pods() -> None:
    def job(name: str, ok: int) -> dict[str, Any]:
        return {"metadata": {"name": name}, "status": {"succeeded": ok},
                "spec": {"template": {"spec": {"containers": [{"name": "restore-analytics", "image": "r/ospreyflow/api@sha256:new"}]}}}}

    pod = {"metadata": {"labels": {"job-name": "ospreyflow-restore-1"}},
           "status": {"containerStatuses": [{"name": "restore-analytics", "state": {"terminated": {"exitCode": 0}}}]}}
    kind = _kind({("jobs",): {"items": [job("ospreyflow-restore-claims-1", 1), job("ospreyflow-restore-1", 1)]},
                  ("pods",): {"items": [pod]}})
    got = kind.job("ospreyflow-restore-<set>")
    assert got["succeeded"] == 1 and got["steps"]["restore-analytics"]["exit_code"] == 0 and got["current"]


@pytest.mark.parametrize(
    ("out", "answer"),
    [("open\n", True), ("blocked\n", False), ("", None), ("dns\n", None),
     ("error: unable to upgrade connection: container not found", None)],
)
def test_an_egress_probe_answers_open_blocked_or_raises(out: str, answer: bool | None) -> None:
    """A failed exec or an unresolved name is no answer about the policy: never a pass for the
    unlisted-host check (the review of 816922f, item 7)."""
    if answer is None:
        with pytest.raises(LookupError):
            iv.probe_answer(out)
    else:
        assert iv.probe_answer(out) is answer


def test_the_unlisted_host_is_an_address_so_dns_is_not_the_question() -> None:
    import ipaddress

    ipaddress.ip_address(iv.UNLISTED_HOST)


def _cron_job(name: str, command: list[str], image: str, succeeded: int, owner: str = "ospreyflow-backup") -> dict[str, Any]:
    return {"metadata": {"name": name, "ownerReferences": [{"kind": "CronJob", "name": owner}]},
            "spec": {"template": {"spec": {"containers": [{"name": "backup", "image": image, "command": command}]}}},
            "status": {"succeeded": succeeded}}


def test_a_cronjobs_runs_count_only_its_own_command_at_the_candidates_image() -> None:
    cron = {"spec": {"jobTemplate": {"spec": {"template": {"spec": {"containers": [
        {"name": "backup", "image": f"r/ospreyflow/api:{CANDIDATE}@sha256:new", "command": ["python", "-m", "x", "run"]}]}}}}}}
    jobs = [
        _cron_job("ospreyflow-backup-1", ["python", "-m", "x", "run"], f"r/ospreyflow/api:{OLD_COMMIT}@sha256:old", 1),  # before the upgrade
        _cron_job("backup-sets-1", ["python", "-m", "x", "sets"], f"r/ospreyflow/api:{CANDIDATE}@sha256:new", 1),  # the runbook's listing
        _cron_job("ospreyflow-backup-2", ["python", "-m", "x", "run"], f"r/ospreyflow/api:{CANDIDATE}@sha256:new", 0),  # failed
    ]
    assert iv.cron_runs(cron, jobs, "ospreyflow-backup") == 0
    jobs.append(_cron_job("ospreyflow-backup-3", ["python", "-m", "x", "run"], f"r/ospreyflow/api:{CANDIDATE}@sha256:new", 1))
    assert iv.cron_runs(cron, jobs, "ospreyflow-backup") == 1


def test_a_restore_template_never_takes_the_claims_restores_runs() -> None:
    names = ["ospreyflow-restore-claims-20261125", "ospreyflow-restore-20261125", "ospreyflow-backup-9"]
    jobs = ["ospreyflow-restore-<set>", "ospreyflow-restore-claims-<set>"]
    assert iv.runs_of_template("ospreyflow-restore-<set>", names, jobs) == ["ospreyflow-restore-20261125"]
    assert iv.runs_of_template("ospreyflow-restore-claims-<set>", names, jobs) == ["ospreyflow-restore-claims-20261125"]


def test_only_running_pods_name_a_reader() -> None:
    pods = [
        {"metadata": {"labels": {"app.kubernetes.io/name": "api"}}, "status": {"phase": "Running", "podIP": "10.244.0.7"}},
        # listed after the running pod, as kubectl may order them: it must not take the address over
        {"metadata": {"labels": {"app.kubernetes.io/name": "ospreyflow-backup"}}, "status": {"phase": "Succeeded", "podIP": "10.244.0.7"}},
    ]
    assert iv.readers_from_sessions("ospreyflow|10.244.0.7\n", "ospreyflow", pods) == {"api"}


def test_the_newest_successful_run_is_read_whatever_kubectls_order() -> None:
    def job(name: str, created: str, image: str) -> dict[str, Any]:
        return {"metadata": {"name": name, "creationTimestamp": created}, "status": {"succeeded": 1},
                "spec": {"template": {"spec": {"containers": [{"name": "restore-analytics", "image": image}]}}}}

    # v0.5.1's run sorts after the candidate's by name; it is the older one
    jobs = [job("ospreyflow-restore-a", "2026-11-25T10:00:00Z", "r/ospreyflow/api@sha256:new"),
            job("ospreyflow-restore-b", "2026-11-20T10:00:00Z", "r/ospreyflow/api@sha256:old")]
    got = _kind({("jobs",): {"items": jobs}, ("pods",): {"items": []}}).job("ospreyflow-restore-<set>")
    assert got["current"] is True


def test_the_opensearch_reader_check_reads_each_readers_probe() -> None:
    signed = {"signing": "sigv4", "alias": "ospreyflow-poc", "signed": {"status": 200, "count": 12},
              "unsigned": {"status": 403, "error": "AuthorizationException(403, 'User: anonymous is not authorized ...')"}}

    class ExecR1(FakeR1):
        def __init__(self, answer: dict[str, Any] | str) -> None:
            super().__init__({})
            self.answer, self.asked = answer, []

        def kubectl(self, *args: str, check: bool = True, stdin: str | None = None) -> str:
            import json

            if "exec" in args:
                self.asked.append(args[args.index("exec") + 1])
                assert iv.SEARCH_PROBE in args
                return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)
            return super().kubectl(*args, check=check, stdin=stdin)

    def kind(answer: dict[str, Any] | str) -> Any:
        return iv.KindDeployment(ExecR1(answer), registry="r", expected={}, clients={}, api_audiences=set(),
                                 bucket_prefix="p-", jobs=[])

    ok = kind(signed)
    assert ok.store_readers("opensearch") == {"api"} and ok.r1.asked == ["deployment/api"]
    with pytest.raises(LookupError, match="not refused 403"):
        kind({**signed, "unsigned": {"status": 200, "count": 12}}).store_readers("opensearch")
    with pytest.raises(LookupError, match="no answer"):
        kind("").store_readers("opensearch")


def _probe_line(**change: Any) -> str:
    import json

    line = {"signing": "sigv4", "alias": "ospreyflow-poc", "signed": {"status": 200, "count": 12},
            # the domain's refusal as the stand-in answers it (platform, 6998234): 403 with its JSON message
            # as opensearch-py's AuthorizationException reads, run against the stand-in's words (gates/search-probe-real.txt)
            "unsigned": {"status": 403, "error": "AuthorizationException(403, '{\"message\": \"User: anonymous is not authorized to "
                                                 "perform: es:ESHttpGet on resource: arn:aws:es:eu-west-2:123456789012:domain/ospreyflow-poc-search/\"}')"}}
    return json.dumps({**line, **change}) + "\n"  # stdout alone: r1_kind.sh keeps no stderr


@pytest.mark.parametrize(
    ("change", "said"),
    [({}, None),
     ({"signing": "none"}, "not sigv4"),
     ({"signed": {"status": 403, "error": "refused"}}, "was refused: 403"),
     ({"signed": {"status": None, "error": "ConnectionError"}}, "was refused: None"),
     ({"signed": {"status": 200, "count": 0}}, "holds no documents"),
     ({"unsigned": {"status": 200, "count": 12}}, "not refused 403"),
     ({"unsigned": {"status": None, "error": "ConnectionError"}}, "not refused 403"),
     # a 403 that is not the domain's refusal (an S3 XML refusal: the request reached the stand-in by another name)
     ({"unsigned": {"status": 403, "error": "AuthorizationException(403, 'SignatureDoesNotMatch')"}}, "not refused 403"),
     ({"failed": "ModuleNotFoundError: No module named 'opensearchpy'"}, "failed in the reader's pod: ModuleNotFoundError")],
)
def test_a_search_reader_signs_finds_documents_and_is_refused_unsigned(change: dict[str, Any], said: str | None) -> None:
    ok, text = iv.search_answer(_probe_line(**change))
    assert ok is (said is None) and (said is None or said in text), text


@pytest.mark.parametrize("out", ["", "error: unable to upgrade connection: container not found\n"])
def test_a_search_probe_with_no_json_line_is_no_answer(out: str) -> None:
    """What r1's kubectl returns when the exec itself fails: stdout empty, or kubectl's own words."""
    ok, text = iv.search_answer(out)
    assert not ok and "no answer" in text


def test_the_search_probe_prints_one_json_line_whatever_fails() -> None:
    """Run as the pod runs it, where neither opensearch-py nor rules' client is installed here: the reason is the line."""
    import json
    import subprocess

    done = subprocess.run([sys.executable, "-I", "-c", iv.SEARCH_PROBE], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    line = json.loads(done.stdout.strip().splitlines()[-1])
    assert "ModuleNotFoundError" in line["failed"]
    ok, text = iv.search_answer(done.stdout)
    assert not ok and "ModuleNotFoundError" in text


def test_the_search_probe_is_python_and_uses_the_deployments_own_client() -> None:
    compile(iv.SEARCH_PROBE, "<probe>", "exec")
    assert "from services.search_index.client import SearchIndexConfig, search_client" in iv.SEARCH_PROBE
    assert "client = search_client(config)" in iv.SEARCH_PROBE


def test_an_egress_placeholder_fails_without_probing() -> None:
    m = candidate()
    m["egress"]["<the namespace's OpenSearch domain endpoint>"] = {}
    failed = [r for r in iv.verify(m, Fake(m)) if not r.ok]
    assert [r.entry for r in failed] == ["egress.<the namespace's OpenSearch domain endpoint>"]
    assert "placeholder" in failed[0].said


def test_a_cronjob_whose_template_is_still_the_old_release_reads_as_not_current() -> None:
    def cron(image: str) -> dict[str, Any]:
        return {"spec": {"schedule": "15 2 * * *", "jobTemplate": {"spec": {"template": {"spec": {"containers": [
            {"name": "backup", "image": image, "command": ["run"]}]}}}}}}

    old = _kind({("cronjob", "ospreyflow-backup"): cron(f"r/ospreyflow/api:{OLD_COMMIT}@sha256:old"), ("jobs",): {"items": []}})
    new = _kind({("cronjob", "ospreyflow-backup"): cron("r/ospreyflow/api@sha256:new"), ("jobs",): {"items": []}})
    assert old.job("ospreyflow-backup")["current"] is False
    assert new.job("ospreyflow-backup")["current"] is True


# ---- the live half's own wiring ---------------------------------------------------------------------------


def _env_seen(script: Path, args: list[str], tmp: Path) -> dict[str, str]:
    """Run `script` as on the server, from a folder whose `.venv/bin/python` only reports what it was given."""
    import json
    import os
    import subprocess

    core = tmp / "core"
    (core / ".venv" / "bin").mkdir(parents=True)
    stub = core / ".venv" / "bin" / "python"
    stub.write_text('#!/bin/sh\nexec "$(command -v python3)" -c \'import json,os,sys; print(json.dumps({**{k: os.environ.get(k, "") for k in ("PATH", "KUBECONFIG", "OSPREY_PLATFORM_FOLDERS", "PYTHONPATH")}, "ARGV": sys.argv[1:]}))\' "$@"\n')
    stub.chmod(0o755)
    env = {"HOME": str(tmp / "home"), "PATH": os.environ["PATH"],
           **{k: v for k, v in os.environ.items() if k == "OSPREY_V052_R1_GATES"}}
    done = subprocess.run(["bash", str(script), *args], cwd=core, env=env, capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_live_wrapper_gives_install_verify_r1s_own_environment(tmp_path: Path) -> None:
    """The review of b6da153, must 1: `r1_kind.sh py` runs r1_kind.py only; the wrapper must set what it sets."""
    here = Path(iv.__file__).resolve().parent
    ours = _env_seen(here / "verify_live.sh", [], tmp_path / "a")
    import os

    gates = Path(os.environ.get("OSPREY_V052_R1_GATES") or here.parents[1] / "platform" / "gates")
    r1 = _env_seen(gates / "r1_kind.sh", ["py", "x"], tmp_path / "b")
    for key in ("KUBECONFIG", "OSPREY_PLATFORM_FOLDERS"):
        assert ours[key] == r1[key].replace(str(tmp_path / "b"), str(tmp_path / "a")), key
    assert ours["PATH"].split(":")[0] == r1["PATH"].split(":")[0].replace(str(tmp_path / "b"), str(tmp_path / "a"))
    assert Path(ours["ARGV"][0]) == here / "install_verify.py" and ours["ARGV"][1:] == ["verify", "--candidate", "auto"]
    named = _env_seen(here / "verify_live.sh", ["--candidate", "abc", "--allow-pending"], tmp_path / "c")
    assert named["ARGV"][1:] == ["verify", "--candidate", "abc", "--allow-pending"]


def _copy_repo(tmp: Path) -> tuple[Any, str, str, str]:
    """A stack_lease copy: each run commits afresh (`commit --allow-empty`) on top of the last."""
    import subprocess

    def git(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(tmp), *args], capture_output=True, text=True, check=False,
                              env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x.invalid", "GIT_COMMITTER_NAME": "t",
                                   "GIT_COMMITTER_EMAIL": "t@x.invalid", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"})
        return done.stdout if done.returncode == 0 else ""

    tmp.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    (tmp / "f").write_text("v0.5.1's files\n")
    git("add", "-A"), git("commit", "-q", "-m", "the copy sent for this run")
    old = git("rev-parse", "HEAD").strip()
    (tmp / "f").write_text("the candidate's files\n")
    git("add", "-A"), git("commit", "-q", "--allow-empty", "-m", "the copy sent for this run")
    upgrade = git("rev-parse", "HEAD").strip()
    git("add", "-A"), git("commit", "-q", "--allow-empty", "-m", "the copy sent for this run")
    return git, old, upgrade, git("rev-parse", "HEAD").strip()


def test_the_candidate_is_the_kept_renders_commit_with_this_copys_files(tmp_path: Path) -> None:
    git, _old, upgrade, head = _copy_repo(tmp_path)
    assert head != upgrade
    assert iv.candidate_from_copy([upgrade, upgrade, None], git) == upgrade


@pytest.mark.parametrize(
    ("which", "said"),
    [("old", "other files"), ("absent", "not in this copy's history"), ("two", "not one commit"),
     ("unknown", "not one commit"), ("none", "not one commit")],
)
def test_a_kept_render_not_of_this_copys_files_names_no_candidate(tmp_path: Path, which: str, said: str) -> None:
    git, old, upgrade, _ = _copy_repo(tmp_path)
    tags = {"old": [old], "absent": ["1" * 40], "two": [old, upgrade], "unknown": ["unknown"], "none": [None]}[which]
    with pytest.raises(LookupError, match=said):
        iv.candidate_from_copy(tags, git)


def test_the_unsigned_probe_takes_the_signed_clients_own_transport() -> None:
    """The review of b6da153, item 4: the same hosts, connection class, TLS and timeout, less the signer."""
    assert "client.transport.kwargs.items() if k != \"http_auth\"" in iv.SEARCH_PROBE
    assert "hosts=client.transport.hosts, connection_class=client.transport.connection_class" in iv.SEARCH_PROBE


def _have_search_client() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("opensearchpy", "botocore", "services.search_index"))


@pytest.mark.skipif(not _have_search_client(), reason="rules' search client and opensearch-py are not in this tree yet")
def test_the_search_probe_against_a_domain_that_refuses_unsigned(tmp_path: Path) -> None:  # pragma: no cover
    """The probe as the pod runs it, the deployment's own client against a server answering as the domain's
    stand-in does: signed answered, unsigned refused 403 in the domain's JSON words."""
    import json
    import os
    import subprocess
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Domain(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.headers.get("Authorization"):
                body, status = {"count": 3, "_shards": {}}, 200
            else:
                body, status = {"message": "User: anonymous is not authorized to perform: es:ESHttpGet"}, 403
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_POST = do_GET

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Domain)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {**os.environ, "OPENSEARCH_URL": f"http://127.0.0.1:{server.server_port}", "OPENSEARCH_SIGNING": "sigv4",
           "OPENSEARCH_REGION": "eu-west-2", "AWS_ACCESS_KEY_ID": "AKIDEXAMPLE", "AWS_SECRET_ACCESS_KEY": "x"}
    done = subprocess.run([sys.executable, "-c", iv.SEARCH_PROBE], capture_output=True, text=True, env=env, check=False)
    server.shutdown()
    ok, said = iv.search_answer(done.stdout)
    assert ok, (said, done.stderr[-500:])
