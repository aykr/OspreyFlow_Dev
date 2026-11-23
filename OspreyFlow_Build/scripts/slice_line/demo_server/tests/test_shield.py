"""The demo shield (the owner's ruling of 21 November 2026): the nftables rules' shape, and the check each job makes
before running anything, that no port another account listens on can be reached from this account.

The rules themselves load only on the server (nft needs root and Linux): SERVER_HAND_CHECKS.md has the check that a
connection from the runner's account to a port the demo publishes fails. Here: the rules' text, and the job's own
check against a real listening socket the test opens, listed in a /proc/net/tcp of the test's own as another
account's."""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time

import pytest
from pathlib import Path

from conftest import DEMO, PROC_HEADER, runner, sh

sys.path.insert(0, str(DEMO))
import runner as r  # noqa: E402

ME = os.getuid()


def row(addr_hex: str, port: int, state: str, uid: int) -> str:
    return f"   0: {addr_hex}:{port:04X} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000 {uid:5d} 0 1 1\n"


def test_listeners_of_other_accounts_are_read_and_this_accounts_own_are_not(tmp_path, monkeypatch):
    (tmp_path / "tcp").write_text(PROC_HEADER + row("00000000", 22, "0A", 0) + row("0100007F", 5432, "0A", 999)
                                  + row("0100007F", 40000, "0A", ME) + row("0100007F", 8080, "01", 0))
    (tmp_path / "tcp6").write_text(PROC_HEADER + row("00000000000000000000000000000000", 8443, "0A", 0))
    monkeypatch.setattr(r, "PROC", tmp_path)
    got = [g[:3] for g in r.foreign_listeners(ME)]
    assert (socket.AF_INET, "127.0.0.1", 22) in got and (socket.AF_INET, "127.0.0.1", 5432) in got
    assert (socket.AF_INET6, "::1", 8443) in got
    assert all(port not in (40000, 8080) for _, _, port in got)  # its own, and one not listening


def test_a_port_another_account_listens_on_that_is_reachable_is_a_breach(tmp_path, monkeypatch):
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        (tmp_path / "tcp").write_text(PROC_HEADER + row("0100007F", port, "0A", ME + 1))
        (tmp_path / "tcp6").write_text(PROC_HEADER)
        monkeypatch.setattr(r, "PROC", tmp_path)
        assert r.shield_breaches() == [f"port {port}"]
        (tmp_path / "tcp").write_text(PROC_HEADER + row("0100007F", port, "0A", ME))  # its own: no breach
        assert r.shield_breaches() == []


# ------------------------------------------------------------------ the resolver the shield allows (run 7a6267988c4ebce6)

RESOLVED = "0100007F"  # 127.0.0.1, as /proc/net/tcp writes it
STUB = "3500007F"  # systemd-resolved's stub address, the server's resolver
ANY = "00000000"  # 0.0.0.0


def listening(tmp_path, monkeypatch, rows, nameservers=(".".join(["127", "0", "0", "53"]),), tcp6=""):
    """A /proc/net/tcp of the test's own, a resolv.conf naming `nameservers`, and every connection succeeding (the
    shield taken down entirely), so only the exemption decides what is a breach."""
    (tmp_path / "tcp").write_text(PROC_HEADER + "".join(row(a, p, "0A", ME + 1) for a, p in rows))
    (tmp_path / "tcp6").write_text(PROC_HEADER + tcp6)
    (tmp_path / "resolv.conf").write_text("# test\noptions edns0\n" + "".join(f"nameserver {n}\n" for n in nameservers))
    monkeypatch.setattr(r, "PROC", tmp_path)
    monkeypatch.setattr(r, "RESOLV", tmp_path / "resolv.conf")
    monkeypatch.setattr(r, "reachable", lambda family, addr, port: True)
    return r.shield_breaches()


def test_the_resolver_on_53_at_its_own_address_is_not_a_breach(tmp_path, monkeypatch):
    assert listening(tmp_path, monkeypatch, [(STUB, 53)]) == []


