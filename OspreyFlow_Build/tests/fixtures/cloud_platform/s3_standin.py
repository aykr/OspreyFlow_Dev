"""A stand-in for S3, STS and KMS that **refuses what they refuse** (`process/CLAUDE.md` rule 15's
second example; ADR-148 Amendment 7): P9's backups are proved against it, on this machine, on the
test server and as a pod on kind, where no AWS account exists.

A stand-in built from the happy path proves only that the code agrees with our hopes, so each
refusal here is one AWS gives, with its own code and its own words:

- **SigV4 is checked** (`SignatureDoesNotMatch`, `InvalidAccessKeyId`, `RequestTimeTooSkewed`,
  `XAmzContentSHA256Mismatch`), so a wrong secret or a request signed for another payload fails.
- **Temporary credentials expire** (`ExpiredToken`, "The provided token has expired."), and a
  session's token must travel with its key (`InvalidToken`).
- **STS's AssumeRoleWithWebIdentity** holds the role's trust: the token signed by the trusted
  issuer, its `aud` and `sub` the role's, not expired (`InvalidIdentityToken`, `AccessDenied`).
- **Every action is authorised** as IAM does within one account: an explicit deny in the role's
  policy or the bucket's wins; otherwise either may allow; nothing allows by default
  (`AccessDenied`). The conditions modelled are the ones our Terraform writes (`Bool`,
  `StringEquals`/`StringNotEquals` and their `IfExists`, `Null`, `ArnEquals`/`ArnNotEquals`).
- **SSE-KMS asks KMS**, as KMS judges it with the key's own policy where the config gives one
  (`keys`: an explicit deny wins, a grant naming the role is enough, the root's delegates to IAM):
  a write to a bucket encrypted by a customer key needs
  `kms:GenerateDataKey` on that key, a read or a multipart completion `kms:Decrypt`, as S3 asks
  on the caller's behalf (`AccessDenied`, naming the KMS action and the key).

**Not modelled, and said so**: a key with no policy in the config is taken as having the default
key policy (the account's IAM delegated); an STS session policy, virtual-host addressing (path style
only), versioning, object lock and presigned URLs (refused, `AccessDenied`). A chunked upload's
per-chunk signatures are not checked; its seed signature is.

    python s3_standin.py --config standin.json --port 9000 [--tls-cert c --tls-key k]
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from xml.sax.saxutils import escape

#: S3's own AWS-managed key, which `aws:kms` with no key named uses.
AWS_MANAGED_S3_KEY = "arn:aws:kms:aws-managed:alias/aws/s3"
#: S3's own tolerance for a request's clock (`RequestTimeTooSkewed`).
SKEW = dt.timedelta(minutes=15)
#: An OpenSearch Service domain's tolerance: five minutes ("Signature expired"), not S3's fifteen.
DOMAIN_SKEW = dt.timedelta(minutes=5)
#: The poc domain's largest request payload (t3.medium.search: 10 MiB), answered 413 above it.
DOMAIN_MAX_BODY = 10 * 1024 * 1024
UNSIGNED = "UNSIGNED-PAYLOAD"
STREAMING = ("STREAMING-",)
S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


class Refused(Exception):
    """One of AWS's own refusals: its HTTP status, code and words."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------------------------------------------------------------------------------------
# Policies, as IAM evaluates them within one account
# ---------------------------------------------------------------------------------------------


