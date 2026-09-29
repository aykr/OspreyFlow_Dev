"""Sign-in for the Admin console — `06_DECISIONS.md` ADR-051, decision 4.

The setup harness (`python -m harness`, port 7100) is the Admin console: it edits the deployment's
configuration, starts and stops the stack and reads its files. Once a realm has been rendered there
is an identity provider to ask, so from then on every route requires a signed-in account holding
`osprey-admin`. Before that (nothing rendered) the console is open, because there is nothing to
sign in to and a first-time operator could otherwise never reach the wizard that renders the realm.

**Decided when the console starts, not per request.** A console started before any realm exists
stays open for its lifetime, so finishing the Launch that renders the realm does not lock the
operator out mid-flow; the next start enforces. `main()` says which it is.

**Fails closed.** Enforced and the provider not answering: nobody is admitted, and the page says the
provider is not running (not that the account was refused, ADR-044). There is deliberately no
"fall back to open".

**One way in: a server-side session behind an opaque cookie.** HttpOnly, SameSite=Lax, host-only,
absolute expiry, held in this process's memory. No bearer token is accepted here. A state-changing
request carrying a foreign `Origin` is refused (a page in the same browser posting to localhost),
and a request addressed to any host name other than `localhost` / `127.0.0.1` on the harness port is
refused (DNS rebinding). `127.0.0.1` is redirected to `localhost` so the cookie and the registered
redirect agree.

`/admin` in console mode is not touched: it stays bearer-only and answers 404 (R2).
"""

from __future__ import annotations

import html
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from harness import oidc
from harness.oidc import (
    IdentityProviderUnreachable,
    LoginAttempts,
    SessionStore,
    SignInConfig,
    default_issuer,
    handle_callback,
    rendered_realm_exists,
)
from harness.realm import (
    ADMIN_ROLE,
    DEMO_ADMIN_SUBJECT,
    HARNESS_CLIENT_ID,
    HARNESS_ORIGIN,
    HARNESS_PORT,
    HARNESS_REDIRECT_URI,
)

SESSION_COOKIE = "osprey_harness_session"
LOGIN_COOKIE = "osprey_harness_login"
PUBLIC_PATHS = frozenset({"/login", "/callback", "/logout"})
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass
class SignInSettings:
    config: SignInConfig
    sessions: SessionStore = field(default_factory=SessionStore)
    attempts: LoginAttempts = field(default_factory=LoginAttempts)


def make_settings(issuer: str) -> SignInSettings:
    return SignInSettings(
        config=SignInConfig(
            issuer=issuer,
            client_id=HARNESS_CLIENT_ID,
            redirect_uri=HARNESS_REDIRECT_URI,
            post_logout_uri=f"{HARNESS_ORIGIN}/",
        )
    )


def port_problem(port: int, *, enforced: bool) -> str | None:
    """Sign-in redirects to a fixed address, so a console on another port cannot complete it."""
    if enforced and port != HARNESS_PORT:
        return (
            f"sign-in is required and the identity provider only redirects to port {HARNESS_PORT}; "
            f"start the console on {HARNESS_PORT}, not {port}"
        )
    return None


def _allowed_hosts() -> frozenset[str]:
    return frozenset({f"localhost:{HARNESS_PORT}", f"127.0.0.1:{HARNESS_PORT}"})


def _page(status: int, title: str, body: str) -> HTMLResponse:
    """Plain, unstyled pages: they carry no colour of their own."""
    return HTMLResponse(
        '<!doctype html><html lang="en-GB"><meta charset="utf-8">'
        f"<title>{html.escape(title)} — OspreyFlow Admin console</title>"
        f"<main><h1>{html.escape(title)}</h1>{body}</main></html>",
        status_code=status,
    )


def _unreachable_page() -> HTMLResponse:
    return _page(
        503,
        "The sign-in service is not running",
        "<p>OspreyFlow's identity provider did not answer, so nobody can be signed in. "
        "This is not a problem with your account.</p>"
        "<p>Start OspreyFlow first: run <code>make launch</code>, choose <b>Start</b>, wait until "
        "it says it is running, then reload this page.</p>",
    )


