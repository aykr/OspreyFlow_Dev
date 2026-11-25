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
    assert {(g[2], g[4]) for g in r.foreign_listeners(ME)} == {(22, 0), (5432, 999), (8443, 0)}  # each with its owner
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
        monkeypatch.setattr(r, "SHIELD_SEEN", tmp_path / "shield-seen.json")
        (got,) = r.shield_breaches()
        assert got.startswith(f"port {port} (uid {ME + 1}; found by the runner's checks since "), got
        (tmp_path / "tcp").write_text(PROC_HEADER + row("0100007F", port, "0A", ME))  # its own: no breach
        assert r.shield_breaches() == []


# ------------------------------------------------------------------ whose port, and since when (the owner, 24 November)

BREACH = re.compile(r"port \d+ \(uid \d+(, root)?; found by the runner's checks since "
                    r"\d{4}-\d\d-\d\d \d\d:\d\d UTC, (under a minute|\d+ min|\d+ h \d+ min|\d+ d \d+ h)\)")


def breach_world(tmp_path, monkeypatch, rows):
    """A /proc/net/tcp of the test's own with `rows` (address, port, uid), every connection succeeding, and the
    runner's record of what its checks found in tmp_path."""
    (tmp_path / "tcp").write_text(PROC_HEADER + "".join(row(a, p, "0A", u) for a, p, u in rows))
    (tmp_path / "tcp6").write_text(PROC_HEADER)
    (tmp_path / "resolv.conf").write_text("nameserver %s\n" % ".".join(["127", "0", "0", "53"]))
    monkeypatch.setattr(r, "PROC", tmp_path)
    monkeypatch.setattr(r, "RESOLV", tmp_path / "resolv.conf")
    monkeypatch.setattr(r, "SHIELD_SEEN", tmp_path / "shield-seen.json")
    monkeypatch.setattr(r, "reachable", lambda family, addr, port: True)
    (tmp_path / "range").write_text("32768\t60999\n")  # /proc/sys/net/ipv4/ip_local_port_range, as Linux writes it
    monkeypatch.setattr(r, "EPHEMERAL", tmp_path / "range")
    return tmp_path / "shield-seen.json"


def test_a_breach_names_its_owners_uid_and_how_long_the_runners_checks_have_found_it(tmp_path, monkeypatch):
    seen = breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000)])
    (first,) = r.shield_breaches()
    assert BREACH.fullmatch(first) and first.startswith("port 55434 (uid 1000; ") and "under a minute" in first, first
    assert json.loads(seen.read_text()) == {"1000:55434": pytest.approx(time.time(), abs=60)}
    since = time.time() - (6 * 3600 + 48 * 60 + 5)
    seen.write_text(json.dumps({"1000:55434": since}))  # as if found at every check since then
    (later,) = r.shield_breaches()
    assert BREACH.fullmatch(later) and later.endswith(
        "since %s, 6 h 48 min)" % time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(since))), later
    assert json.loads(seen.read_text()) == {"1000:55434": since}  # a later check keeps when it was first found


def test_a_listener_gone_at_one_check_counts_from_when_it_is_found_again(tmp_path, monkeypatch):
    seen = breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000)])
    seen.write_text(json.dumps({"1000:55434": time.time() - 7200}))
    (tmp_path / "tcp").write_text(PROC_HEADER)
    assert r.shield_breaches() == [] and json.loads(seen.read_text()) == {}
    (tmp_path / "tcp").write_text(PROC_HEADER + row("0100007F", 55434, "0A", 1000))
    (again,) = r.shield_breaches()
    assert "under a minute" in again, again


def test_each_owner_of_a_port_is_named_and_root_is_said(tmp_path, monkeypatch):
    breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000), ("00000000", 55434, 0), ("0100007F", 4000, 112)])
    got = r.shield_breaches()
    assert [g.split(";")[0] for g in got] == ["port 4000 (uid 112", "port 55434 (uid 0, root", "port 55434 (uid 1000"]
    assert all(BREACH.fullmatch(g) for g in got), got  # a port, a uid and a time: no address, no process, no name


def test_a_breach_is_still_named_when_its_record_cannot_be_kept(tmp_path, monkeypatch):
    breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000)])
    monkeypatch.setattr(r, "SHIELD_SEEN", tmp_path / "no-such-folder" / "shield-seen.json")
    (got,) = r.shield_breaches()
    assert BREACH.fullmatch(got) and "under a minute" in got and not (tmp_path / "no-such-folder").exists()