def _listed(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _glob(pattern: str, value: str) -> bool:
    return fnmatch.fnmatchcase(value, pattern)


def _condition_holds(conditions: dict[str, Any], context: dict[str, str]) -> bool:
    """Whether every condition block holds for `context`. An operator this stand-in does not know
    is refused loudly rather than read as true (a policy it cannot read is not one it may pass)."""
    for operator, keys in conditions.items():
        if_exists = operator.endswith("IfExists")
        base = operator.removesuffix("IfExists")
        for key, wanted in keys.items():
            wanted_values = [str(w).lower() if base == "Bool" else str(w) for w in _listed(wanted)]
            present = key in context
            actual = context.get(key)
            if base == "Null":
                # `Null: true` holds when the key is absent.
                want_absent = wanted_values[0].lower() == "true"
                if want_absent != (not present):
                    return False
                continue
            if not present:
                if if_exists:
                    continue
                # A negated operator on an absent key holds in IAM; a positive one does not.
                if base in {"StringNotEquals", "ArnNotEquals", "ArnNotLike", "StringNotLike"}:
                    continue
                return False
            assert actual is not None
            if base == "Bool":
                ok = actual.lower() in wanted_values
            elif base == "StringEquals" or base == "ArnEquals":
                ok = actual in wanted_values
            elif base == "StringNotEquals" or base == "ArnNotEquals":
                ok = actual not in wanted_values
            elif base in {"StringLike", "ArnLike"}:
                ok = any(_glob(w, actual) for w in wanted_values)
            elif base in {"StringNotLike", "ArnNotLike"}:
                ok = not any(_glob(w, actual) for w in wanted_values)
            else:
                raise ValueError(f"the stand-in does not know the condition operator {operator}")
            if not ok:
                return False
    return True


def _statement_matches(
    statement: dict[str, Any],
    action: str,
    resource: str,
    context: dict[str, str],
    principal: str | None,
) -> bool:
    if principal is not None and "Principal" in statement:
        named = statement["Principal"]
        arns = ["*"] if named == "*" else _listed(named.get("AWS", []))
        if not any(a == "*" or a == principal for a in arns):
            return False
    actions = _listed(statement.get("Action", []))
    if "NotAction" in statement:
        if any(_glob(a.lower(), action.lower()) for a in _listed(statement["NotAction"])):
            return False
    elif not any(_glob(a.lower(), action.lower()) for a in actions):
        return False
    resources = _listed(statement.get("Resource", []))
    if not any(_glob(r, resource) for r in resources):
        return False
    return _condition_holds(statement.get("Condition", {}), context)


def evaluate(
    policies: list[dict[str, Any]],
    action: str,
    resource: str,
    context: dict[str, str],
    *,
    principal: str | None = None,
) -> str:
    """`deny`, `allow` or `none` for one action over `policies` (identity policies, or a
    resource policy when `principal` is given)."""
    verdict = "none"
    for policy in policies:
        for statement in _listed(policy.get("Statement", [])):
            if _statement_matches(statement, action, resource, context, principal):
                if statement.get("Effect") == "Deny":
                    return "deny"
                verdict = "allow"
    return verdict


# ---------------------------------------------------------------------------------------------
# Who is calling
# ---------------------------------------------------------------------------------------------


@dataclass
class Principal:
    arn: str
    secret: str
    policies: list[dict[str, Any]]
    token: str | None = None
    expires: dt.datetime | None = None
    access_key: str = ""


@dataclass
class Role:
    arn: str
    policies: list[dict[str, Any]]
    #: The trust: the issuer whose signature it accepts (HS256 by this shared secret, standing in
    #: for the cluster's OIDC provider), and the `sub` and `aud` it requires.
    issuer_secret: str
    subject: str
    audience: str = "sts.amazonaws.com"
    max_seconds: int = 3600
    #: The cluster's own issuer instead (on kind: its service-account tokens, RS256, verified by
    #: the keys `kubectl get --raw /openid/v1/jwks` gives, and its `iss`), as IRSA's OIDC
    #: provider verifies them on EKS.
    jwks: dict[str, Any] | None = None
    issuer: str | None = None
    #: The role's trust document as the Terraform writes it (`backups.trust_policy`): when given, it
    #: alone decides, its conditions on `<issuer>:sub` and `<issuer>:aud` read from the token.
    trust: dict[str, Any] | None = None


@dataclass
class Bucket:
    name: str
    policy: dict[str, Any] | None = None
    kms_key: str | None = None


#: S3's smallest part, but for an upload's last (EntityTooSmall below it).
MIN_PART = 5 * 1024 * 1024


@dataclass
class Upload:
    bucket: str
    key: str
    kms_key: str | None
    parts: dict[int, bytes] = field(default_factory=dict)


@dataclass
class StandIn:
    """Everything the stand-in holds: who may call, the buckets and their objects."""

    root: Path
    region: str = "eu-west-2"
    users: dict[str, Principal] = field(default_factory=dict)
    roles: dict[str, Role] = field(default_factory=dict)
    buckets: dict[str, Bucket] = field(default_factory=dict)
    #: Each KMS key's own policy, by its ARN (a key not here has the default key policy).
    keys: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, Principal] = field(default_factory=dict)
    uploads: dict[str, Upload] = field(default_factory=dict)
    #: Whether the connection in front is TLS (`aws:SecureTransport`): set when the stand-in
    #: serves TLS itself.
    secure: bool = False
    clock: Callable[[], dt.datetime] = _now
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: Every refusal given, for a test to read back (`(code, message)`).
    refusals: list[tuple[str, str]] = field(default_factory=list)
    #: The namespace's OpenSearch domains (ADR-148 Amendment 13), by the host the pods ask: the roles
    #: its access policy admits (`es:ESHttp*`) and the OpenSearch behind it.
    domains: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict[str, Any], root: Path) -> StandIn:
        stand_in = cls(root=root, region=config.get("region", "eu-west-2"))
        stand_in.configure(config)
        return stand_in

    def configure(self, config: dict[str, Any]) -> None:
        """Who may call and each bucket's policy and key, from `config`; the objects kept. As on
        AWS, a session already running goes on and meets its role's policy as it now stands; a
        session whose role is gone ends."""
        stand_in = self
        with self.lock:
            self.users.clear()
            self.roles.clear()
        for user in config.get("users", []):
            stand_in.users[user["access_key"]] = Principal(
                arn=user["arn"], secret=user["secret_key"], policies=user.get("policies", [])
            )
        for role in config.get("roles", []):
            stand_in.roles[role["arn"]] = Role(
                arn=role["arn"],
                policies=role.get("policies", []),
                issuer_secret=role["issuer_secret"],
                subject=role["subject"],
                audience=role.get("audience", "sts.amazonaws.com"),
                max_seconds=int(role.get("max_seconds", 3600)),
                jwks=role.get("jwks"),
                issuer=role.get("issuer"),
                trust=role.get("trust"),
            )
        with self.lock:
            for key, session in list(self.sessions.items()):
                role = self.roles.get(_role_of(session.arn))
                if role is None:
                    del self.sessions[key]
                else:
                    session.policies = role.policies
        stand_in.keys = {k["arn"]: k["policy"] for k in config.get("keys", [])}
        self.configure_domains(config.get("domains", []))
        stand_in.buckets.clear()
        for bucket in config.get("buckets", []):
            stand_in.buckets[bucket["name"]] = Bucket(
                name=bucket["name"], policy=bucket.get("policy"), kms_key=bucket.get("kms_key")
            )
            (self.root / bucket["name"]).mkdir(parents=True, exist_ok=True)

    def configure_domains(self, domains: list[dict[str, Any]]) -> None:
        """Each OpenSearch domain: `host` (its endpoint, as the pods ask it), `roles` (the role ARNs its
        access policy admits) and `upstream` (the OpenSearch behind it, `http://host:port`)."""
        self.domains = {d["host"]: {"roles": list(d["roles"]), "upstream": d["upstream"].rstrip("/")}
                        for d in domains}  # fmt: skip

    # -- objects on disk ------------------------------------------------------------------------

    def _path(self, bucket: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()
        return self.root / bucket / digest

    def put(self, bucket: str, key: str, body: bytes, kms_key: str | None) -> str:
        etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
        path = self._path(bucket, key)
        path.write_bytes(body)
        meta = {"key": key, "etag": etag, "kms_key": kms_key, "size": len(body),
                "modified": self.clock().strftime("%Y-%m-%dT%H:%M:%S.000Z")}  # fmt: skip
        path.with_suffix(".json").write_text(json.dumps(meta))
        return etag

    def meta(self, bucket: str, key: str) -> dict[str, Any] | None:
        path = self._path(bucket, key).with_suffix(".json")
        return json.loads(path.read_text()) if path.exists() else None

    def read(self, bucket: str, key: str) -> bytes:
        return self._path(bucket, key).read_bytes()

    def delete(self, bucket: str, key: str) -> None:
        path = self._path(bucket, key)
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)

    def listing(self, bucket: str) -> list[dict[str, Any]]:
        metas = [json.loads(p.read_text()) for p in (self.root / bucket).glob("*.json")]
        return sorted(metas, key=lambda m: m["key"])

    # -- STS ------------------------------------------------------------------------------------

    def assume_role_with_web_identity(self, params: dict[str, str]) -> Principal:
        role = self.roles.get(params.get("RoleArn", ""))
        token = params.get("WebIdentityToken", "")
        if role is None:
            raise Refused(403, "AccessDenied", "Not authorized to perform sts:AssumeRoleWithWebIdentity")
        claims = (
            _verify_rs256(token, role.jwks, role.issuer, self.clock())
            if role.jwks is not None
            else _verify_jwt(token, role.issuer_secret, self.clock())
        )
        if role.trust is not None:
            if not _trusted(role.trust, claims):
                raise Refused(403, "AccessDenied", "Not authorized to perform sts:AssumeRoleWithWebIdentity")
        elif claims.get("aud") != role.audience and role.audience not in _listed(claims.get("aud")):
            raise Refused(403, "AccessDenied", "Not authorized to perform sts:AssumeRoleWithWebIdentity")
        elif claims.get("sub") != role.subject:
            raise Refused(403, "AccessDenied", "Not authorized to perform sts:AssumeRoleWithWebIdentity")
        seconds = int(params.get("DurationSeconds", "3600"))
        if seconds < 900 or seconds > role.max_seconds:
            raise Refused(
                400,
                "ValidationError",
                "The requested DurationSeconds exceeds the MaxSessionDuration set for this role.",
            )
        session = Principal(
            arn=role.arn.replace(":role/", ":assumed-role/").replace("iam::", "sts::")
            + "/" + params.get("RoleSessionName", "session"),
            secret=secrets.token_urlsafe(30),
            policies=role.policies,
            token=secrets.token_urlsafe(48),
            expires=self.clock() + dt.timedelta(seconds=seconds),
        )  # fmt: skip
        session.access_key = "ASIA" + secrets.token_hex(8).upper()
        with self.lock:
            self.sessions[session.access_key] = session
        return session

    def expire(self, access_key: str | None = None) -> None:
        """Every session (or one) expired now: what an hour on the platform does."""
        with self.lock:
            for key, session in self.sessions.items():
                if access_key is None or key == access_key:
                    session.expires = self.clock() - dt.timedelta(seconds=1)

    # -- who signed this ------------------------------------------------------------------------

    def caller(
        self, method: str, raw_path: str, headers: dict[str, str], body: bytes, *, service_of: str = ""
    ) -> Principal:
        """Who signed this request. `service_of`: the service it must be signed for (the domain's
        `es`); otherwise any, as S3's own requests have always been taken."""
        auth = headers.get("authorization")
        if not auth:
            if "X-Amz-Signature" in raw_path:
                raise Refused(403, "AccessDenied", "Presigned requests are not modelled by the stand-in")
            raise Refused(403, "AccessDenied", "Access Denied")
        match = re.match(
            r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/([^/]+)/aws4_request,\s*"
            r"SignedHeaders=([^,]+),\s*Signature=([0-9a-f]+)",
            auth,
        )
        if not match:
            raise Refused(400, "AuthorizationHeaderMalformed", "The authorization header is malformed")
        access_key, day, region, service, signed_headers, signature = match.groups()
        if service_of and service != service_of:
            raise Refused(403, "IncompleteSignature",
                          f"Credential should be scoped to correct service: '{service_of}'.")  # fmt: skip
        if region != self.region:
            # S3's own words for a request signed for another region.
            raise Refused(400, "AuthorizationHeaderMalformed",
                          f"The authorization header is malformed; the region '{region}' is wrong; "
                          f"expecting '{self.region}'")  # fmt: skip
        principal = self.users.get(access_key) or self.sessions.get(access_key)
        if principal is None:
            raise Refused(
                403,
                "InvalidAccessKeyId",
                "The AWS Access Key Id you provided does not exist in our records.",
            )
        amz_date = headers.get("x-amz-date", "")
        try:
            when = dt.datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.UTC)
        except ValueError as error:
            raise Refused(403, "AccessDenied", "AWS authentication requires a valid Date or x-amz-date header") from error
        if service == "es" and abs(self.clock() - when) > DOMAIN_SKEW:
            earliest = (self.clock() - DOMAIN_SKEW).strftime("%Y%m%dT%H%M%SZ")
            raise Refused(403, "RequestTimeTooSkewed",
                          f"Signature expired: {amz_date} is now earlier than {earliest} "
                          f"({self.clock():%Y%m%dT%H%M%SZ} - 5 min.)")  # fmt: skip
        if abs(self.clock() - when) > SKEW:
            raise Refused(
                403,
                "RequestTimeTooSkewed",
                "The difference between the request time and the current time is too large.",
            )
        if principal.token is not None:
            if headers.get("x-amz-security-token") != principal.token:
                raise Refused(403, "InvalidToken", "The provided token is malformed or otherwise invalid.")
            assert principal.expires is not None
            if self.clock() >= principal.expires:
                raise Refused(400, "ExpiredToken", "The provided token has expired.")
        payload_hash = headers.get("x-amz-content-sha256") or hashlib.sha256(body).hexdigest()
        if service in ("s3", "es") and not payload_hash.startswith(STREAMING) and payload_hash != UNSIGNED:
            if hashlib.sha256(body).hexdigest() != payload_hash:
                raise Refused(
                    400,
                    "XAmzContentSHA256Mismatch",
                    "The provided 'x-amz-content-sha256' header does not match what was computed.",
                )
        path, _, query = raw_path.partition("?")
        canonical_query = "&".join(
            sorted(
                f"{_uri(k, True)}={_uri(v, True)}"
                for k, v in urllib.parse.parse_qsl(query, keep_blank_values=True)
            )
        )
        names = signed_headers.split(";")
        canonical_headers = "".join(
            f"{n}:{' '.join(headers.get(n, '').split())}\n" for n in names
        )
        canonical = "\n".join(
            [method, _canonical_path(path, service), canonical_query, canonical_headers,
             signed_headers, payload_hash]
        )  # fmt: skip
        scope = f"{day}/{region}/{service}/aws4_request"
        to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
        )
        key = f"AWS4{principal.secret}".encode()
        for part in (day, region, service, "aws4_request"):
            key = hmac.new(key, part.encode(), hashlib.sha256).digest()
        expected = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise Refused(
                403,
                "SignatureDoesNotMatch",
                "The request signature we calculated does not match the signature you provided. "
                "Check your key and signing method.",
            )
        return principal

    # -- may they ------------------------------------------------------------------------------

    def authorise(
        self, principal: Principal, action: str, resource: str, bucket: Bucket, context: dict[str, str]
    ) -> None:
        context = {**context, "aws:PrincipalArn": _role_of(principal.arn),
                   "aws:SecureTransport": "true" if self.secure else "false"}  # fmt: skip
        identity = evaluate(principal.policies, action, resource, context)
        held = (
            evaluate([bucket.policy], action, resource, context, principal=principal.arn)
            if bucket.policy
            else "none"
        )
        if bucket.policy and held == "none":
            # A statement naming the role's own ARN (not the session's) counts for the session.
            held = evaluate(
                [bucket.policy], action, resource, context, principal=_role_of(principal.arn)
            )
        if "deny" in (identity, held) or "allow" not in (identity, held):
            raise Refused(403, "AccessDenied", "Access Denied")

    def kms(self, principal: Principal, action: str, key_arn: str) -> None:
        """S3 asks KMS on the caller's behalf (`kms:ViaService` is S3 in the region); KMS's refusal
        comes back as S3's `AccessDenied`. S3's own AWS-managed key needs no grant of the caller's.
        A key with its own policy (`keys` in the config) is judged as KMS judges it: an explicit
        deny in either policy wins; the key policy naming the role is enough alone; the key policy
        naming the account's root delegates to the role's IAM policy, for that action only; else
        refused. A key with none is the default key policy's: the role's IAM policy alone."""
        if key_arn == AWS_MANAGED_S3_KEY:
            return
        role = _role_of(principal.arn)
        context = {"aws:PrincipalArn": role, "kms:ViaService": f"s3.{self.region}.amazonaws.com"}
        iam = evaluate(principal.policies, action, key_arn, context)
        key_policy = self.keys.get(key_arn)
        if key_policy is None:
            verdict, kind = iam, "identity-based"
        else:
            root = re.sub(r":(role|assumed-role)/.*$", ":root", role).replace("arn:aws:sts::", "arn:aws:iam::")
            named = evaluate([key_policy], action, key_arn, context, principal=role)
            delegated = evaluate([key_policy], action, key_arn, context, principal=root)
            if "deny" in (named, iam):
                verdict, kind = "deny", "identity-based" if iam == "deny" else "resource-based"
            elif named == "allow" or (delegated == "allow" and iam == "allow"):
                verdict, kind = "allow", ""
            else:
                verdict, kind = "none", "resource-based" if delegated != "allow" else "identity-based"
        if verdict != "allow":
            reason = (
                f"with an explicit deny in a {kind} policy"
                if verdict == "deny"
                else f"because no {kind} policy allows the " + action + " action"
            )
            raise Refused(
                403,
                "AccessDenied",
                f"User: {principal.arn} is not authorized to perform: {action} on resource: "
                f"{key_arn} {reason}",
            )


