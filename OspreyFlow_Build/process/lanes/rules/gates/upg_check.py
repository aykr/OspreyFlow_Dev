"""UPG's checks of a deployment through its front door, as a person signs in: the Glass's public
client, authorization code with PKCE (S256), Keycloak's own sign-in form, then the Conduit's routes
with the access token, through the front proxy as the browser reaches them. Prints what each route
answered and a short summary of its body; never prints a password or a token.

    python upg_check.py <origin> <identity origin> <account> <password env var> GET:/path \
        POST:/path|{"json": "body"} ...

The password is read from the environment variable named, never from the command line. Exit 1 if
the sign-in fails or any route answers other than 2xx.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import sys
from urllib.parse import parse_qs, urlsplit

import httpx

REALM = "osprey"
CLIENT = "osprey-glass"


def _form_action(page: str) -> str:
    found = re.search(
        r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', page
    ) or re.search(r'<form[^>]*action="([^"]+)"[^>]*id="kc-form-login"', page)
    if not found:
        raise SystemExit(
            "upg-check: FAILED: no sign-in form on the identity provider's page"
        )
    return html.unescape(found.group(1))


def sign_in(origin: str, idp: str, account: str, password: str) -> str:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=")
    parts = urlsplit(origin)
    redirect = f"{parts.scheme}://{parts.netloc}/"  # the Glass's registered redirect
    base = f"{idp.rstrip('/')}/realms/{REALM}/protocol/openid-connect"
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        page = client.get(
            f"{base}/auth",
            params={
                "client_id": CLIENT, "response_type": "code", "scope": "openid",
                "redirect_uri": redirect, "state": secrets.token_urlsafe(16),
                "nonce": secrets.token_urlsafe(16), "code_challenge": challenge.decode(),
                "code_challenge_method": "S256",
            },
        )  # fmt: skip
        if page.status_code != 200:
            raise SystemExit(
                f"upg-check: FAILED: the sign-in page answered {page.status_code}"
            )
        # Keycloak marks its cookies Secure; a browser sends them to a `*.localhost` origin over
        # http (a secure context), httpx does not, so they are sent as the browser would.
        cookies = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
        sent = client.post(
            _form_action(page.text),
            data={"username": account, "password": password},
            headers={"Cookie": cookies},
        )
        location = sent.headers.get("location", "")
        code = parse_qs(urlsplit(location).query).get("code", [None])[0]
        if sent.status_code not in (302, 303) or not code:
            raise SystemExit(
                f"upg-check: FAILED: sign-in as {account} refused ({sent.status_code}, no code)"
            )
        token = client.post(
            f"{base}/token",
            data={
                "grant_type": "authorization_code", "client_id": CLIENT, "code": code,
                "redirect_uri": redirect, "code_verifier": verifier,
            },
        )  # fmt: skip
        if token.status_code != 200:
            raise SystemExit(
                f"upg-check: FAILED: the code exchange answered {token.status_code}"
            )
        return str(token.json()["access_token"])


def _summary(body: object) -> str:
    if isinstance(body, list):
        return f"list of {len(body)}"
    if isinstance(body, dict):
        parts = []
        for key, value in list(body.items())[:12]:
            if isinstance(value, list):
                parts.append(f"{key}=[{len(value)}]")
            elif isinstance(value, (str, int, float, bool)) or value is None:
                parts.append(f"{key}={str(value)[:60]}")
            elif key == "detail":  # a refusal's words, in full
                parts.append(f"detail={json.dumps(value)[:300]}")
            else:
                parts.append(f"{key}={{...}}")
        return ", ".join(parts)
    return str(body)[:120]


def main(argv: list[str]) -> int:
    origin, idp, account, password_var, *routes = argv
    token = sign_in(origin, idp, account, os.environ[password_var])
    print(f"upg-check: signed in as {account} through {CLIENT}'s form (PKCE)")
    ok = True
    with httpx.Client(
        timeout=60, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        for route in routes:
            method, _, rest = route.partition(":")
            path, _, body = rest.partition("|")  # POST:/path|{"json": "body"}
            answer = client.request(
                method,
                origin.rstrip("/") + path,
                json=json.loads(body) if body else None,
            )
            try:
                shown = _summary(answer.json())
            except (json.JSONDecodeError, ValueError):
                shown = answer.text[:120].replace("\n", " ")
            print(f"upg-check: {method} {path} -> {answer.status_code}: {shown}")
            ok = ok and 200 <= answer.status_code < 300
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