def _install_routes(app: FastAPI, settings: SignInSettings) -> None:
    config = settings.config

    def signed_in_admin(request: Request) -> bool:
        identity = settings.sessions.get(request.cookies.get(SESSION_COOKIE))
        return identity is not None and identity.has_role(ADMIN_ROLE)

    @app.get("/login", include_in_schema=False)
    def login(request: Request) -> Response:
        if signed_in_admin(request):
            return RedirectResponse("/", status_code=303)
        try:
            oidc.probe(config)
        except IdentityProviderUnreachable:
            return _unreachable_page()
        url, state = settings.attempts.begin(config)
        response = RedirectResponse(url, status_code=303)
        response.set_cookie(
            LOGIN_COOKIE, state, max_age=600, httponly=True, samesite="lax", path="/"
        )
        return response

    @app.get("/callback", include_in_schema=False)
    def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> Response:
        again = '<p><a href="/login">Start again</a></p>'
        outcome = handle_callback(
            config,
            settings.attempts,
            code=code,
            state=state,
            error=error,
            login_cookie=request.cookies.get(LOGIN_COOKIE),
        )
        if outcome.kind == "invalid_link":
            return _page(400, "This sign-in link is not valid", again)
        if outcome.kind == "not_completed":
            return _page(403, "Sign-in was not completed", again)
        if outcome.kind == "unreachable":
            return _unreachable_page()
        if outcome.kind == "refused" or outcome.identity is None:
            return _page(403, "Sign-in was refused", again)
        identity = outcome.identity
        if not identity.has_role(ADMIN_ROLE):
            return _page(
                403,
                "This account is not an administrator",
                f"<p>{html.escape(identity.username)} is signed in, but the Admin console needs "
                f"an account with the <code>{ADMIN_ROLE}</code> role (the demonstration one is "
                f"<code>{DEMO_ADMIN_SUBJECT}</code>).</p>"
                '<p><a href="/logout">Sign out and use another account</a></p>',
            )
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            settings.sessions.create(identity),
            httponly=True,
            samesite="lax",
            path="/",
        )
        response.delete_cookie(LOGIN_COOKIE, path="/")
        return response

    @app.get("/logout", include_in_schema=False)
    def logout(request: Request) -> Response:
        settings.sessions.destroy(request.cookies.get(SESSION_COOKIE))
        response = RedirectResponse(config.logout_url, status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response


def install(app: FastAPI, settings: SignInSettings) -> None:
    """Adds the sign-in routes and the middleware that requires a session for everything else.
    Called before the front end is mounted at `/`, so these routes win."""
    app.state.sign_in = settings
    _install_routes(app, settings)

    async def middleware(request: Request, call_next: Any) -> Response:
        host = request.headers.get("host", "")
        if host not in _allowed_hosts():
            return Response("refused: unexpected host name", status_code=403)
        if host.startswith("127.0.0.1") and request.method == "GET":
            target = f"{HARNESS_ORIGIN}{request.url.path}"
            if request.url.query:
                target += f"?{request.url.query}"
            return RedirectResponse(target, status_code=307)
        path = request.url.path
        if path in PUBLIC_PATHS:
            response: Response = await call_next(request)
            return response
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin != f"http://{host}":
                return Response("refused: request from another origin", status_code=403)
        identity = settings.sessions.get(request.cookies.get(SESSION_COOKIE))
        if identity is None or not identity.has_role(ADMIN_ROLE):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "sign_in_required"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        admitted: Response = await call_next(request)
        return admitted

    app.middleware("http")(middleware)


__all__ = [
    "LOGIN_COOKIE",
    "PUBLIC_PATHS",
    "SESSION_COOKIE",
    "SignInSettings",
    "default_issuer",
    "install",
    "make_settings",
    "port_problem",
    "rendered_realm_exists",
]

_ = urllib.parse  # imported for callers that build addresses; kept explicit