def test_another_service_on_53_at_a_different_address_is_a_breach(tmp_path, monkeypatch):
    assert listening(tmp_path, monkeypatch, [(STUB, 53), (RESOLVED, 53)]) == ["port 53"]


def test_a_wildcard_listener_on_53_is_a_breach_even_where_loopback_is_a_nameserver(tmp_path, monkeypatch):
    assert listening(tmp_path, monkeypatch, [(ANY, 53)], nameservers=(".".join(["127", "0", "0", "1"]),)) == ["port 53"]


def test_another_port_at_the_resolvers_address_is_a_breach(tmp_path, monkeypatch):
    assert listening(tmp_path, monkeypatch, [(STUB, 53), (STUB, 5355)]) == ["port 5355"]


def test_53_is_a_breach_when_resolv_conf_names_another_resolver(tmp_path, monkeypatch):
    assert listening(tmp_path, monkeypatch, [(STUB, 53)], nameservers=(".".join(["192", "0", "2", "53"]),)) == ["port 53"]


def test_an_ipv6_resolver_at_its_own_address_is_not_a_breach(tmp_path, monkeypatch):
    v6_loopback = "00000000000000000000000001000000"  # ::1, as /proc/net/tcp6 writes it
    got = listening(tmp_path, monkeypatch, [], nameservers=("::1",), tcp6=row(v6_loopback, 53, "0A", ME + 1))
    assert got == []


def test_with_no_listing_of_sockets_the_shield_cannot_be_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(r, "PROC", tmp_path / "absent")
    assert r.shield_breaches() and "cannot be checked" in r.shield_breaches()[0]


def wait(w, jid):
    end = time.monotonic() + 30
    while time.monotonic() < end:
        a = json.loads(runner(w, "result " + jid).stdout.decode().splitlines()[-1])
        if a["state"] != "running":
            return a
        time.sleep(0.2)
    raise AssertionError("no result")


def start(w):
    f = w["tmp"] / "b.bundle"
    sh(["git", "bundle", "create", "-q", str(f), "refs/heads/main", "refs/heads/lane/slice-S1"], w["repo"], w["env"])
    return json.loads(runner(w, "run", f.read_bytes()).stdout.decode().splitlines()[-1])["id"]


def test_a_job_whose_account_reaches_another_accounts_port_runs_nothing(world):
    w = world
    proc = w["tmp"] / "proc-net"
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        (proc / "tcp").write_text(PROC_HEADER + row("0100007F", port, "0A", ME + 1))  # "the demo", reachable
        a = wait(w, start(w))
    assert a["verdict"] == "error" and "the shield does not hold" in a["words"] and f"port {port}" in a["words"]
    assert "steps" not in a and "merge" not in a  # nothing was run: no merge, no gate
    assert "127.0.0.1" not in json.dumps(a)  # ports alone, never an address


def test_with_the_shield_holding_the_job_runs(world):
    a = wait(world, start(world))
    assert a["verdict"] == "pass" and a["steps"]


RULES = (DEMO / "shield.nft").read_text()


def test_the_rules_touch_only_the_runners_account_and_nothing_inbound():
    chain = RULES[RULES.index("chain output"):]
    rules = [ln.strip() for ln in chain.splitlines()[1:] if ln.strip() and not ln.strip().startswith("}")]
    assert rules[0] == "type filter hook output priority filter; policy accept;"
    assert rules[1] == 'meta skuid != "@USER@" accept'  # every other account: as if the table were not there
    assert "hook input" not in RULES and "hook forward" not in RULES and "hook prerouting" not in RULES
    assert RULES.count("table inet osprey_early {") == 1 and "delete table inet osprey_early" in RULES


