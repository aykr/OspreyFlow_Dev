"""The decommission's AWS steps (`DECOMMISSION.md` steps 6 and 8, the platform's blocks; ADR-148
Amendment 5 point 14), run under bash as written, against a stand-in `aws` on the path that answers
and refuses as AWS does (the orchestrator's confirmation of P7b, item 3; rule 15's fixture rule):

- `delete-objects` refuses more than 1000 keys (`MalformedXML`), and answers exit 0 with per-key
  `Errors` when it deletes only some;
- `list-object-versions`' `--max-items` counts the versions alone, never the delete markers;
- `batch-delete-image` answers exit 0 with `failures` (an image an index still references);
- `head-bucket` answers 404 for a bucket that is not there and 403 for one it may not see;
- any listing can fail outright.

Each branch the blocks take is shown: a bucket of 1200 delete markers emptied in calls under 1000
keys, and every refusal stopping the step (never looping: each run has a deadline).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness.cloud_platform.runbooks import command_blocks
from harness.cloud_platform.terraform import BUCKETS
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

PREFIX = "ospreyflow-poc-1a2b3c4d-"

#: The stand-in `aws`: its state in `$STUB_STATE` (JSON), every call appended to `calls`.
STUB = r"""
import json, os, re, sys
path = os.environ["STUB_STATE"]
state = json.load(open(path))
argv = sys.argv[1:]
state["calls"].append(argv)
def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default
def save():
    json.dump(state, open(path, "w"))
def refuse(code, said):
    save(); sys.stderr.write(said + "\n"); sys.exit(code)
service, op = argv[0], argv[1]
if [service, op] in state["fail"]:
    refuse(254, f"An error occurred (InternalError) when calling {op}")
if (service, op) == ("s3api", "list-object-versions"):
    bucket = state["buckets"].setdefault(arg("--bucket"), {"Versions": [], "DeleteMarkers": []})
    query = arg("--query")
    kind, cap = re.search(r"Objects: (Versions|DeleteMarkers)(?:\[:(\d+)\])?", query).groups()
    items = bucket[kind]
    if kind == "Versions" and "--max-items" in argv:  # botocore: it counts the versions alone
        items = items[: int(arg("--max-items"))]
    if cap:
        items = items[: int(cap)]
    print(json.dumps({"Objects": items or None})); save(); sys.exit(0)
if (service, op) == ("s3api", "delete-objects"):
    keys = json.load(open(arg("--delete").removeprefix("file://")))["Objects"]
    if len(keys) > 1000:
        refuse(254, "An error occurred (MalformedXML) when calling the DeleteObjects operation")
    bucket = state["buckets"][arg("--bucket")]
    errors = []
    for key in keys:
        if state.get("noop_delete"):
            continue  # answers no errors and deletes nothing
        if state["refuse_keys"]:
            errors.append({"Key": key["Key"], "Code": "AccessDenied"})
            continue
        for kind in ("Versions", "DeleteMarkers"):
            bucket[kind] = [v for v in bucket[kind] if v != key]
    print(len(errors)); save(); sys.exit(0)  # --query 'length(Errors || `[]`)' --output text
if (service, op) == ("ecr", "list-images"):
    status = arg("--filter").split("=")[1]
    images = [i for i in state["images"].get(arg("--repository-name"), []) if i["status"] == status]
    print(json.dumps([{"imageDigest": i["digest"]} for i in images[:100]])); save(); sys.exit(0)
if (service, op) == ("ecr", "batch-delete-image"):
    ids = {i["imageDigest"] for i in json.loads(arg("--image-ids"))}
    held = state["images"][arg("--repository-name")]
    referenced = {i["digest"] for i in held if i["status"] == "TAGGED"}
    failures = [d for d in ids if d in state["children"] and state["children"][d] in referenced]
    state["images"][arg("--repository-name")] = [
        i for i in held if i["digest"] not in ids or i["digest"] in failures
    ]
    print(len(failures)); save(); sys.exit(0)  # --query 'length(failures)' --output text
