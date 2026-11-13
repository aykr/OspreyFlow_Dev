"""Every route the closing-pass proof calls is one the Conduit serves.

`test_phase8_exit_over_the_wire.py` runs only when opted in against a rendered deployment, so a route
it calls can move and nothing notices: B13 and B14's fixture went on asking `POST /v1/hotlists` and
`GET /v1/alerts` after both moved under the case (found giving each of its cases a disposition for the
v0.5.2 install test, 13 November 2026). This reads every call the module makes, from its source, and
holds each to the routes FastAPI has registered, so the module cannot drift from the API again
without failing offline.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

MODULE = Path(__file__).with_name("test_phase8_exit_over_the_wire.py")
VERBS = {"get", "post", "put", "patch", "delete"}
#: The module's HTTP clients: a call on one whose path cannot be read fails the reading, never skipped.
CLIENTS = {"analyst", "client", "httpx", "browser"}
#: Client calls whose path is not the Conduit's, by their source: the demo analyst's Keycloak sign-in
#: (`_sign_in_as_the_demo_analyst`; on poc spec08_poc.py replaces it).
NOT_THE_CONDUIT = {"browser.get(authorize)", "browser.post(form_action.group(1)", "browser.post(f'{KEYCLOAK_ORIGIN}/realms/"}
_PARAM = re.compile(r"\{[^}]*\}")


def _path(node: ast.expr) -> str | None:
    """A call's path argument as a template: a string, an f-string (its fields as `{}`), or
    `_in_case(<path>)` (the module's own case prefix); None for anything else."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
        return text.removeprefix("{}") if text.startswith("{}/v1/") else text  # an origin before the path
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_in_case" and node.args:
        inner = _path(node.args[0])
        return None if inner is None else "/v1/investigations/{}" + inner.removeprefix("/v1")
    return None


def _client_calls(source: str) -> list[ast.Call]:
    """Every call on a client that names a path: its verbs, and `request`/`stream`, whose path is not read here
    and so is always named."""
    return [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in VERBS | {"request", "stream"} and ast.unparse(n.func.value) in CLIENTS]


def unreadable(source: str) -> set[str]:
    """Client calls whose path the reading cannot hold to a route (a variable, a keyword `url=`, a path built
    some other way, one led by a field that is not an origin before /v1, or one off /v1), less the known calls
    that are not the Conduit's; and every WebSocket URL not of the one shape `streams` reads."""
    found = set()
    for node in _client_calls(source):
        path = _path(node.args[0]) if node.args and node.func.attr in VERBS else None
        if path is None or not path.startswith("/v1/"):
            text = ast.unparse(node)
            if not any(text.startswith(known) for known in NOT_THE_CONDUIT):
                found.add(f"line {node.lineno}: {text[:120]}")
    tree = ast.parse(source)
    prose = _prose(tree)
    # A WebSocket opened with a URL the reading cannot read (a concatenation, a name given anything but a string
    # it reads) is named; a name only ever given strings is read through them.
    given: dict[str, list[ast.expr]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    given.setdefault(target.id, []).append(node.value)

    def read_url(arg: ast.expr) -> bool:
        if isinstance(arg, (ast.JoinedStr, ast.Constant)):
            return True
        values = given.get(arg.id, []) if isinstance(arg, ast.Name) else []
        return bool(values) and all(isinstance(v, (ast.JoinedStr, ast.Constant)) for v in values)

    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and ast.unparse(node.func).endswith("connect") and node.args
                and not read_url(node.args[0])):
            found.add(f"line {node.lineno}: a stream opened at a URL not read: {ast.unparse(node)[:120]}")
    for node in ast.walk(tree):
        if isinstance(node, (ast.JoinedStr, ast.Constant)) and id(node) not in prose:
            text = _template(node)
            if text is None or re.fullmatch(r"\{\}://\{\}(/v1/.*)", text):
                continue
            elif re.match(r"(\{\}|wss?)://", text):
                found.add(f"line {node.lineno}: a stream URL of another shape: {text[:120]}")
    return found


def _template(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    return None


def _prose(tree: ast.Module) -> set[int]:
    """Docstrings, and the pieces inside an f-string (read whole, as the f-string): not URLs anything opens."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        if isinstance(node, ast.JoinedStr):
            skip.update(id(v) for v in node.values)
    return skip


def calls(source: str) -> set[str]:
    """`METHOD /path` for every `<client>.<verb>(path, …)` in the source whose path is a /v1 route."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in VERBS and node.args:
            path = _path(node.args[0])
            if path and path.startswith("/v1/"):
                found.add(f"{node.func.attr.upper()} {_PARAM.sub('{}', path.split('?', 1)[0])}")
    return found


def streams(source: str) -> set[str]:
    """The WebSocket paths the module opens: an f-string `<scheme>://<origin>/v1/…`, its fields as `{}`."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.JoinedStr):
            text = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
            match = re.fullmatch(r"\{\}://\{\}(/v1/.*)", text)
            if match:
                found.add(match.group(1).split("?", 1)[0])
    return found


def _served_streams() -> set[str]:
    from fastapi.routing import APIWebSocketRoute
    from services.api.app import app

    return {_PARAM.sub("{}", r.path) for r in app.routes if isinstance(r, APIWebSocketRoute)}


def _served() -> set[str]:
    from tools.route_coverage_check import list_live_routes

    return {_PARAM.sub("{}", r) for r in list_live_routes()}


def served_by(call: str, served: set[str]) -> bool:
    """A call matches a route segment by segment: a route's `{}` takes any one segment (a literal one
    too, as `compute/{metric}` takes `compute/degree`); a call's segment holding a `{}` only a `{}`."""
    method, _, path = call.partition(" ")
    asked = path.strip("/").split("/")
    for route in served:
        verb, _, pattern = route.partition(" ")
        parts = pattern.strip("/").split("/")
        if verb == method and len(parts) == len(asked) and all(
            r == "{}" or (r == a and "{}" not in a) for r, a in zip(parts, asked, strict=True)
        ):
            return True
    return False


def test_the_reading_finds_the_calls_it_must() -> None:
    """A floor, so a reading that finds nothing cannot agree with every route."""
    found = calls(MODULE.read_text(encoding="utf-8"))
    for must in ("GET /v1/ontology", "POST /v1/investigations/{}/search", "GET /v1/alerts/{}",
                 "POST /v1/investigations/{}/ingest/recipes"):
        assert must in found, sorted(found)


def test_the_reading_names_a_moved_route() -> None:
    """The shape the module wrote before the fix, read at its own call site."""
    source = 'def f(client):\n    client.post("/v1/hotlists", json={})\n    client.get(_in_case(f"/v1/x/{i}"))\n'
    assert calls(source) == {"POST /v1/hotlists", "GET /v1/investigations/{}/x/{}"}


def test_matching_takes_a_parameter_for_a_literal_and_never_the_reverse() -> None:
    served = {"POST /v1/investigations/{}/compute/{}", "GET /v1/alerts/{}", "POST /v1/investigations/{}/hotlists"}
    assert served_by("POST /v1/investigations/{}/compute/degree", served)
    assert served_by("GET /v1/alerts/no-such-alert-{}", served)
    assert not served_by("POST /v1/hotlists", served)
    assert not served_by("GET /v1/alerts", served)
    assert not served_by("POST /v1/investigations/{}/{}", {"POST /v1/investigations/{}/hotlists"})


def test_the_reading_reads_an_origin_before_the_path() -> None:
    assert calls('def f():\n    httpx.get(f"{ORIGIN}/v1/ontology")\n') == {"GET /v1/ontology"}


def test_a_client_call_whose_path_cannot_be_read_is_named() -> None:
    """The review of c6c6044, note 6: a path in a variable, a `url=` keyword or built by a helper was skipped;
    and the review of 6918a58: one led by a field that is not an origin before /v1."""
    source = ('def f(analyst, browser, d, path):\n    analyst.get(path)\n    analyst.post(url="/v1/x")\n'
              '    analyst.get(_paths.alerts(case))\n    d.get(path)\n    browser.get(authorize)\n'
              '    analyst.post(f"{case_prefix}/hotlists")\n    analyst.get("/healthz")\n'
              '    u = f"ws://{host}/v1/investigations/{i}/stream"\n    w = f"{scheme}://{host}/ws/x"\n'
              '    websockets.connect(origin + "/v1/x/stream")\n    analyst.request("GET", "/v1/x")\n'
              '    ok = f"{scheme}://{h}/v1/investigations/{i}/stream"\n    websockets.connect(ok)\n')
    assert unreadable(source) == {"line 2: analyst.get(path)", "line 3: analyst.post(url='/v1/x')",
                                  "line 4: analyst.get(_paths.alerts(case))", "line 7: analyst.post(f'{case_prefix}/hotlists')",
                                  "line 8: analyst.get('/healthz')",
                                  "line 9: a stream URL of another shape: ws://{}/v1/investigations/{}/stream",
                                  "line 10: a stream URL of another shape: {}://{}/ws/x",
                                  "line 11: a stream opened at a URL not read: websockets.connect(origin + '/v1/x/stream')",
                                  "line 12: analyst.request('GET', '/v1/x')"}


def test_the_stream_the_module_opens_is_read_and_served() -> None:
    source = MODULE.read_text(encoding="utf-8")
    assert streams(source) == {"/v1/investigations/{}/stream"}
    assert streams(source) <= _served_streams()
    assert not streams('u = f"{scheme}://{host}/v1/investigations/{i}/strem"\n') <= _served_streams()


def test_every_client_call_in_the_closing_pass_proof_is_read() -> None:
    assert not unreadable(MODULE.read_text(encoding="utf-8"))


def test_every_route_the_closing_pass_proof_calls_is_served() -> None:
    served = _served()
    missing = sorted(c for c in calls(MODULE.read_text(encoding="utf-8")) if not served_by(c, served))
    assert not missing, f"the over-the-wire module calls routes the Conduit does not serve: {missing}"
