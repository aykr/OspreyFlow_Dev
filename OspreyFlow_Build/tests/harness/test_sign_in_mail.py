"""Invitations by email when the deployment has a mail server (`06_DECISIONS.md` ADR-114
Amendment 5, the owner's "Email if set, else one-time code"; stage B4e).

Measured first on Keycloak 26.0.8 with a mail catcher: with the realm's `smtpServer` set, an actions
email reaches the person, from the configured sender, carrying Keycloak's own set-password link; with
none it is refused (500, "No sender address configured"); a person with no address is refused (400,
"User email missing"); and reading the realm back never returns the mail password.

What a mistake would do, and the case that catches it:
- the mail password in `osprey.yaml`, the render or `realm.json` —
  `test_the_mail_password_is_never_in_the_configuration_or_the_render`;
- email switched on without a mail server, or off with one — `test_the_conduit_invites_by_email_only_with_a_mail_server`;
- a mail server that needs a password installed without one — `test_a_mail_password_comes_from_the_installer_or_the_install_stops`;
- Keycloak never told the mail server — `test_registration_gives_keycloak_the_mail_server`.
"""

from __future__ import annotations

from typing import Any

import pytest
from harness import apply as apply_module
from harness import keycloak_admin
from harness.realm import render_realm
from harness.render import render

from schemas.deployment import OspreyConfig

MAIL = {"host": "smtp.example.org", "port": 587, "from_address": "osprey@example.org",
        "starttls": True, "username": "osprey-mailer"}  # fmt: skip


def _artefacts(mail: dict[str, Any] | None) -> dict[str, str]:
    config = OspreyConfig.model_validate({"mail": mail} if mail else {})
    return render(config, resolver=lambda _image: "sha256:" + "0" * 64).artefacts


def test_the_mail_password_is_never_in_the_configuration_or_the_render() -> None:
    with pytest.raises(ValueError):
        OspreyConfig.model_validate({"mail": {**MAIL, "password": "hunter2"}})
    config = OspreyConfig.model_validate({"mail": MAIL})
    rendered = "".join(_artefacts(MAIL).values()) + str(render_realm(config))
    assert "OSPREY_SMTP_PASSWORD=" not in rendered and "hunter2" not in rendered


def test_the_conduit_invites_by_email_only_with_a_mail_server() -> None:
    assert "OSPREY_SIGN_IN_EMAIL=true" in _artefacts(MAIL)["deployment.env"]
    assert "OSPREY_SIGN_IN_EMAIL" not in _artefacts(None)["deployment.env"]


def test_a_mail_password_comes_from_the_installer_or_the_install_stops() -> None:
    with_login = OspreyConfig.model_validate({"mail": MAIL})
    assert apply_module.mail_secret_lines(with_login, {"OSPREY_SMTP_PASSWORD": "s3cret"}) == (
        "OSPREY_SMTP_PASSWORD=s3cret\n"
    )
    with pytest.raises(apply_module.ApplyFailed, match="OSPREY_SMTP_PASSWORD"):
        apply_module.mail_secret_lines(with_login, {})
    open_relay = OspreyConfig.model_validate({"mail": {**MAIL, "username": None}})
    assert apply_module.mail_secret_lines(open_relay, {}) == ""
    assert apply_module.mail_secret_lines(OspreyConfig(), {"OSPREY_SMTP_PASSWORD": "x"}) == ""


def test_registration_gives_keycloak_the_mail_server(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, Any]] = []

    def call(url: str, *, token: str | None = None, data: Any = None, method: str | None = None,
             form: bool = False) -> tuple[int, Any]:  # fmt: skip
        verb = method or ("POST" if data is not None else "GET")
        sent.append((verb, data))
        if verb == "GET":
            return 200, {"realm": "osprey", "enabled": True}
        return 204, ""

    monkeypatch.setattr(keycloak_admin, "_call", call)
    config = OspreyConfig.model_validate({"mail": MAIL})
    said = keycloak_admin.ensure_realm_mail(
        issuer="http://id.test", realm="osprey", token="t", mail=config.mail, password="s3cret"
    )
    ((_, realm),) = [(v, d) for v, d in sent if v == "PUT"]
    assert realm["smtpServer"] == {
        "host": "smtp.example.org", "port": "587", "from": "osprey@example.org",
        "fromDisplayName": "OspreyFlow", "starttls": "true", "ssl": "false",
        "auth": "true", "user": "osprey-mailer", "password": "s3cret",
    }  # fmt: skip
    assert "s3cret" not in said
