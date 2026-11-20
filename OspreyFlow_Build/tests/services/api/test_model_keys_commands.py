"""P6 of the owner's key review (15 November 2026; ADR-135 Amendment 14 point 10):
`python -m services.api.model_keys` run as the command it is, in a process of its own, with the
key on standard input and in `OSPREY_MODEL_KEY_GIVEN`, against a stand-in gateway this test serves
on localhost (allowed by the orchestrator: it is neither the shared server nor a stack). The key is
in no output, no exit message and no file, on success and on refusal.

The command's audit is Postgres in a deployment; here the process is started through a two-line
wrapper that gives it an in-memory audit, the one thing not the deployment's. Everything else is the
command's own: its arguments, its environment, its standard streams and its exit status.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from adapters.model_litellm.stand_in import StandInGateway, StandInProvider

CORE = Path(__file__).resolve().parents[4] / "OspreyFlow_Core"
MASTER = "sk-stand-in-master-commands"
KEY = "sk-PLANTED-command-key-C0MD-do-not-leak"
REFUSED = "sk-PLANTED-refused-command-key-R3FU"
ENGINES = [{"name": "gemini", "roles": {"extraction": "gemini-2.5-flash"}}]

#: The command, with its audit in memory (Postgres in a deployment) and nothing else changed.
WRAPPER = (
    "import sys, services.api.model_keys as k\n"
    "from services.api.model_admin import InMemoryModelAdminAudit as A\n"
    "class M(A):\n"
    "    async def close(self): pass\n"
    "async def connect(dsn): return M()\n"
    "k.PostgresModelAdminAudit.connect = staticmethod(connect)\n"
    "raise SystemExit(k.main())\n"
)


@pytest.fixture
def gateway() -> Iterator[tuple[StandInGateway, int]]:
    stand_in = StandInGateway(
        master_key=MASTER,
        salt_key="salt-commands",
        providers={"gemini": StandInProvider(KEY, frozenset({"gemini-2.5-flash"}))},
    )

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            request = httpx.Request(
                self.command,
                f"http://litellm:4000{self.path}",
                headers=dict(self.headers),
                content=self.rfile.read(length) if length else b"",
            )
            response = stand_in._handle(request)  # noqa: SLF001 - the stand-in's own handler
            body = response.content
            self.send_response(response.status_code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = do_DELETE = do_PATCH = do_PUT = _answer

        def log_message(self, *_args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield stand_in, server.server_address[1]
    finally:
        server.shutdown()


def _run(
    tmp_path: Path, port: int, args: list[str], *, stdin: str = "", given: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join([str(CORE), str(CORE / "packages")]),
        "LITELLM_HOST": "127.0.0.1",
        "LITELLM_PORT": str(port),
        "LITELLM_API_KEY": MASTER,
        "OSPREY_MODEL_ENGINES": json.dumps(ENGINES),
        "OSPREY_MODELS_LOCAL_ONLY": "false",
        "OSPREY_SENDABLE_HANDLING_CODES": "O",
        "OSPREY_MODEL_SETTINGS_DIR": str(tmp_path / "model-settings"),
        # Closed ports: nothing of the owner's deployment is reached (memory: pin ports).
        "POSTGRES_PORT": "59992",
        "ARCADEDB_HTTP_PORT": "59991",
        "VALKEY_PORT": "59993",
    }
    if given is not None:
        env["OSPREY_MODEL_KEY_GIVEN"] = given
    return subprocess.run(
        [sys.executable, "-c", WRAPPER, *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=CORE,
        env=env,
        timeout=60,
        check=False,
    )


def _shown(done: subprocess.CompletedProcess[str], tmp_path: Path) -> str:
    files = "\n".join(
        p.read_bytes().decode("utf-8", "replace") for p in tmp_path.rglob("*") if p.is_file()
    )
    return "\n".join([done.stdout, done.stderr, files])


def test_set_from_the_variable_and_from_standard_input_shows_the_key_nowhere(
    tmp_path: Path, gateway: tuple[StandInGateway, int]
) -> None:
    stand_in, port = gateway
    by_variable = _run(tmp_path, port, ["set", "gemini", "--by", "ayan"], given=KEY)
    assert by_variable.returncode == 0, by_variable.stderr
    assert "key set for gemini" in by_variable.stdout
    on_stdin = _run(tmp_path, port, ["set", "gemini", "--by", "ayan"], stdin=KEY + "\n")
    assert on_stdin.returncode == 0, on_stdin.stderr
    for done in (by_variable, on_stdin):
        assert KEY not in _shown(done, tmp_path) and "C0MD" not in _shown(done, tmp_path)
    assert stand_in.credential("osprey-gemini") == KEY, "it did reach the gateway"


def test_a_refused_key_is_said_in_fixed_words_and_shown_nowhere(
    tmp_path: Path, gateway: tuple[StandInGateway, int]
) -> None:
    """Refused by its check (the owner's ruling 19): exit 1, the Conduit's words, never the key."""
    stand_in, port = gateway
    for kw in ({"given": REFUSED}, {"stdin": REFUSED + "\n"}):
        done = _run(tmp_path, port, ["set", "gemini", "--by", "ayan"], **kw)  # type: ignore[arg-type]
        assert done.returncode == 1, (done.stdout, done.stderr)
        assert "Nothing was changed" in done.stderr
        assert REFUSED not in _shown(done, tmp_path) and "R3FU" not in _shown(done, tmp_path)
    assert stand_in.credential("osprey-gemini") is None


def test_move_and_remove_show_the_key_nowhere(
    tmp_path: Path, gateway: tuple[StandInGateway, int]
) -> None:
    stand_in, port = gateway
    moved = _run(tmp_path, port, ["move", "--by", "apply"], stdin=f"GEMINI={KEY}\n")
    assert moved.returncode == 0, moved.stderr
    assert "moved into the gateway: gemini" in moved.stdout
    assert stand_in.credential("osprey-gemini") == KEY
    removed = _run(tmp_path, port, ["remove", "gemini", "--by", "ayan"])
    assert removed.returncode == 0, removed.stderr
    assert stand_in.credential("osprey-gemini") is None
    for done in (moved, removed):
        assert KEY not in _shown(done, tmp_path)


def test_an_unreachable_gateway_shows_the_key_nowhere(tmp_path: Path) -> None:
    """The gateway on a closed port: the command fails, and neither its words nor any traceback it
    prints holds the key."""
    done = _run(tmp_path, 59996, ["set", "gemini", "--by", "ayan"], given=KEY)
    assert done.returncode != 0
    assert KEY not in _shown(done, tmp_path) and "C0MD" not in _shown(done, tmp_path)