def _trusted(trust: dict[str, Any], claims: dict[str, Any]) -> bool:
    """Whether a trust document lets this token assume its role, as STS reads one: an Allow of
    `sts:AssumeRoleWithWebIdentity` whose `Principal.Federated` is the OIDC provider **of the token's
    own issuer** (`…:oidc-provider/<iss without its scheme>`), and whose conditions hold, with
    `<issuer>:sub` and `<issuer>:aud` being the token's (each `aud` it names tried, as IAM tries a
    multi-valued key). A token of another issuer meets no statement."""
    issuer = str(claims.get("iss", "")).removeprefix("https://")
    for statement in trust.get("Statement", []):
        if statement.get("Effect") != "Allow":
            continue
        if "sts:AssumeRoleWithWebIdentity" not in _listed(statement.get("Action", [])):
            continue
        federated = _listed((statement.get("Principal") or {}).get("Federated", []))
        if not issuer or not any(str(f).endswith(f":oidc-provider/{issuer}") for f in federated):
            continue
        conditions = statement.get("Condition", {})
        for aud in _listed(claims.get("aud")) or [None]:
            context = {f"{issuer}:sub": str(claims.get("sub"))}
            if aud is not None:
                context[f"{issuer}:aud"] = str(aud)
            if _condition_holds(conditions, context):
                return True
    return False


