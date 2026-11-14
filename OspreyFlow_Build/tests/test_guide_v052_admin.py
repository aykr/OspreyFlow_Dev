"""Two known-wrong passages of the administration guide, held to the code they describe (rule 12):

- §9's refusals on Entra ID are each one `entra_people.py` raises, both ways: a refusal the code no
  longer raises (a dashboard identity was once refused, ADR-148 Amendment 10 registers it) turns red, as
  a refusal left out does (`test_guides_cloud_platform`); the dashboard identity's own refusal, and its
  registration showing no secret, as the code words and returns them;
- §6a.1's decommission: the backups bucket and its key by a choice with no default, as the rendered
  `DECOMMISSION.md` refuses and does it (ADR-148 Amendment 13 decision 6).
"""

from __future__ import annotations

import ast
import re

import yaml

from tests.test_guides_cloud_platform import ADMIN, CORE, entra_refusals, section

ENTRA = CORE / "services/api/entra_people.py"


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def entra_sentence(guide: str) -> str:
    m = re.search(r"What Entra holds is refused here, in words,(.*?)\*\*A dashboard identity\*\*|"
                  r"What Entra holds is refused here, in words,(.*?)No administrator can",
                  _flat(section(guide, "## 9. People")))  # fmt: skip
    assert m, "§9's sentence quoting what Entra ID holds"
    return m.group(1) or m.group(2)


def quoted_refusals(guide: str) -> list[str]:
    """Each refusal §9's sentence quotes, in its parentheses: `("…")`."""
    return re.findall(r'\("([^"]+)"\)', entra_sentence(guide))


def test_section_9_quotes_no_entra_refusal_the_code_does_not_raise() -> None:
    raised = entra_refusals()
    assert [q for q in quoted_refusals(ADMIN) if q not in raised] == []


def test_the_quote_check_flags_a_refusal_the_code_dropped() -> None:
    planted = ADMIN.replace('and joining ("There is no', 'a dashboard ("Dashboard identities are not registered.") and joining ("There is no')
    assert "Dashboard identities are not registered." in [q for q in quoted_refusals(planted) if q not in entra_refusals()]


def _create_dashboard() -> ast.AsyncFunctionDef:
    tree = ast.parse(ENTRA.read_text(encoding="utf-8"))
    found = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "create_dashboard"]
    assert len(found) == 1, "entra_people.py's create_dashboard"
    return found[0]


def test_section_9_gives_the_dashboard_identity_s_registration_as_the_code_does() -> None:
    fn = _create_dashboard()
    words = ["".join(str(c.value) for c in n.args[0].values if isinstance(c, ast.Constant))
             if isinstance(n.args[0], ast.JoinedStr) else n.args[0].value
             for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "UnknownRoleError"]  # fmt: skip
    nine = _flat(section(ADMIN, "## 9. People"))
    without_id = next((w for w in words if "give its application id" in w), None)
    assert (f'refused ("{without_id}")' in nine) if without_id else ("Without an application id" not in nine)
    own = any("this deployment's own application" in w for w in words)
    assert ("and so is the deployment's own application, the Glass's or the API's" in nine) is own
    no_secret = "secret=None" in ast.unparse(fn)
    assert ("registers it by its application id, and shows no secret" in nine) is no_secret
    row = next(line for line in ADMIN.splitlines() if line.startswith("| People | **Dashboard identities** |"))
    assert ("on Entra ID, by its app registration's application id, with no secret shown" in row) is no_secret


def _decommission() -> str:
    from harness.render import render
    from tools.cp_policy_check import FIXTURES, _resolver

    from schemas.deployment import OspreyConfig

    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    return render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts["DECOMMISSION.md"]


def test_section_6a1_gives_the_decommission_s_backups_choice_as_the_runbook_makes_it() -> None:
    runbook = _decommission()
    m = re.search(r"\*\*The runbooks \(poc shape\)\.\*\*(.*?)\*\*Moving to a new release", _flat(section(ADMIN, "### 6a.1")))
    assert m, "§6a.1's paragraph on the runbooks"
    text = m.group(1)
    no_default = 'BACKUPS:?choose keep or destroy' in runbook and "there is no default" in runbook
    assert ("by a choice with no default: its step 7 refuses until it is given `BACKUPS=keep` or `BACKUPS=destroy`"
            in text) is no_default  # fmt: skip
    assert "the backups kept for their retention" not in text
    assert ("(`BACKUP_RETENTION_DAYS`)" in text) is ("BACKUP_RETENTION_DAYS" in runbook)
    assert ("schedules the key's deletion (thirty days" in text) is ("deletion scheduled (thirty days" in runbook)
    assert ("**destroy** removes every set now" in text) is ("delete-bucket-policy" in runbook)