def test_spans_are_said_in_plain_words():
    assert [r.how_long(s) for s in (5, 59, 60, 7 * 60 + 30, 3600, 6 * 3600 + 48 * 60, 49 * 3600)] == [
        "under a minute", "under a minute", "1 min", "7 min", "1 h 0 min", "6 h 48 min", "2 d 1 h"]


def test_nothing_of_any_process_is_read_only_the_kernels_socket_lists():
    """The uid comes from /proc/net/tcp's own column; the runner opens no other process's /proc/<pid> (only its own
    /proc/self/cgroup, and the system's port range under /proc/sys) and names no process."""
    src = (DEMO / "runner.py").read_text()
    assert set(re.findall(r"/proc/[a-z0-9%{]+", src)) == {"/proc/net", "/proc/self", "/proc/sys"}, re.findall(r"/proc/[a-z0-9%{]+", src)
    assert not re.search(r"cmdline|/comm\b|psutil|getpwuid|pwd\.", src)


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
    monkeypatch.setattr(r, "SHIELD_SEEN", tmp_path / "shield-seen.json")
    return [b.split(" (")[0] for b in r.shield_breaches()]  # the port alone: which ones, not whose


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
    assert f"port {port} (uid {ME + 1}; found by the runner's checks since " in a["words"], a["words"]
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


class Clock:
    """time.monotonic and time.sleep for the shield's wait: each sleep moves the clock on, and is kept."""
    def __init__(self):
        self.t, self.slept = 1000.0, []

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def waiting(monkeypatch, seen):
    """shield_after_waiting() over the checks `seen` gives in turn (the last one repeated), on a clock of its own."""
    clock = Clock()
    calls = []
    monkeypatch.setattr(r, "shield_breaches", lambda: calls.append(clock.t) or (seen.pop(0) if len(seen) > 1 else seen[0]))
    monkeypatch.setattr(r.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(r.time, "sleep", clock.sleep)
    return r.shield_after_waiting(), clock, calls


LISTENER = "port 55434 (uid 1000; found by the runner's checks since 2026-11-24 00:12 UTC, 6 h 48 min)"


def test_another_accounts_listener_that_goes_within_five_minutes_lets_the_run_go_ahead_and_says_so(monkeypatch):
    (found, words), clock, calls = waiting(monkeypatch, [[LISTENER]] * 5 + [[]])
    assert found == [] and clock.slept == [30] * 5, clock.slept  # checked again every 30 s
    assert words == ("the shield check found another account's listener (port 55434 (uid 1000)); checked again every "
                     "30 s, it had gone after 2 min 30 s, and the run went ahead")


def test_one_that_stays_five_minutes_refuses_the_run_and_says_how_long_it_was_waited_for(monkeypatch):
    (found, words), clock, calls = waiting(monkeypatch, [[LISTENER]])
    assert found == [LISTENER] and sum(clock.slept) == 300 and max(clock.slept) == 30 and len(calls) == 11
    assert words == "checked again every 30 s for 5 min, it stayed"


def test_with_nothing_found_there_is_no_wait(monkeypatch):
    (found, words), clock, _ = waiting(monkeypatch, [[]])
    assert (found, words, clock.slept) == ([], "", [])


def test_when_the_sockets_cannot_be_read_it_refuses_at_once_without_waiting(monkeypatch):
    (found, words), clock, _ = waiting(monkeypatch, [["the listening sockets cannot be read (/x): the shield cannot be checked"]])
    assert "cannot be checked" in found[0] and words == "" and clock.slept == []


def test_the_job_waits_for_the_summary_then_for_a_listener_to_go_before_anything_runs():
    text = (DEMO / "runner.py").read_text()
    body = text[text.index("def run_job("):]
    assert body.index("wait_for_the_summary(log)") < body.index("breaches, waited = shield_after_waiting()") \
        < body.index("make_tree(tree")
    assert r.SHIELD_WAIT_SECONDS == 5 * 60 and r.SHIELD_RECHECK_SECONDS == 30 and r.SUMMARY_WAIT_SECONDS == 15 * 60


def test_a_listener_that_goes_while_the_job_waits_lets_it_run_and_the_note_says_so(world):
    """End to end: the job finds another account's listener, it goes once the job's first check has recorded it
    (never on a clock: a busy Mac starts the job late), the run goes ahead, and the Mac's note has the Shield line."""
    from conftest import early, note
    w = world
    proc = w["tmp"] / "proc-net"
    h = w["tmp"] / "harness.json"
    h.write_text(json.dumps({**json.loads(h.read_text()), "shield_wait": 120, "shield_recheck": 0.2}))
    import threading
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        (proc / "tcp").write_text(PROC_HEADER + row("0100007F", port, "0A", ME + 1))
        record = w["remote"] / "data" / "shield-seen.json"

        def go_once_found():  # the job's first check writes the record; then the listener goes
            end = time.monotonic() + 100
            while time.monotonic() < end:
                try:
                    if "%d:%d" % (ME + 1, port) in record.read_text():
                        break
                except OSError:
                    pass
                time.sleep(0.05)
            (proc / "tcp").write_text(PROC_HEADER)
        gone = threading.Thread(target=go_once_found)
        gone.start()
        p_ = early(w, "S1")
        gone.join()
    text = note(w).read_text()
    assert p_.returncode == 0, p_.stdout + p_.stderr
    assert re.search(r"- Shield: the shield check found another account's listener \(port %d \(uid %d\)\); checked "
                     r"again every \d+ s, it had gone after \d+ s, and the run went ahead" % (port, ME + 1), text), text


def test_the_three_questions_answer_from_the_socket_lists_and_change_nothing(tmp_path, monkeypatch):
    """ask ports, ask ollama, ask shield (the owner, 24 November): ports and uids, how long seen, and no write."""
    seen = breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000), ("00000000", 22, 0),
                                                ("0100007F", 11434, 997), ("0100007F", 41000, 997)])
    since = time.time() - 3 * 3600
    seen.write_text(json.dumps({"1000:55434": since}))
    before = seen.read_text()
    ports = r.ask("ports")
    assert ports["range"] == "32768-60999" and [(x["port"], x["uid"]) for x in ports["listeners"]] == [(41000, 997), (55434, 1000)]
    assert ports["listeners"][1]["seen"].endswith(", 3 h 0 min") and "not yet found" in ports["listeners"][0]["seen"]
    oll = r.ask("ollama")
    assert oll["listening"] and oll["model_loaded"] and oll["uid"] == [997] and oll["helper_ports"] == [41000]
    assert "a model is loaded" in oll["words"] and "no connection to Ollama" in oll["basis"]
    sh_ = r.ask("shield")
    assert sh_["holds"] is False and len(sh_["breaches"]) == 4 and "would not hold now" in sh_["words"]
    assert seen.read_text() == before  # nothing written, not even the runner's own record
    blob = json.dumps([ports, oll, sh_])
    assert "127.0.0.1" not in blob and "0.0.0.0" not in blob  # ports and uids, never an address


