"""The administration guide's model keys as the code keeps them (ADR-135 Amendment 2, 8 November 2026; the owner
followed the guide on 15 November and it said otherwise; rule 12): a key is entered in *Admin › Models*
(`admin/sections/Models.tsx`), kept by the model gateway alone, and `ospreyflow models key` runs the Conduit's own key
path inside its container, restarting nothing (`cli/ospreyflow/main.py`'s `_models`); the install hands a key from
`deployment.env` to the gateway and removes its line (`harness/apply.py`'s `move_model_keys_into_gateway`). Each claim
read from the code, never its comments, and the guide's old words refused.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "OspreyFlow_Core"
#: What the guide said before this correction.
OLD_WORDS = ("kept in `deployment.env` alone", "never shown in the Admin area", "restarts the model gateway",
             "`models key` and `models remove-key` keep it so")  # fmt: skip


def fold(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def guide() -> str:
    text = (CORE / "docs" / "administration-guide.md").read_text(encoding="utf-8")
    return fold(re.sub(r"<!-- document-control:begin -->.*?<!-- document-control:end -->", " ", text, flags=re.DOTALL))


def function(path: str, name: str) -> str:
    source = (CORE / path).read_text(encoding="utf-8")
    node = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == name)
    body = node.body[1:] if isinstance(node.body[0], ast.Expr) else node.body  # without its docstring
    return fold("\n".join(ast.get_source_segment(source, b) or "" for b in body))


def old_words(text: str) -> list[str]:
    return [w for w in OLD_WORDS if w in text]


def test_a_key_is_entered_in_admin_models_as_the_guide_says() -> None:
    models = fold((CORE / "apps/workspace/src/admin/sections/Models.tsx").read_text(encoding="utf-8"))
    assert '{engine.key_state === "set" ? "Rotate key" : "Enter key"}' in models
    assert '{engine.key_state === "set" ? "Rotate the key" : "Set the key"}' in models
    assert 'type="password"' in models
    # Neither Enter key nor Remove key for an engine on the gateway's IAM role.
    assert '{engine.key_state !== "iam_role" && (' in models
    assert '{engine.key_state !== "none" && engine.key_state !== "iam_role" && (' in models
    text = guide()
    assert ("**On a running deployment, a key is entered in Admin › Models** (section 10.1): an engine's row offers "
            "**Enter key** (**Rotate key** once one is set), which opens a password field and **Set the key** "
            "(**Rotate the key**).") in text  # fmt: skip
    assert "**Remove key** removes it." in text
    assert "keeps no key, and neither is offered for it." in text


def test_models_key_runs_the_conduit_s_key_path_and_restarts_nothing() -> None:
    body = function("cli/ospreyflow/main.py", "_models")
    assert 'in_conduit = [*_compose_of(directory), "exec", "-T"]' in body
    assert '[*in_conduit, "-e", engine_keys.KEY_GIVEN, "api", *engine_keys.KEY_PATH,' in body
    assert not re.search(r'"(restart|up|stop|start)"', body), "the command restarts nothing"
    text = guide()
    assert ("Both run the Conduit's own key path inside its container, the one Admin › Models uses, with the key passed "
            "by name in the environment, never as an argument; nothing is restarted.") in text  # fmt: skip


def test_the_install_hands_the_key_to_the_gateway_and_removes_its_line() -> None:
    body = function("harness/apply.py", "move_model_keys_into_gateway")
    assert '["exec", "-T", "api", "python", "-m", "services.api.model_keys", "move"]' in body
    assert 'line.startswith("OSPREY_MODEL_KEY_")' in body and "write_private(env_path," in body
    assert "they stay in deployment.env and the \" \"next apply tries again" in body
    text = guide()
    assert ("The install writes it to `deployment.env` only until the gateway is up, then hands it to the gateway and "
            "removes its line. If that fails it says so, the key stays in `deployment.env`, and the next "
            "`ospreyflow apply` tries again.") in text  # fmt: skip


def test_the_guide_s_old_words_are_gone_both_copies() -> None:
    assert old_words(guide()) == []
    spec = fold((Path(__file__).resolve().parents[1] / "spec" / "10_ADMINISTRATION_GUIDE.md").read_text(encoding="utf-8"))
    assert old_words(spec) == []


def test_the_old_words_are_flagged() -> None:
    planted = ("A key is kept in `deployment.env` alone and read only by the deployment's model gateway — never shown "
               "in the Admin area or any page of the Glass.")  # fmt: skip
    assert old_words(planted) == ["kept in `deployment.env` alone", "never shown in the Admin area"]