def _role_of(arn: str) -> str:
    """An assumed role's session ARN as its role's (`aws:PrincipalArn` is the role's)."""
    match = re.match(r"arn:aws:sts::(\d+):assumed-role/([^/]+)/.+", arn)
    return f"arn:aws:iam::{match.group(1)}:role/{match.group(2)}" if match else arn


def _canonical_path(path: str, service: str) -> str:
    """SigV4's canonical URI: S3's is the path as sent; every other service's (OpenSearch's `es`
    among them) is the path with its dot segments removed and percent-encoded once more, as
    botocore's `SigV4Auth` signs it (so `a,b`, `*`, `:` and an encoded `/` hash as the real
    domain hashes them)."""
    if service == "s3":
        return path or "/"
    kept: list[str] = []
    for part in path.split("/"):
        if part == "..":
            if kept:
                kept.pop()
        elif part and part != ".":
            kept.append(part)
    normalized = ("/" if path.startswith("/") else "") + "/".join(kept)
    if path.endswith("/") and kept:
        normalized += "/"
    return urllib.parse.quote(normalized or "/", safe="/~")


def _uri(text: str, encode_slash: bool) -> str:
    return urllib.parse.quote(text, safe="-_.~" + ("" if encode_slash else "/"))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


#: The issuer the tests' tokens name, as an EKS cluster's OIDC issuer is named.
TEST_ISSUER = "https://oidc.eks.eu-west-2.amazonaws.com/id/0A1B2C3D"


def mint_token(issuer_secret: str, *, sub: str, aud: str = "sts.amazonaws.com", seconds: int = 3600,
               now: dt.datetime | None = None, iss: str = TEST_ISSUER) -> str:  # fmt: skip
    """A web identity token as the cluster's issuer signs one (HS256 by the stand-in's secret)."""
    now = now or _now()
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"sub": sub, "aud": aud, "iss": iss, "iat": int(now.timestamp()),
                                  "exp": int(now.timestamp()) + seconds}).encode())  # fmt: skip
    signature = hmac.new(issuer_secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256)
    return f"{header}.{payload}.{_b64url(signature.digest())}"