if (service, op) == ("s3api", "head-bucket"):
    code = state["head"].get(arg("--bucket"), 404)
    if code == 200:
        save(); sys.exit(0)
    refuse(254, f"An error occurred ({code}) when calling the HeadBucket operation: "
                + ("Not Found" if code == 404 else "Forbidden"))
if (service, op) == ("sts", "get-caller-identity"):
    print("210987654321"); save(); sys.exit(0)
if (service, op) == ("ec2", "describe-volumes"):
    print(json.dumps({"Volumes": []})); save(); sys.exit(0)
refuse(252, f"the stand-in does not answer {service} {op}")
"""


@pytest.fixture(scope="module")
def decommission() -> str:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    return render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["DECOMMISSION.md"]


def _block(text: str, marker: str) -> str:
    return next(b for b in command_blocks(text, on_the_platform=True) if marker in b)


def _run(tmp_path: Path, block: str, state: dict[str, Any]) -> tuple[int, str, dict[str, Any]]:
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    stub = bin_ / "aws"
    stub.write_text(f"#!{sys.executable}\n{STUB}", encoding="utf-8")
    stub.chmod(0o755)
    full = {"calls": [], "fail": [], "buckets": {}, "refuse_keys": False, "images": {},
            "children": {}, "head": {}, **state}  # fmt: skip
    full["fail"] = [list(f) for f in full["fail"]]
    (tmp_path / "state.json").write_text(json.dumps(full), encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    (tmp_path / "tofu-state.txt").write_text("", encoding="utf-8")
    environment = {
        "PATH": f"{bin_}:/usr/bin:/bin", "STUB_STATE": str(tmp_path / "state.json"),
        "REGION": "eu-west-2", "PREFIX": PREFIX, "WORK": str(work), "PY": sys.executable,
        "NS": "ospreyflow-poc", "STATE": str(tmp_path / "tofu-state.txt"),
        "CLUSTER_ACCOUNT": "210987654321", "HOME": str(tmp_path),
    }  # fmt: skip
    done = subprocess.run(["bash", "-c", block], env=environment, capture_output=True,
                          text=True, timeout=60, check=False)  # fmt: skip
    after = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    return done.returncode, done.stdout + done.stderr, after


def _keys(n: int, kind: str) -> list[dict[str, str]]:
    return [{"Key": f"{kind}/{i}", "VersionId": f"v{i}"} for i in range(n)]


def _calls(after: dict[str, Any], op: str) -> list[list[str]]:
    return [c for c in after["calls"] if c[1] == op]


def test_every_version_and_every_delete_marker_go_in_calls_under_a_thousand_keys(
    tmp_path: Path, decommission: str
) -> None:
    """1200 delete markers and 700 versions in the versioned bucket: each delete under 1000 keys
    (the delete markers sliced in the query, since `--max-items` counts the versions alone)."""
    media = f"{PREFIX}media"
    code, said, after = _run(tmp_path, _block(decommission, "delete-objects"), {
        "buckets": {media: {"Versions": _keys(700, "v"), "DeleteMarkers": _keys(1200, "m")}},
    })  # fmt: skip
    assert code == 0, said
    assert after["buckets"][media] == {"Versions": [], "DeleteMarkers": []}
    # The stand-in refuses a delete of more than 1000 keys, so each was under it; and the delete
    # markers, which `--max-items` does not count, took three calls of five hundred or fewer.
    assert len(_calls(after, "delete-objects")) >= 4  # 700 in two, 1200 in three
    for call in after["calls"]:
        assert "--region" in call, call


@pytest.mark.parametrize(
    ("state", "said"),
    [
        ({"refuse_keys": True}, "key(s) refused: stopped"),
        ({"fail": [("s3api", "list-object-versions")]}, "failed: stopped"),
        ({"fail": [("s3api", "delete-objects")]}, "failed: stopped"),
        ({"noop_delete": True}, "are the same after a delete: stopped"),
    ],
    ids=["per-key-errors", "listing-fails", "delete-fails", "nothing-deleted"],
)
def test_a_refused_delete_or_listing_stops_the_step(
    tmp_path: Path, decommission: str, state: dict[str, Any], said: str
) -> None:
    media = f"{PREFIX}media"
    code, out, _ = _run(tmp_path, _block(decommission, "delete-objects"), {
        "buckets": {media: {"Versions": _keys(3, "v"), "DeleteMarkers": []}}, **state,
    })  # fmt: skip
    assert code != 0 and said in out, out


def test_buildx_s_indexes_go_before_the_images_they_hold(tmp_path: Path, decommission: str) -> None:
    """An untagged child an index still references is refused (exit 0, `failures`): the tagged
    indexes go first, then the children, and nothing is refused."""
    repository = "ospreyflow/api"
    images = [{"digest": "sha256:index", "status": "TAGGED"},
              {"digest": "sha256:amd64", "status": "UNTAGGED"}]  # fmt: skip
    code, said, after = _run(tmp_path, _block(decommission, "batch-delete-image"), {
        "images": {repository: images}, "children": {"sha256:amd64": "sha256:index"},
    })  # fmt: skip
    assert code == 0, said
    assert after["images"][repository] == []


def test_an_image_refused_stops_the_step(tmp_path: Path, decommission: str) -> None:
    """A child still referenced by an index the step cannot remove (here, held by a tag the
    listing does not show): `failures` is not empty, and the step stops rather than loops."""
    repository = "ospreyflow/api"
    images = [{"digest": "sha256:amd64", "status": "UNTAGGED"},
              {"digest": "sha256:elsewhere", "status": "TAGGED"}]  # fmt: skip
    state = {"images": {repository: images}, "children": {"sha256:amd64": "sha256:elsewhere"}}
    # Only the untagged pass, as if the index were outside the repository's listing.
    block = _block(decommission, "batch-delete-image").replace(
        "for status in TAGGED UNTAGGED", "for status in UNTAGGED"
    )
    code, out, _ = _run(tmp_path, block, state)
    assert code != 0 and "refused: stopped" in out, out


def test_a_bucket_not_there_is_not_listed_and_one_that_cannot_be_seen_stops(
    tmp_path: Path, decommission: str
) -> None:
    block = _block(decommission, "head-bucket")
    head = {f"{PREFIX}{b}": 404 for b in BUCKETS}
    head[f"{PREFIX}media"] = 200
    code, said, _ = _run(tmp_path, block, {"head": head})
    assert code == 0, said
    listed = (tmp_path / "work" / "buckets.txt").read_text(encoding="utf-8").split()
    assert listed == [f"{PREFIX}media"]
    head[f"{PREFIX}staging"] = 403
    again = tmp_path / "again"
    again.mkdir()
    code, said, _ = _run(again, block, {"head": head})
    assert code != 0 and "could not be checked" in said, said


def test_the_disks_are_listed_with_the_account_and_region_they_were_asked_in(
    tmp_path: Path, decommission: str
) -> None:
    code, said, after = _run(tmp_path, _block(decommission, "describe-volumes"), {})
    assert code == 0, said
    disks = json.loads((tmp_path / "work" / "disks.json").read_text(encoding="utf-8"))
    assert disks == {"Volumes": [], "Account": "210987654321", "Region": "eu-west-2"}
    assert all("--region" in c for c in after["calls"])


def test_the_stand_in_refuses_what_aws_refuses(tmp_path: Path) -> None:
    """The fixture itself, red where AWS is: more than a thousand keys refused."""
    work = tmp_path / "keys.json"
    work.write_text(json.dumps({"Objects": _keys(1001, "k")}), encoding="utf-8")
    block = (
        f"aws s3api delete-objects --region eu-west-2 --bucket {PREFIX}media "
        f'--delete "file://{work}"'
    )
    empty = {f"{PREFIX}media": {"Versions": [], "DeleteMarkers": []}}
    code, said, _ = _run(tmp_path, block, {"buckets": empty})
    assert code == 254 and "MalformedXML" in said