def test_the_rules_refuse_this_machine_and_every_private_network_before_allowing_https():
    chain = RULES[RULES.index("chain output"):]
    order = [ln.strip() for ln in chain.splitlines()]
    at = {k: min(i for i, ln in enumerate(order) if k in ln) for k in (
        "@DNS@", 'oifname "lo"', "fib daddr type local reject", "ip daddr @private4 reject",
        "ip6 daddr @private6 reject", "th dport 443 accept")}
    assert at["@DNS@"] < at['oifname "lo"'] < at["fib daddr type local reject"] < at["ip daddr @private4 reject"]
    assert at["ip6 daddr @private6 reject"] < at["th dport 443 accept"]
    assert order[[i for i, ln in enumerate(order) if ln][-3]] == "reject"  # all else refused
    lo = order[at['oifname "lo"']]
    assert "th dport @EPHEMERAL@ accept" in lo and "meta l4proto tcp" in lo
    for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "169.254.0.0/16", "fc00::/7", "fe80::/10"):
        assert net in RULES, net  # Docker's bridges (172.16/12 by default) and every other private range


def test_a_job_whose_account_reaches_dockers_socket_runs_nothing(world):
    """005: with no DOCKER_HOST, each job checks Docker's socket refuses its account, as it checks the shield."""
    import tempfile
    w = world
    d = tempfile.mkdtemp(prefix="ew", dir="/tmp")  # a unix socket's path must be short
    sock = os.path.join(d, "docker.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
        srv.bind(sock)
        srv.listen(1)
        f = w["tmp"] / "b2.bundle"
        sh(["git", "bundle", "create", "-q", str(f), "refs/heads/main", "refs/heads/lane/slice-S1"], w["repo"], w["env"])
        jid = json.loads(runner(w, "run", f.read_bytes(), harness={"docker_sockets": [sock]}).stdout.decode()
                         .splitlines()[-1])["id"]
        a = wait(w, jid)
    assert a["verdict"] == "error" and "Docker's socket answers this account" in a["words"] and "steps" not in a
    os.unlink(sock)
    os.rmdir(d)


def test_a_docker_socket_that_refuses_the_account_is_not_reachable(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "DOCKER_SOCKETS", (str(tmp_path / "absent.sock"),))
    assert r.docker_reachable() == []


def test_the_runner_sets_no_docker_host_and_fetches_duckdbs_extension_over_https_only():
    text = (DEMO / "runner.py").read_text()
    assert '"DOCKER_HOST"' not in text
    assert "https://extensions.duckdb.org/" in text and "http://extensions" not in text


def spatial_step(monkeypatch, tmp_path, answer=None, refuse=None, during_install=None):
    """runner.py's DUCKDB_SPATIAL itself, with DuckDB and the network stood in for: what it asked for, and said."""
    import gzip
    import io
    import types
    import urllib.error
    import urllib.request
    asked = {}

    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        asked["url"] = req.full_url if isinstance(req, urllib.request.Request) else req
        asked["agent"] = req.get_header("User-agent") if isinstance(req, urllib.request.Request) else None
        if refuse:
            raise urllib.error.HTTPError(asked["url"], refuse, "Forbidden", {}, None)
        return Answer(gzip.compress(answer or b"extension"))

    duck = types.ModuleType("duckdb")
    duck.__version__ = "1.5.6"
    duck.sql = lambda q: types.SimpleNamespace(fetchone=lambda: ("linux_amd64",))
    def install_extension(p):
        asked.setdefault("installed", p)
        if during_install:
            during_install(p)  # e.g. a second job's step, run while this one installs
        asked.setdefault("read", Path(p).read_bytes())

    duck.connect = lambda: types.SimpleNamespace(install_extension=install_extension,
                                                 load_extension=lambda n: asked.setdefault("loaded", n))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setitem(sys.modules, "duckdb", duck)
    monkeypatch.setattr(sys, "argv", ["-c", str(tmp_path)])
    printed = io.StringIO()
    monkeypatch.setattr(sys, "stdout", printed)
    exec(compile(r.DUCKDB_SPATIAL, "DUCKDB_SPATIAL", "exec"), {"__name__": "__main__"})
    monkeypatch.undo()
    return asked, json.loads(printed.getvalue().splitlines()[-1])


def test_the_spatial_fetch_names_a_client_the_extension_host_accepts(monkeypatch, tmp_path):
    """006: the host refuses Python's own client name (403 in run fb4aa131a68d8fb4), so the fetch names its own."""
    asked, said = spatial_step(monkeypatch, tmp_path)
    assert asked["url"] == "https://extensions.duckdb.org/v1.5.6/linux_amd64/spatial.duckdb_extension.gz"
    assert asked["agent"] and not asked["agent"].lower().startswith("python")
    assert said["status"] == "installed" and asked["loaded"] == "spatial" and asked["installed"].endswith(".duckdb_extension")
    assert len(said["sha256"]) == 64


def test_a_refused_spatial_fetch_says_where_it_stopped_and_why(monkeypatch, tmp_path):
    """006: a failure is the stage and the reason, for the note's one line; never only an exit code."""
    asked, said = spatial_step(monkeypatch, tmp_path, refuse=403)
    assert said["status"] == "failed" and said["stage"] == "fetch" and said["http_status"] == 403
    assert said["reason"] == "HTTPError: HTTP Error 403: Forbidden"
    assert "installed" not in asked


def test_a_job_installs_from_its_own_unpacked_file_while_another_job_unpacks(monkeypatch, tmp_path):
    """015: three jobs share the cache. A second job's step, run while the first installs, writes none of the first's
    files, so the first still installs the whole extension (runs 1c7525d175792ee0 and d7ce43cd986f60e3 were truncated)."""
    import types
    whole = b"the whole extension" * 1000
    second = []

    def another_job_meanwhile(_):
        duck = sys.modules["duckdb"]
        first = duck.connect
        duck.connect = lambda: types.SimpleNamespace(install_extension=second.append, load_extension=lambda n: None)
        try:
            exec(compile(r.DUCKDB_SPATIAL, "DUCKDB_SPATIAL", "exec"), {"__name__": "__main__"})
        finally:
            duck.connect = first

    asked, said = spatial_step(monkeypatch, tmp_path, answer=whole, during_install=another_job_meanwhile)
    assert said["status"] == "installed"
    assert second and second[0] != asked["installed"], "the two jobs installed from one shared file"
    assert asked["read"] == whole, "the first job's file was changed by the second's unpack"
    folder = tmp_path / "v1.5.6" / "linux_amd64"
    assert sorted(x.name for x in folder.iterdir()) == ["spatial.duckdb_extension.gz"], \
        "a job left its part file or its unpacked copy in the shared cache"


def test_a_fetch_writes_a_part_file_of_its_own(monkeypatch, tmp_path):
    """015: two jobs fetching at once never write one part file. Another job's download in progress is left alone, and
    this job's own is put in place whole."""
    import gzip
    folder = tmp_path / "v1.5.6" / "linux_amd64"
    folder.mkdir(parents=True)
    theirs = folder / "spatial.duckdb_extension.gz.part"
    theirs.write_bytes(b"another job's download, half written")
    asked, said = spatial_step(monkeypatch, tmp_path, answer=b"mine")
    assert said["status"] == "installed" and asked["read"] == b"mine"
    assert theirs.read_bytes() == b"another job's download, half written", "another job's part file was written over"
    assert gzip.decompress((folder / "spatial.duckdb_extension.gz").read_bytes()) == b"mine"


def test_a_cached_download_that_does_not_unpack_is_dropped_and_fetched_again(monkeypatch, tmp_path):
    """015: a bad file in the cache would turn every later run red; it is dropped, and the next run fetches it."""
    folder = tmp_path / "v1.5.6" / "linux_amd64"
    folder.mkdir(parents=True)
    (folder / "spatial.duckdb_extension.gz").write_bytes(b"not gzip")
    asked, said = spatial_step(monkeypatch, tmp_path)
    assert said["status"] == "failed" and said["stage"] == "unpack" and "url" not in asked
    assert not (folder / "spatial.duckdb_extension.gz").exists()
    asked, said = spatial_step(monkeypatch, tmp_path)
    assert said["status"] == "installed" and asked["url"].endswith("spatial.duckdb_extension.gz")


def test_install_shows_the_shield_in_its_dry_run_and_cleanup_removes_it():
    install = (DEMO / "install.sh").read_text()
    assert 'say "  would write $ROOT/bin/shield.nft, checked with nft -c, and load it as:"' in install
    assert "systemctl enable --now osprey-early-shield.service" in install and "nft -c -f" in install
    cleanup = (DEMO / "cleanup.sh").read_text()
    assert "nft delete table inet osprey_early" in cleanup and "osprey-early-shield.service" in cleanup


# ------------------------------------------------------------------------------------------------ 015: the summary's model

def test_a_starting_job_waits_while_the_summary_holds_the_model_then_holds_the_lock_for_its_run(monkeypatch, tmp_path):
    """015: run edfcda0e99098325's summary loaded the model at 07:12:31 and five runs after it were refused on its port.
    A job now waits for the summary to let go, then holds the lock shared, so no summary starts beside it."""
    import fcntl
    import threading
    lock, log = tmp_path / "model.lock", tmp_path / "log"
    lock.write_text("")
    monkeypatch.setattr(r, "MODEL_LOCK", lock)
    monkeypatch.setattr(r, "_HELD", [])
    summary = open(lock)
    fcntl.flock(summary, fcntl.LOCK_EX)
    done = threading.Event()
    t = threading.Thread(target=lambda: (r.wait_for_the_summary(log), done.set()), daemon=True)
    t.start()
    assert not done.wait(2.5), "the job did not wait for the summary"
    fcntl.flock(summary, fcntl.LOCK_UN)
    summary.close()
    assert done.wait(5)
    assert len(r._HELD) == 1 and "waited" in log.read_text() and "for the summary to unload its model" in log.read_text()
    with open(lock) as again:
        with pytest.raises(OSError):
            fcntl.flock(again, fcntl.LOCK_EX | fcntl.LOCK_NB)  # a summary now finds it held
    os.close(r._HELD.pop())


def test_a_job_waits_for_the_summary_no_longer_than_its_limit(monkeypatch, tmp_path):
    import fcntl
    lock, log = tmp_path / "model.lock", tmp_path / "log"
    lock.write_text("")
    monkeypatch.setattr(r, "MODEL_LOCK", lock)
    monkeypatch.setattr(r, "SUMMARY_WAIT_SECONDS", 1)
    monkeypatch.setattr(r, "_HELD", [])
    with open(lock) as summary:
        fcntl.flock(summary, fcntl.LOCK_EX)
        t0 = time.monotonic()
        r.wait_for_the_summary(log)
        assert time.monotonic() - t0 < 5 and r._HELD == []
    assert "going on to the shield check" in log.read_text()


def test_with_no_summary_installed_a_job_does_not_wait(monkeypatch, tmp_path):
    monkeypatch.setattr(r, "MODEL_LOCK", tmp_path / "absent.lock")
    monkeypatch.setattr(r, "_HELD", [])
    r.wait_for_the_summary(tmp_path / "log")
    assert r._HELD == [] and not (tmp_path / "log").exists()


def test_a_breach_that_goes_within_the_settle_time_refuses_nothing_and_one_that_stays_does(monkeypatch):
    seen = [["port 34041"], ["port 34041"], []]
    monkeypatch.setattr(r, "shield_breaches", lambda: seen.pop(0) if len(seen) > 1 else seen[0])
    monkeypatch.setattr(r, "SHIELD_SETTLE_SECONDS", 10)
    monkeypatch.setattr(r.time, "sleep", lambda s: None)
    assert r.settled_breaches() == []
    monkeypatch.setattr(r, "shield_breaches", lambda: ["port 34041"])
    monkeypatch.setattr(r, "SHIELD_SETTLE_SECONDS", 0.2)
    assert r.settled_breaches() == ["port 34041"]


def test_the_job_waits_for_the_summary_before_its_shield_check_and_refuses_on_a_breach_that_stays():
    text = (DEMO / "runner.py").read_text()
    body = text[text.index("def run_job("):]
    assert body.index("wait_for_the_summary(log)") < body.index("breaches = settled_breaches()") \
        < body.index("make_tree(tree")
    assert r.SHIELD_SETTLE_SECONDS == 30 and r.SUMMARY_WAIT_SECONDS == 15 * 60