def test_ollama_with_no_helper_has_no_model_loaded_and_with_no_listener_is_not_running(tmp_path, monkeypatch):
    breach_world(tmp_path, monkeypatch, [("0100007F", 11434, 997), ("0100007F", 41000, 1000)])
    oll = r.ask("ollama")
    assert oll["listening"] and oll["model_loaded"] is False and "no model is loaded" in oll["words"]  # 41000: not its
    breach_world(tmp_path, monkeypatch, [])
    oll = r.ask("ollama")
    assert oll["listening"] is False and "not running here" in oll["words"]
    breach_world(tmp_path, monkeypatch, [("0100007F", 11434, 0), ("0100007F", 41000, 0)])
    assert "runs as root here" in r.ask("ollama")["words"]


def test_the_shield_question_says_it_holds_when_nothing_is_reachable(tmp_path, monkeypatch):
    breach_world(tmp_path, monkeypatch, [("0100007F", 55434, 1000)])
    monkeypatch.setattr(r, "reachable", lambda family, addr, port: False)
    assert r.ask("shield")["holds"] is True and r.ask("ports")["listeners"][0]["port"] == 55434


def test_the_questions_come_over_the_forced_command_and_from_early_warning(world):
    from conftest import early, ssh_calls
    w = world
    for what in ("ports", "ollama", "shield"):
        a = json.loads(runner(w, "ask " + what).stdout.decode().splitlines()[-1])
        assert a["state"] == "done" and a["ask"] == what, a
        p_ = early(w, "ask", what)
        assert p_.returncode == 0 and json.loads(p_.stdout)["ask"] == what and ssh_calls(w)[-1][-2:] == ["ask", what]
    for bad in ("ask", "ask ports ollama", "ask kill", "ask ports;id"):
        assert json.loads(runner(w, bad).stdout.decode().splitlines()[-1])["state"] == "refused", bad
    assert early(w, "ask", "kill").returncode == 2 and early(w, "ask").returncode == 2
