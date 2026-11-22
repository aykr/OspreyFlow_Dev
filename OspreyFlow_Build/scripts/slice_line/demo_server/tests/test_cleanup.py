"""cleanup.sh (point 7) against a fake Docker and a fake account: it removes only what carries the prefix and the label,
--dry-run removes nothing, the second run lists nothing, and the demo's own container and volume are untouched.

The fake docker answers `ps -a`, `network ls`, `volume ls` and `images` with --filter label=... as the real one does
(only objects carrying that label), and `rm`, `network rm`, `volume rm`, `rmi`, refusing an object that is not there."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from conftest import DEMO

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
f = os.environ["FAKE_DOCKER_STATE"]
s = json.load(open(f))
a = sys.argv[1:]
kinds = {"ps": "container", "network": "network", "volume": "volume", "images": "image", "rm": "container", "rmi": "image"}
if a[0] in ("network", "volume"):
    kind, verb, rest = kinds[a[0]], a[1], a[2:]
else:
    kind, verb, rest = kinds[a[0]], a[0], a[1:]
if verb in ("ps", "ls", "images"):
    label = next(x.split("=", 1)[1] for x in rest if x.startswith("label=")) if any(x.startswith("label=") for x in rest) else None
    for o in s:
        if o["kind"] == kind and (label is None or label in o["labels"]):
            print(o["name"] if kind == "volume" else "%s %s" % (o["id"], o["name"]))
    sys.exit(0)
target = [x for x in rest if not x.startswith("-")][0]
hit = [o for o in s if o["kind"] == kind and target in (o["id"], o["name"])]
if not hit:
    sys.stderr.write("Error: No such object\n"); sys.exit(1)
s.remove(hit[0]); json.dump(s, open(f, "w"))
'''
FAKE_ID = r'''#!/bin/sh
if [ "$1" = "-u" ] && [ -n "$2" ]; then grep -qx "$2" "$FAKE_USERS" && { echo 1500; exit 0; }; exit 1; fi
if [ "$1" = "-nG" ]; then echo "$2"; exit 0; fi
exec /usr/bin/id "$@"
'''
FAKE_LOGINCTL = '#!/bin/sh\necho "loginctl $*" >> "$FAKE_CALLS"\n[ "$1" = show-user ] && { grep -qx "$2" "$FAKE_USERS"; exit $?; }\nexit 0\n'
FAKE_USERDEL = '#!/bin/sh\necho "userdel $*" >> "$FAKE_CALLS"\ngrep -vx "$1" "$FAKE_USERS" > "$FAKE_USERS.new"; mv "$FAKE_USERS.new" "$FAKE_USERS"\n'
FAKE_SYSTEMCTL = '#!/bin/sh\necho "systemctl $*" >> "$FAKE_CALLS"\n'
FAKE_NFT = ('#!/bin/sh\necho "nft $*" >> "$FAKE_CALLS"\n'
            'if [ "$1" = list ]; then [ -f "$FAKE_TABLE" ]; exit $?; fi\n'
            'if [ "$1" = delete ]; then rm -f "$FAKE_TABLE"; exit 0; fi\nexit 1\n')
STATE = [
    {"kind": "container", "id": "c1", "name": "osprey-early-job", "labels": ["osprey.early=1"]},
    {"kind": "container", "id": "c2", "name": "demo-web", "labels": []},
    {"kind": "container", "id": "c3", "name": "osprey-early-stray", "labels": []},  # the prefix, not the label
    {"kind": "container", "id": "c4", "name": "demo-db", "labels": ["osprey.early=1"]},  # the label, not the prefix
    {"kind": "network", "id": "n1", "name": "osprey-early-net", "labels": ["osprey.early=1"]},
    {"kind": "network", "id": "n2", "name": "demo-net", "labels": []},
    {"kind": "volume", "id": "osprey-early-vol", "name": "osprey-early-vol", "labels": ["osprey.early=1"]},
    {"kind": "volume", "id": "demo-data", "name": "demo-data", "labels": []},
    {"kind": "volume", "id": "demo-cache", "name": "demo-cache", "labels": ["osprey.early=1"]},  # the label alone
    {"kind": "image", "id": "i1", "name": "osprey-early-img:1", "labels": ["osprey.early=1"]},
    {"kind": "image", "id": "i2", "name": "postgres:16", "labels": []},
]
UNRELATED = {"demo-web", "osprey-early-stray", "demo-db", "demo-net", "demo-data", "demo-cache", "postgres:16"}


@pytest.fixture
def server(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    for name, text in (("docker", FAKE_DOCKER), ("id", FAKE_ID), ("loginctl", FAKE_LOGINCTL), ("userdel", FAKE_USERDEL),
                       ("systemctl", FAKE_SYSTEMCTL), ("nft", FAKE_NFT)):
        (bins / name).write_text(text)
        (bins / name).chmod(0o755)
    (tmp_path / "state.json").write_text(json.dumps(STATE))
    (tmp_path / "users").write_text("osprey-early\nayan\n")
    root = tmp_path / "srv" / "osprey-early"
    (root / "home/.ssh").mkdir(parents=True)
    (root / "data/source.git").mkdir(parents=True)
    (root / "home/.ssh/authorized_keys").write_text(
        'command="/usr/bin/env x",restrict ssh-ed25519 <key> osprey-early-warning-key\nssh-ed25519 <other> someone\n')
    dropin = tmp_path / "etc/user@1500.service.d/osprey-early-delegate.conf"
    dropin.parent.mkdir(parents=True)
    dropin.write_text("[Service]\nDelegate=cpu cpuset io memory pids\n")
    (tmp_path / "units").mkdir()
    (tmp_path / "units/osprey-early-shield.service").write_text("[Service]\nExecStart=/usr/sbin/nft -f x\n")
    (tmp_path / "table").write_text("table inet osprey_early\n")  # the fake nft's loaded table
    env = {"PATH": f"{bins}:/usr/bin:/bin", "FAKE_DOCKER_STATE": str(tmp_path / "state.json"),
           "FAKE_USERS": str(tmp_path / "users"), "FAKE_CALLS": str(tmp_path / "calls"),
           "OSPREY_EARLY_ROOT": str(root), "OSPREY_EARLY_DROPIN_BASE": str(tmp_path / "etc"),
           "OSPREY_EARLY_UNIT_DIR": str(tmp_path / "units"), "FAKE_TABLE": str(tmp_path / "table")}
    return {"tmp": tmp_path, "root": root, "env": env, "dropin": dropin}


def cleanup(s, *args):
    return subprocess.run(["bash", str(DEMO / "cleanup.sh"), *args], env=s["env"], capture_output=True, text=True)


def names(s):
    return {o["name"] for o in json.loads((s["tmp"] / "state.json").read_text())}


def test_dry_run_lists_and_removes_nothing(server):
    s = server
    p = cleanup(s, "--dry-run")
    assert p.returncode == 0, p.stderr
    for what in ("container osprey-early-job", "network osprey-early-net", "volume osprey-early-vol",
                 "image osprey-early-img:1", "the account osprey-early", "osprey-early-warning-key", str(s["root"]),
                 "the shield's unit", "the shield (nftables table inet osprey_early)"):
        assert f"would remove: {what}" in p.stdout or any(
            ln.startswith("would remove: ") and what in ln for ln in p.stdout.splitlines()), what
    assert names(s) == {o["name"] for o in STATE} and s["root"].exists() and s["dropin"].exists()
    assert "osprey-early" in (s["tmp"] / "users").read_text()
    calls = (s["tmp"] / "calls").read_text() if (s["tmp"] / "calls").exists() else ""
    assert "terminate-user" not in calls and "disable-linger" not in calls and "userdel" not in calls


def test_it_removes_only_the_runners_and_lists_what_it_removed_and_the_second_run_lists_nothing(server):
    s = server
    p = cleanup(s)
    assert p.returncode == 0, p.stderr
    assert names(s) == UNRELATED  # the demo's container and volume, and every object without both marks, untouched
    for what in ("removed: container osprey-early-job", "removed: network osprey-early-net",
                 "removed: volume osprey-early-vol", "removed: image osprey-early-img:1", "removed: the account",
                 "removed: the key's line", "removed: the runner's jobs", "removed: " + str(s["dropin"]),
                 "removed: the shield's unit", "removed: the shield (nftables table inet osprey_early)"):
        assert what in p.stdout, what
    assert not s["root"].exists() and not s["dropin"].exists()
    assert not (s["tmp"] / "units/osprey-early-shield.service").exists() and not (s["tmp"] / "table").exists()
    assert (s["tmp"] / "users").read_text() == "ayan\n"
    again = cleanup(s)
    assert again.returncode == 0 and again.stdout.strip() == "nothing to remove"


def test_the_key_line_goes_by_its_marker_and_another_key_stays(server):
    s = server
    keys = s["root"] / "home/.ssh/authorized_keys"
    env = {**s["env"]}
    # the line alone: the account and the folder kept out of it, so the file can be read after
    subprocess.run(["bash", "-c", 'grep -v "$2" "$1" > "$1.new"; mv "$1.new" "$1"', "_", str(keys),
                    "osprey-early-warning-key"], env=env, check=True)
    assert keys.read_text() == "ssh-ed25519 <other> someone\n"


def test_a_folder_that_is_not_the_runners_is_refused(server):
    s = server
    p = subprocess.run(["bash", str(DEMO / "cleanup.sh"), "--dry-run"],
                       env={**s["env"], "OSPREY_EARLY_ROOT": str(s["tmp"])}, capture_output=True, text=True)
    assert p.returncode == 2 and "not an osprey-early folder" in p.stderr


def test_the_server_scripts_parse_and_pass_shellcheck():
    for f in ("install.sh", "cleanup.sh"):
        assert subprocess.run(["bash", "-n", str(DEMO / f)]).returncode == 0
    if subprocess.run(["sh", "-c", "command -v shellcheck"], capture_output=True).returncode == 0:
        p = subprocess.run(["shellcheck", "-S", "warning", str(DEMO / "install.sh"), str(DEMO / "cleanup.sh")],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stdout


def test_install_prints_the_key_line_with_a_placeholder_and_opens_nothing():
    text = (DEMO / "install.sh").read_text()
    line = next(ln for ln in text.splitlines() if "restrict <PUBLIC KEY" in ln)
    assert 'command=\\"/usr/bin/python3 -I $ROOT/bin/runner.py\\",restrict' in line
    assert "osprey-early-warning-key" in line
    assert "Opened: nothing" in text
    import re
    code = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if re.search(r"(?:^|[;&|(]\s*|\$\()\s*docker\s", ln)]  # it runs no docker command
    assert os.access(DEMO / "install.sh", os.X_OK) and os.access(DEMO / "cleanup.sh", os.X_OK)