def _verify_jwt(token: str, secret: str, now: dt.datetime) -> dict[str, Any]:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64url(signature)):
            raise ValueError("signature")
        claims: dict[str, Any] = json.loads(_unb64url(payload))
    except (ValueError, json.JSONDecodeError) as error:
        raise Refused(400, "InvalidIdentityToken", "The web identity token that was passed could not be validated by AWS.") from error
    if int(claims.get("exp", 0)) <= now.timestamp():
        raise Refused(400, "ExpiredTokenException", "Token is expired")
    return claims


def _verify_rs256(token: str, jwks: dict[str, Any], issuer: str | None, now: dt.datetime) -> dict[str, Any]:
    """A token the cluster signed, by its published keys (PyJWT, the Conduit's own)."""
    import jwt

    try:
        kid = jwt.get_unverified_header(token).get("kid")
        key = next(k for k in jwks.get("keys", []) if k.get("kid") == kid)
        claims: dict[str, Any] = jwt.decode(
            token,
            jwt.PyJWK(key).key,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False},
        )
    except (StopIteration, jwt.PyJWTError) as error:
        raise Refused(400, "InvalidIdentityToken", "The web identity token that was passed could not be validated by AWS.") from error
    if issuer is not None and claims.get("iss") != issuer:
        raise Refused(400, "InvalidIdentityToken", "The web identity token that was passed could not be validated by AWS.")
    if int(claims.get("exp", 0)) <= now.timestamp():
        raise Refused(400, "ExpiredTokenException", "Token is expired")
    return claims


def decode_chunked(body: bytes) -> bytes:
    """An `aws-chunked` body's data (signed chunks or the unsigned-with-trailer form)."""
    out = bytearray()
    rest = body
    while rest:
        line, _, rest = rest.partition(b"\r\n")
        size = int(line.split(b";")[0], 16)
        if size == 0:
            break
        out += rest[:size]
        rest = rest[size + 2 :]
    return bytes(out)


# ---------------------------------------------------------------------------------------------
# The HTTP front
# ---------------------------------------------------------------------------------------------


