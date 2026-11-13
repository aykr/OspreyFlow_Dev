"""The refresh's silent round through the shared key's gate (ADR-050 Amendment 3, point 4).

On a deployment that asks for a shared key (ADR-114 Amendments 41 and 42, osprey-small), the Glass's
silent sign-in at load sends its hidden frame to `id.<host>`'s authorisation endpoint, which is
**behind** the key (only the token, the keys and the discovery document are open,
`harness.site.OPEN_ON_THE_IDENTITY_PROVIDER`).

**What this proves, at the HTTP level only:** through the real Caddy the deployment renders
(`test_access_key_proxy.py`'s fixture, whose `curl` keeps and sends cookies by RFC 6265's domain
rules), a request carrying the pass that answering the key on the Glass's own name gave
(`Domain=<host>`) reaches the identity provider, and its return to the Glass passes too; without
the pass it is answered 401 with the key's Basic challenge and reaches nothing. **What it does not
prove:** that a browser sends the `SameSite=Lax` pass with a hidden frame's navigation from
`<host>` to `id.<host>` (a same-site request, so the cookie rules say it should), nor what a
browser does with the 401's challenge inside a hidden frame. Neither is measured here; Amendment 3
says so.
"""

from __future__ import annotations

from pathlib import Path

from .test_access_key_proxy import HOST, KEY, _Proxy, proxy, pytestmark  # noqa: F401  (the fixture, the skip)

#: The silent round as `oidc-client-ts` builds it (`userManager.ts`'s `renewSilently`).
SILENT_ROUND = (
    "/realms/osprey/protocol/openid-connect/auth?client_id=osprey-glass"
    f"&redirect_uri=https%3A%2F%2F{HOST}%2F&response_type=code&scope=openid&state=s1"
    "&code_challenge=c&code_challenge_method=S256&prompt=none"
)
#: What a browser sends with a hidden frame's navigation from the Glass to its identity provider.
FRAME = {"Sec-Fetch-Dest": "iframe", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "same-site"}


def test_the_silent_round_from_the_glass_passes_with_the_pass_given_on_the_glass_s_name(
    proxy: _Proxy,  # noqa: F811
    tmp_path: Path,
) -> None:
    jar = tmp_path / "jar"
    # The person answered the key on the Glass's own name, once.
    assert proxy.ask(HOST, "/", user="demo", key=KEY, jar=jar)[0] == 200
    before = len(proxy.stand_in.seen)

    status, _ = proxy.ask(f"id.{HOST}", SILENT_ROUND, headers=FRAME, jar=jar)
    assert status == 200, "the silent round was asked for the key"
    # The identity provider's answer brings the frame back to the Glass, which passes too.
    back, _ = proxy.ask(HOST, "/?state=s1&code=c1", headers=FRAME, jar=jar)
    assert back == 200
    reached = proxy.stand_in.seen[before:]
    assert len(reached) == 2 and all(seen.authorization is None for seen in reached)


def test_without_the_pass_the_silent_round_is_asked_for_the_key_and_reaches_nothing(
    proxy: _Proxy,  # noqa: F811
) -> None:
    status, fields = proxy.ask(f"id.{HOST}", SILENT_ROUND, headers=FRAME)
    assert status == 401
    assert "set-cookie" not in fields
    assert proxy.stand_in.seen == []
