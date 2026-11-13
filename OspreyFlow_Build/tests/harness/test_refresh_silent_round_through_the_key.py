"""The refresh's silent round passes the shared key's gate (ADR-050 Amendment 3, point 3).

On a deployment that asks for a shared key (ADR-114 Amendments 41 and 42, osprey-small), the Glass's
silent sign-in at load sends its hidden frame to `id.<host>`'s authorisation endpoint, which is
**behind** the key (only the token, the keys and the discovery document are open,
`harness.site.OPEN_ON_THE_IDENTITY_PROVIDER`). It passes because the browser holds the pass from
answering the key on the Glass's own name: `osprey_pass` is set for the base name (`Domain=<host>`,
`SameSite=Lax`), and a frame from `<host>` to `id.<host>` is a same-site request, so the browser
sends it. Then the identity provider's answer brings the frame back to `<host>/?code=…`, again with
the pass.

Driven through the real Caddy the deployment renders (`test_access_key_proxy.py`'s fixture, whose
`curl` keeps and sends cookies by a browser's domain rules), with the frame's own request headers.
Its refusal is checked too (rule 15): with no pass, the same round is asked for the key, and nothing
behind the proxy sees it. A browser that has not answered the key never has the Glass to refresh
in the first place; the 8-hour pass ending under an open Glass is the one way to meet that refusal,
and the frame then times out to the Sign in screen, whose button reaches the key's prompt.
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