def _xml(root: str, body: str) -> bytes:
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<{root} xmlns="{S3_NS}">{body}</{root}>'.encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Server

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if os.environ.get("S3_STANDIN_LOG"):
            super().log_message(format, *args)

    # Every verb goes through one place, so no path skips the checks.
    def do_GET(self) -> None:
        self._serve("GET")

    def do_PUT(self) -> None:
        self._serve("PUT")

    def do_POST(self) -> None:
        self._serve("POST")

    def do_DELETE(self) -> None:
        self._serve("DELETE")

    def do_HEAD(self) -> None:
        self._serve("HEAD")

    def _send(self, status: int, body: bytes = b"", headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.send_header("x-amz-request-id", uuid.uuid4().hex[:16].upper())
        if "Content-Length" not in (headers or {}):
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _refuse(self, refusal: Refused) -> None:
        stand_in = self.server.stand_in
        stand_in.refusals.append((refusal.code, refusal.message))
        error = f"<Code>{refusal.code}</Code><Message>{escape(refusal.message)}</Message>"
        if getattr(self, "_sts_call", False):
            # STS's query protocol wraps its error, and says whose fault it was.
            body = (
                '<ErrorResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/"><Error>'
                f"<Type>Sender</Type>{error}</Error><RequestId>standin</RequestId></ErrorResponse>"
            ).encode()
        else:
            body = (
                f'<?xml version="1.0" encoding="UTF-8"?>\n<Error>{error}'
                "<RequestId>standin</RequestId></Error>"
            ).encode()
        self._send(refusal.status, body, {"Content-Type": "application/xml"})

    #: The domain's own words for each refusal of the signature (OpenSearch Service answers 403, in
    #: JSON, for every one of them).
    _DOMAIN_WORDS = {
        "InvalidToken": "The security token included in the request is invalid.",
        "ExpiredToken": "The security token included in the request is expired",
        "InvalidAccessKeyId": "The security token included in the request is invalid.",
        # The domain has no payload-hash error of its own: a body changed after signing is a signature
        # that does not match.
        "XAmzContentSHA256Mismatch": "The request signature we calculated does not match the signature "
        "you provided. Check your AWS Secret Access Key and signing method.",
    }

    def _domain(self, method: str, raw_body: bytes, headers: dict[str, str], domain: dict[str, Any]) -> None:
        """The namespace's OpenSearch domain: signed for `es` by a session of a role its access policy
        admits, or refused 403 in its own words; then the request passed to the OpenSearch behind."""
        stand_in = self.server.stand_in
        host = headers.get("host", "").rsplit(":", 1)[0]
        action = f"es:ESHttp{method.capitalize()}"
        # The domain's own ARN: its account (its roles'), its name (`vpc-<name>-<id>.<region>...`).
        account = domain["roles"][0].split(":")[4] if domain["roles"] else ""
        name = host.split(".", 1)[0].removeprefix("vpc-").rsplit("-", 1)[0]
        path = self.path.partition("?")[0]
        resource = f"arn:aws:es:{stand_in.region}:{account}:domain/{name}{path}"

        def refuse(message: str) -> None:
            stand_in.refusals.append(("es", message))
            data = json.dumps({"message": message}).encode()
            self._send(403, data, {"Content-Type": "application/json"})

        # Before anything else, as the domain's front answers it.
        if len(raw_body) > DOMAIN_MAX_BODY:
            stand_in.refusals.append(("es", "413"))
            words = {"Message": f"Request size exceeded {DOMAIN_MAX_BODY} bytes"}
            data = json.dumps(words).encode()
            self._send(413, data, {"Content-Type": "application/json"})
            return
        if not headers.get("authorization"):
            refuse(f"User: anonymous is not authorized to perform: {action} on resource: {resource}")
            return
        try:
            principal = stand_in.caller(method, self.path, headers, raw_body, service_of="es")
        except Refused as refusal:
            if refusal.code == "AuthorizationHeaderMalformed" and "region" in refusal.message:
                refuse(f"Credential should be scoped to a valid region. Expecting '{stand_in.region}'.")
            else:
                refuse(self._DOMAIN_WORDS.get(refusal.code, refusal.message))
            return
        if _role_of(principal.arn) not in domain["roles"]:
            refuse(f"User: {principal.arn} is not authorized to perform: {action} on resource: {resource}")
            return
        passed = {k: v for k, v in headers.items() if k in ("content-type", "content-encoding")}
        request = urllib.request.Request(domain["upstream"] + self.path, data=raw_body or None,
                                         method=method, headers=passed)  # fmt: skip
        try:
            with urllib.request.urlopen(request, timeout=60) as answer:
                status, data, kind = answer.status, answer.read(), answer.headers.get("Content-Type")
        except urllib.error.HTTPError as error:
            status, data, kind = error.code, error.read(), error.headers.get("Content-Type")
        except TimeoutError:
            words = {"message": "upstream: no answer in 60 s"}
            status, data, kind = 504, json.dumps(words).encode(), None
        except OSError as error:
            status, data, kind = 502, json.dumps({"message": f"upstream: {error}"}).encode(), None
        self._send(status, data, {"Content-Type": kind or "application/json"})

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            data = bytearray()
            while True:
                size = int(self.rfile.readline().split(b";")[0], 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    break
                data += self.rfile.read(size)
                self.rfile.readline()
            return bytes(data)
        return self.rfile.read(length) if length else b""

    def _serve(self, method: str) -> None:
        self._sts_call = False
        body = self._body()
        try:
            self._dispatch(method, body)
        except Refused as refusal:
            self._refuse(refusal)

    def _dispatch(self, method: str, raw_body: bytes) -> None:
        stand_in = self.server.stand_in
        headers = {k.lower(): v for k, v in self.headers.items()}
        domain = stand_in.domains.get(headers.get("host", "").rsplit(":", 1)[0])
        if domain is not None:
            self._domain(method, raw_body, headers, domain)
            return
        path, _, query = self.path.partition("?")
        params = dict(urllib.parse.parse_qsl(query, keep_blank_values=True))
        # The stand-in's own lever, for a run on kind (no bucket may start with `_`): every
        # session expired now, as an hour on the platform would leave them.
        if method == "POST" and path == "/_standin/expire":
            stand_in.expire()
            self._send(204)
            return
        if method == "POST" and path == "/_standin/configure":
            stand_in.configure(json.loads(raw_body))
            self._send(204)
            return
        # STS: a form POST to the root, unsigned for AssumeRoleWithWebIdentity (as AWS takes it).
        if method == "POST" and path == "/" and "Action=" in raw_body.decode(errors="replace"):
            self._sts_call = True
            form = dict(urllib.parse.parse_qsl(raw_body.decode()))
            if form.get("Action") != "AssumeRoleWithWebIdentity":
                raise Refused(400, "InvalidAction", f"Could not find operation {form.get('Action')}")
            self._sts(form)
            return
        principal = stand_in.caller(method, self.path, headers, raw_body)
        body = raw_body
        if headers.get("x-amz-content-sha256", "").startswith(STREAMING) or "aws-chunked" in headers.get(
            "content-encoding", ""
        ):
            body = decode_chunked(raw_body)
        parts = urllib.parse.unquote(path).lstrip("/").split("/", 1)
        bucket_name = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        if not bucket_name:
            raise Refused(403, "AccessDenied", "ListBuckets is not modelled by the stand-in")
        bucket = stand_in.buckets.get(bucket_name)
        if bucket is None:
            raise Refused(404, "NoSuchBucket", "The specified bucket does not exist")
        bucket_arn = f"arn:aws:s3:::{bucket_name}"
        object_arn = f"{bucket_arn}/{key}"
        sse = headers.get("x-amz-server-side-encryption")
        sse_key = headers.get("x-amz-server-side-encryption-aws-kms-key-id")
        context: dict[str, str] = {}
        if sse is not None:
            context["s3:x-amz-server-side-encryption"] = sse
        if sse_key is not None:
            context["s3:x-amz-server-side-encryption-aws-kms-key-id"] = sse_key
        if "prefix" in params:
            context["s3:prefix"] = params["prefix"]

        def allow(action: str, resource: str) -> None:
            stand_in.authorise(principal, action, resource, bucket, context)

        def kms_key_for_write() -> str | None:
            if sse is not None and sse != "aws:kms":
                if sse == "AES256":
                    return None
                raise Refused(400, "InvalidArgument", "The encryption method specified is not supported")
            if sse == "aws:kms" and not sse_key:
                # `aws:kms` named without a key is S3's own AWS-managed key, never the bucket's
                # (the lane-reviewer's finding): the bucket's policy must refuse it (`NoKeyNamed`).
                return AWS_MANAGED_S3_KEY
            return sse_key or bucket.kms_key

        if not key:
            if method == "GET" and "uploads" in params:
                allow("s3:ListBucketMultipartUploads", bucket_arn)
                self._send(200, _xml("ListMultipartUploadsResult", f"<Bucket>{bucket_name}</Bucket>"))
                return
            if method == "GET" and "location" in params:
                allow("s3:GetBucketLocation", bucket_arn)
                self._send(200, _xml("LocationConstraint", stand_in.region))
                return
            if method in {"GET", "HEAD"}:
                allow("s3:ListBucket", bucket_arn)
                if method == "HEAD":
                    self._send(200, headers={"x-amz-bucket-region": stand_in.region})
                    return
                self._list(bucket_name, params)
                return
            if method == "POST" and "delete" in params:
                self._delete_many(bucket_name, body, allow)
                return
            # A bucket's own settings (versioning, policy, lifecycle): IAM's action of that name,
            # which no backup role is given; one that is allowed is not modelled.
            sub = next(iter(params), "")
            verb = {"PUT": "Put", "DELETE": "Delete", "GET": "Get"}.get(method, method.title())
            allow(f"s3:{verb}Bucket{sub.title()}", bucket_arn)
            raise Refused(501, "NotImplemented", f"The stand-in does not model {method} ?{sub}")

        if method == "PUT" and "partNumber" in params:
            allow("s3:PutObject", object_arn)
            upload = stand_in.uploads.get(params.get("uploadId", ""))
            if upload is None or upload.bucket != bucket_name or upload.key != key:
                raise Refused(404, "NoSuchUpload", "The specified upload does not exist.")
            if upload.kms_key:
                stand_in.kms(principal, "kms:GenerateDataKey", upload.kms_key)
            if "x-amz-copy-source" in headers:
                source = self._copy_source(headers["x-amz-copy-source"], principal, context)
                upload.parts[int(params["partNumber"])] = source
                etag = hashlib.md5(source, usedforsecurity=False).hexdigest()
                self._send(200, _xml("CopyPartResult", f'<ETag>"{etag}"</ETag>'))
                return
            upload.parts[int(params["partNumber"])] = body
            etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
            self._send(200, headers={"ETag": f'"{etag}"'})
            return
        if method == "POST" and "uploads" in params:
            allow("s3:PutObject", object_arn)
            kms_key = kms_key_for_write()
            if kms_key:
                stand_in.kms(principal, "kms:GenerateDataKey", kms_key)
            upload_id = uuid.uuid4().hex
            stand_in.uploads[upload_id] = Upload(bucket_name, key, kms_key)
            self._send(200, _xml(
                "InitiateMultipartUploadResult",
                f"<Bucket>{bucket_name}</Bucket><Key>{escape(key)}</Key><UploadId>{upload_id}</UploadId>",
            ), self._sse_headers(kms_key))  # fmt: skip
            return
        if method == "POST" and "uploadId" in params:
            allow("s3:PutObject", object_arn)
            upload = stand_in.uploads.get(params["uploadId"])
            if upload is None:
                raise Refused(404, "NoSuchUpload", "The specified upload does not exist.")
            if upload.kms_key:
                # Completing a multipart upload under SSE-KMS asks KMS to decrypt the data key.
                stand_in.kms(principal, "kms:Decrypt", upload.kms_key)
            # S3's own refusals of a completion, each a 400 with the upload kept (it may be
            # completed again, or aborted): the parts listed in ascending order, each uploaded and
            # named by its own ETag, and every part but the last at least 5 MiB.
            listed = []
            for part in ElementTree.fromstring(body).iter():
                if part.tag.endswith("Part"):
                    number = next((n.text for n in part if n.tag.endswith("PartNumber")), "0")
                    tag = next((n.text for n in part if n.tag.endswith("ETag")), "")
                    listed.append((int(number or 0), (tag or "").strip('"')))
            numbers = [n for n, _ in listed]
            if not listed or numbers != sorted(set(numbers)):
                raise Refused(400, "InvalidPartOrder",
                              "The list of parts was not in ascending order. Parts must be ordered by part number.")  # fmt: skip
            for number, tag in listed:
                held = upload.parts.get(number)
                if held is None or hashlib.md5(held, usedforsecurity=False).hexdigest() != tag:
                    raise Refused(400, "InvalidPart",
                                  "One or more of the specified parts could not be found. The part may not have "
                                  "been uploaded, or the specified entity tag may not match the part's entity tag.")  # fmt: skip
            if any(len(upload.parts[n]) < MIN_PART for n in numbers[:-1]):
                raise Refused(400, "EntityTooSmall",
                              "Your proposed upload is smaller than the minimum allowed object size.")  # fmt: skip
            stand_in.uploads.pop(params["uploadId"], None)
            data = b"".join(upload.parts[n] for n in numbers)
            etag = stand_in.put(bucket_name, key, data, upload.kms_key)
            self._send(200, _xml(
                "CompleteMultipartUploadResult",
                f"<Bucket>{bucket_name}</Bucket><Key>{escape(key)}</Key><ETag>\"{etag}\"</ETag>",
            ), self._sse_headers(upload.kms_key))  # fmt: skip
            return
        if method == "DELETE" and "uploadId" in params:
            allow("s3:AbortMultipartUpload", object_arn)
            stand_in.uploads.pop(params["uploadId"], None)
            self._send(204)
            return
        if method == "PUT":
            allow("s3:PutObject", object_arn)
            kms_key = kms_key_for_write()
            if "x-amz-copy-source" in headers:
                data = self._copy_source(headers["x-amz-copy-source"], principal, context)
                if kms_key:
                    stand_in.kms(principal, "kms:GenerateDataKey", kms_key)
                etag = stand_in.put(bucket_name, key, data, kms_key)
                self._send(200, _xml("CopyObjectResult", f'<ETag>"{etag}"</ETag>'), self._sse_headers(kms_key))
                return
            if kms_key:
                stand_in.kms(principal, "kms:GenerateDataKey", kms_key)
            etag = stand_in.put(bucket_name, key, body, kms_key)
            self._send(200, headers={"ETag": f'"{etag}"', **self._sse_headers(kms_key)})
            return
        if method in {"GET", "HEAD"}:
            allow("s3:GetObject", object_arn)
            meta = stand_in.meta(bucket_name, key)
            if meta is None:
                # Without s3:ListBucket S3 answers 403 for a missing key, never 404.
                try:
                    stand_in.authorise(principal, "s3:ListBucket", bucket_arn, bucket, context)
                except Refused:
                    raise Refused(403, "AccessDenied", "Access Denied") from None
                raise Refused(404, "NoSuchKey", "The specified key does not exist.")
            if meta["kms_key"]:
                stand_in.kms(principal, "kms:Decrypt", meta["kms_key"])
            data = stand_in.read(bucket_name, key)
            status, extra = 200, {}
            if "range" in headers and method == "GET":
                start_text, _, end_text = headers["range"].removeprefix("bytes=").partition("-")
                start = int(start_text)
                end = int(end_text) if end_text else len(data) - 1
                extra["Content-Range"] = f"bytes {start}-{end}/{len(data)}"
                data, status = data[start : end + 1], 206
            reply = {"ETag": f'"{meta["etag"]}"', "Content-Type": "application/octet-stream",
                     "Last-Modified": _http_date(meta["modified"]), "Accept-Ranges": "bytes",
                     **extra, **self._sse_headers(meta["kms_key"])}  # fmt: skip
            if method == "HEAD":
                reply["Content-Length"] = str(meta["size"])
                self._send(status, b"", reply)
            else:
                self._send(status, data, reply)
            return
        if method == "DELETE":
            allow("s3:DeleteObject", object_arn)
            stand_in.delete(bucket_name, key)
            self._send(204)
            return
        raise Refused(405, "MethodNotAllowed", "The specified method is not allowed against this resource.")

    def _sse_headers(self, kms_key: str | None) -> dict[str, str]:
        if not kms_key:
            return {"x-amz-server-side-encryption": "AES256"}
        return {"x-amz-server-side-encryption": "aws:kms",
                "x-amz-server-side-encryption-aws-kms-key-id": kms_key}  # fmt: skip

    def _copy_source(self, source: str, principal: Principal, context: dict[str, str]) -> bytes:
        stand_in = self.server.stand_in
        bucket_name, _, key = urllib.parse.unquote(source).lstrip("/").partition("/")
        bucket = stand_in.buckets.get(bucket_name)
        if bucket is None:
            raise Refused(404, "NoSuchBucket", "The specified bucket does not exist")
        stand_in.authorise(principal, "s3:GetObject", f"arn:aws:s3:::{bucket_name}/{key}", bucket, context)
        meta = stand_in.meta(bucket_name, key)
        if meta is None:
            raise Refused(404, "NoSuchKey", "The specified key does not exist.")
        if meta["kms_key"]:
            stand_in.kms(principal, "kms:Decrypt", meta["kms_key"])
        return stand_in.read(bucket_name, key)

    def _list(self, bucket: str, params: dict[str, str]) -> None:
        prefix = params.get("prefix", "")
        delimiter = params.get("delimiter", "")
        max_keys = int(params.get("max-keys", "1000"))
        after = params.get("continuation-token") or params.get("start-after") or params.get("marker") or ""
        if params.get("continuation-token"):
            after = base64.b64decode(after).decode()
        items = [m for m in self.server.stand_in.listing(bucket) if m["key"].startswith(prefix) and m["key"] > after]
        contents, common = [], []
        last = ""
        for meta in items:
            if delimiter:
                rest = meta["key"][len(prefix):]
                if delimiter in rest:
                    folder = prefix + rest.split(delimiter, 1)[0] + delimiter
                    if folder not in common:
                        if len(contents) + len(common) >= max_keys:
                            break
                        common.append(folder)
                    last = meta["key"]
                    continue
            if len(contents) + len(common) >= max_keys:
                break
            contents.append(meta)
            last = meta["key"]
        truncated = len(contents) + len(common) >= max_keys and any(m["key"] > last for m in items)
        xml = [f"<Name>{bucket}</Name><Prefix>{escape(prefix)}</Prefix><KeyCount>{len(contents) + len(common)}</KeyCount>",
               f"<MaxKeys>{max_keys}</MaxKeys><IsTruncated>{'true' if truncated else 'false'}</IsTruncated>"]  # fmt: skip
        if truncated:
            xml.append(f"<NextContinuationToken>{base64.b64encode(last.encode()).decode()}</NextContinuationToken>")
            xml.append(f"<NextMarker>{escape(last)}</NextMarker>")
        for meta in contents:
            xml.append(f"<Contents><Key>{escape(meta['key'])}</Key><LastModified>{meta['modified']}</LastModified>"
                       f"<ETag>\"{meta['etag']}\"</ETag><Size>{meta['size']}</Size><StorageClass>STANDARD</StorageClass></Contents>")  # fmt: skip
        for folder in common:
            xml.append(f"<CommonPrefixes><Prefix>{escape(folder)}</Prefix></CommonPrefixes>")
        root = "ListBucketResult"
        self._send(200, _xml(root, "".join(xml)), {"Content-Type": "application/xml"})

    def _delete_many(self, bucket: str, body: bytes, allow: Callable[[str, str], None]) -> None:
        keys = [n.text or "" for n in ElementTree.fromstring(body).iter() if n.tag.endswith("Key")]
        done = []
        for key in keys:
            allow("s3:DeleteObject", f"arn:aws:s3:::{bucket}/{key}")
            self.server.stand_in.delete(bucket, key)
            done.append(f"<Deleted><Key>{escape(key)}</Key></Deleted>")
        self._send(200, _xml("DeleteResult", "".join(done)), {"Content-Type": "application/xml"})

    def _sts(self, form: dict[str, str]) -> None:
        session = self.server.stand_in.assume_role_with_web_identity(form)
        assert session.expires is not None
        expires = session.expires.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = (
            '<AssumeRoleWithWebIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
            "<AssumeRoleWithWebIdentityResult><Credentials>"
            f"<AccessKeyId>{session.access_key}</AccessKeyId>"
            f"<SecretAccessKey>{session.secret}</SecretAccessKey>"
            f"<SessionToken>{session.token}</SessionToken><Expiration>{expires}</Expiration>"
            "</Credentials>"
            f"<AssumedRoleUser><Arn>{session.arn}</Arn><AssumedRoleId>AROA:standin</AssumedRoleId></AssumedRoleUser>"
            "</AssumeRoleWithWebIdentityResult></AssumeRoleWithWebIdentityResponse>"
        )
        self._send(200, body.encode(), {"Content-Type": "text/xml"})


def _http_date(iso: str) -> str:
    when = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=dt.UTC)
    return when.strftime("%a, %d %b %Y %H:%M:%S GMT")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    #: S3 takes many connections at once: ClickHouse's BACKUP opens one per part in parallel, and
    #: the standard library's backlog of 5 timed its connections out (osprey-p9, 11 November 2026).
    request_queue_size = 256

    def __init__(self, address: tuple[str, int], stand_in: StandIn) -> None:
        super().__init__(address, Handler)
        self.stand_in = stand_in


def serve(
    stand_in: StandIn, host: str = "127.0.0.1", port: int = 0, *, tls: tuple[str, str] | None = None
) -> Server:
    """The stand-in listening (port 0: any free one), on a thread of its own."""
    server = Server((host, port), stand_in)
    if tls is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(*tls)
        # The handshake on the request's own thread, never the accepting one, so one slow client
        # cannot hold every other connection waiting.
        server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        stand_in.secure = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("/tmp/s3-standin"))
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - a pod's own address
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args()
    stand_in = StandIn.from_config(json.loads(args.config.read_text()), args.root)
    tls = (args.tls_cert, args.tls_key) if args.tls_cert and args.tls_key else None
    server = serve(stand_in, args.host, args.port, tls=tls)
    print(f"s3 stand-in on {args.host}:{server.server_address[1]}", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
