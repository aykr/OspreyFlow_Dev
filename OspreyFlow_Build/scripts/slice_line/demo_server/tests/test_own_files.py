"""No file the early warning adds holds an address, a host name, a private key or a long base64 string (point 2), each
kind shown red planted. The planted values are built here at run time, so this file passes its own scan.

What counts: an IPv4 address other than loopback; a dotted name ending in a host-like top-level domain (the public
download hosts install.sh names, github.com and nodejs.org, are the only ones allowed, and `.invalid` is reserved by
RFC 2606 and can name no real host); a PEM or OpenSSH private-key block; a run of 40 or more base64 characters with
upper case, lower case and digits (a key's body; a git hash, all hex, is not one)."""
from __future__ import annotations

import re

import pytest

from conftest import DEMO

ADDED = sorted([p for p in DEMO.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
               + [DEMO.parent / "early_warning.py"])
ALLOWED_HOSTS = {"github.com", "nodejs.org", "extensions.duckdb.org"}  # public download hosts
TLDS = "com|net|org|io|co|uk|us|de|eu|info|biz|me|app|dev|cloud|ai|lan|local|internal|home|arpa|corp|localdomain"
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d./])")  # a network (10.0.0.0/8) names no host
HOST = re.compile(r"(?<![\w.-])((?:[A-Za-z0-9-]+\.)+(?:%s))(?![\w-])" % TLDS, re.I)
KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
B64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


def scan(text: str) -> list[str]:
    found = [f"address {m}" for m in IPV4.findall(text) if m not in ("127.0.0.1", "0.0.0.0")]
    found += [f"host {m}" for m in HOST.findall(text) if m.lower() not in ALLOWED_HOSTS]
    found += ["private key" for _ in KEY.findall(text)]
    for m in B64.findall(text):
        if re.search(r"[A-Z]", m) and re.search(r"[a-z]", m) and re.search(r"\d", m) and not re.fullmatch(r"[0-9a-f]+", m):
            found.append("base64 " + m[:8] + "...")
    return found


def test_the_scan_finds_nothing_in_any_file_the_early_warning_adds():
    assert len(ADDED) >= 10
    bad = {str(p.relative_to(DEMO.parent)): scan(p.read_text(errors="replace")) for p in ADDED}
    assert {k: v for k, v in bad.items() if v} == {}


DOT = "."
PLANTED = [
    ("address", "host = '" + DOT.join(["10", "20", "30", "40"]) + "'"),
    ("address", "ssh osprey@" + DOT.join(["192", "168", "1", "7"])),
    ("address", "elements = { " + DOT.join(["172", "17", "0", "1"]) + " }"),  # the Docker gateway, bare
    ("host", "HOST=" + DOT.join(["demo-box", "example", "com"])),
    ("host", "the server, " + DOT.join(["ospreydemo", "lan"]) + ", answered"),
    ("private key", "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nb3Blbn\n"),
    ("private key", "-----BEGIN " + "RSA PRIVATE KEY-----"),
    ("base64", "ssh-ed25519 " + "AAAAC3NzaC1lZDI1NTE5AAAAI" + "Hq9x7Kd2mPq4Z8vB3nR5" + "tY1wE6uI0oL9sA2dF4gH7jK" + " me"),
]


@pytest.mark.parametrize("kind,text", PLANTED)
def test_each_kind_planted_is_found(kind, text):
    assert any(f.startswith(kind) for f in scan(text)), scan(text)


@pytest.mark.parametrize("text", [
    "os.environ and subprocess.run and json.loads", "a git hash " + "0123456789abcdef" * 3, "127.0.0.1:59991",
    "early-box.example.invalid", "https://github.com/astral-sh/uv/releases", "Node 22.23.5 and uv 0.5.14",
    "tests/test_x.py::test_y", "uvicorn.Server is replaced",
    "elements = { 10.0.0.0/8, 172.16.0.0/12 }", "bound to 0.0.0.0", "OspreyFlow_Build/scripts/slice_line/demo_server/runner.py"])
def test_what_is_not_an_address_is_not_found(text):
    assert scan(text) == []
