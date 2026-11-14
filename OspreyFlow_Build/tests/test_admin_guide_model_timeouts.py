"""The administration guide §10's *How long a model is waited for* and §6a.9's line on it (D2, ADR-135 Amendment 13,
with studio's render-timeouts change), held to the code (rule 12):

- `harness/render.py` passes both settings to the Conduit, each with its default, and the client
  (`adapters/model_litellm/client.py`) reads them with the same defaults;
- a hosted engine is any engine but the deployment's own (`_bound`);
- a call past its bound, and an engine's provider refusing, are said in `errors.py`'s words, naming the engine, with
  nothing recorded;
- the cloud-platform render passes neither setting, so its defaults hold there.
"""

from __future__ import annotations

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"


def read(path: str) -> str:
    return (CORE / path).read_text(encoding="utf-8")


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def guide() -> str:
    text = read("docs/administration-guide.md")
    return fold(re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL))


def rendered_defaults() -> dict[str, int]:
    """`harness/render.py`'s `MODEL_TIMEOUTS`, the one place the two defaults are written, and compose's use of it."""
    render = read("harness/render.py")
    block = re.search(r"^MODEL_TIMEOUTS: dict\[str, str\] = \{(.*?)^\}", render, re.MULTILINE | re.DOTALL)
    assert block, "render.py's MODEL_TIMEOUTS"
    found = dict(re.findall(r'"(OSPREY_(?:HOSTED_)?MODEL_TIMEOUT_SECONDS)": "(\d+)"', block.group(1)))
    assert set(found) == {"OSPREY_MODEL_TIMEOUT_SECONDS", "OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS"}, found
    assert 'for name, seconds in MODEL_TIMEOUTS.items(): api_environment[name] = "${" + name + ":-" + seconds + "}"' in fold(render)
    return {k: int(v) for k, v in found.items()}


def test_the_render_and_the_client_agree_on_both_bounds() -> None:
    defaults = rendered_defaults()
    client = fold(read("packages/adapters/model_litellm/client.py"))
    assert f'timeout_seconds=float(os.environ.get("OSPREY_MODEL_TIMEOUT_SECONDS", "{defaults["OSPREY_MODEL_TIMEOUT_SECONDS"]}")),' in client
    assert f'os.environ.get("OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS", "{defaults["OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS"]}")' in client
    # A hosted engine is any but the deployment's own.
    assert "hosted = call is not None and call.engine != LOCAL" in client
    assert "return self._hosted_timeout if hosted else self._timeout" in client


def test_section_10_gives_both_bounds_as_the_code_holds_them() -> None:
    defaults = rendered_defaults()
    text = guide()
    assert (f"A call to a hosted engine (any engine but the deployment's own) is waited for "
            f"{defaults['OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS']} seconds, `OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS`; a call to the "
            f"deployment's own model {defaults['OSPREY_MODEL_TIMEOUT_SECONDS']} seconds, `OSPREY_MODEL_TIMEOUT_SECONDS`.") in text  # fmt: skip
    assert "On Lite and Small each is set in the deployment's env file (`deployment.env`), and `ospreyflow apply` passes it to the Conduit." in text


def test_section_10_says_a_timeout_and_a_refusal_as_the_conduit_words_them() -> None:
    errors = fold(read("packages/adapters/model_litellm/errors.py"))
    assert 'f"{engine} did not answer within the time this deployment allows{bound}, so the "' in errors
    assert 'bound = f" ({self.timeout_seconds:g} seconds)" if self.timeout_seconds else ""' in errors
    assert 'return f"{said} Nothing was recorded."' in errors
    for kind in ('if self.kind == "busy":', 'elif self.kind == "key":', 'elif self.kind == "timed_out":'):
        assert kind in errors, kind
    assert 'f"{engine} is refusing more requests just now: its provider\'s own rate limit or "' in errors
    assert "f\"{engine}'s provider refused this deployment's key for it" in errors
    assert "f\"{engine}'s provider could not answer just now. Try again in a minute.\"" in errors
    client = fold(read("packages/adapters/model_litellm/client.py"))
    assert 'raise ModelEngineRefused("timed_out", timeout_seconds=self._bound()) from None' in client
    text = guide()
    assert ("A call past its bound is stopped, and the person is told the engine did not answer in the time this "
            "deployment allows, with the bound; nothing is recorded.") in text  # fmt: skip
    assert ("When an engine's provider refuses (its own rate limit or quota, a key it does not accept, or no answer after "
            "the gateway's own retries), the person is told which, in words naming the engine; nothing is recorded "
            "then either.") in text  # fmt: skip


def test_a_cluster_and_the_platform_render_both_at_their_defaults_with_no_setting() -> None:
    """442d28f: `harness/cluster.py`'s environment holds each at its default, and the shared platform's values carry
    it; `osprey.yaml` has no setting for either (no schema field names them)."""
    defaults = rendered_defaults()
    cluster = fold(read("harness/cluster.py"))
    assert "for name, seconds in MODEL_TIMEOUTS.items(): environment.setdefault(name, seconds)" in cluster
    from tests.harness.test_cloud_platform_render import _config, _values

    environment = _values(_config())["environment"]
    assert {k: int(environment[k]) for k in defaults} == defaults, "the shared platform's values carry both at their defaults"
    schema = read("packages/schemas/deployment.py")
    assert "MODEL_TIMEOUT" not in schema and "timeout_seconds" not in schema, "osprey.yaml has a setting now: the guide must say so"
    text = guide()
    assert ("On Enterprise and on a shared platform both are rendered into the chart's values (`environment`), at these "
            "defaults, and reach the Conduit from its ConfigMap; `osprey.yaml` has no setting for them.") in text  # fmt: skip
    assert (f"the render puts both settings in the values at their defaults ({defaults['OSPREY_HOSTED_MODEL_TIMEOUT_SECONDS']} "
            "seconds for a hosted engine), and `osprey.yaml` has no setting to change them.") in text  # fmt: skip
