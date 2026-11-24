/**
 * A real loopback identity provider that can say no, for the page service's sign-in tests: the
 * TypeScript twin of `tests/harness/fake_idp.py` in the Build folder's tests, with the same rules.
 *
 * `CLAUDE.md` rule 15: a fake that only grants proves the code agrees with our hopes, so this one
 * refuses what a real Keycloak refuses. It is an actual HTTP server, which the code under test reaches
 * through `fetch` exactly as it reaches a realm. It
 *
 * - serves its discovery document and its signing keys at Keycloak's paths;
 * - refuses an unknown client, an inexact `redirect_uri` (at the authorisation address and again at the
 *   token address), a challenge that is not S256, a missing or wrong PKCE verifier;
 * - authenticates the client at the token address (a wrong or missing secret: `401 invalid_client`,
 *   as `tests/conftest.py` models and records) and, as Keycloak does, before it looks at the code;
 * - issues codes that are single use even when the first try was wrong, and that expire;
 * - signs ID tokens whose claims a test bends one at a time, and hands out a real signed JWT access
 *   token whose audience is the Conduit's, with a refresh token, each carrying a marker made at run time.
 *
 * Slice PL9b adds what a renewing and signing-out service meets, each as the real Keycloak answers it:
 *
 * - the refresh grant: the client is authenticated first (`401 invalid_client`); a missing `refresh_token` is `400
 *   invalid_request`; a token that is not a refresh token of the fake's own making, one that has ended, one whose
 *   provider session has ended (a sign-out, an administrator) and one issued to another client are each `400 invalid_grant`
 *   in Keycloak's own words. With rotation on (the default here: the strictest a realm can be set to) every refresh
 *   returns a new refresh token, the old one is used up, and **a refresh token presented a second time revokes the whole
 *   session** (Keycloak's "revoke refresh token" with no reuse allowed): two exchanges with one token end the person's
 *   session at the provider, so a renewal that is not single-flight cannot pass against this fake;
 * - the end-session address (`GET .../logout`): it ends the provider session only when it is given a valid `id_token_hint`
 *   (without one Keycloak shows a confirmation page and ends nothing), and it refuses a `post_logout_redirect_uri` that is
 *   not registered exactly. Ending a session queues a back-channel logout token, which a test then delivers to the service;
 * - logout tokens, signed as Keycloak signs them (`typ` `Logout`, the `events` claim, `sid` and `sub`, no `nonce`), each
 *   claim bendable one at a time, and the signing key, so a test plants one failing check at a time.
 *
 * Nothing here is a real secret: keys, the client secret and every marker are made when the test runs.
 */
import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { createHash, randomBytes } from "node:crypto";

import { SignJWT, exportJWK, generateKeyPair, jwtVerify } from "jose";
import type { CryptoKey, JWK } from "jose";

export const REALM = "osprey";
export const CONDUIT_AUDIENCE = "osprey-conduit";
const KID = "fake-keycloak-key-1";

export class AuthorisationRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AuthorisationRefused";
  }
}

interface Keys {
  signing: CryptoKey;
  other: CryptoKey;
  jwk: JWK;
  publicKey(): CryptoKey;
}

let keys: Promise<Keys> | undefined;

/** Two keys, made once per test file: 2048-bit generation dominates the run time. */
function theKeys(): Promise<Keys> {
  keys ??= (async () => {
    const signing = await generateKeyPair("RS256", { modulusLength: 2048 });
    const other = await generateKeyPair("RS256", { modulusLength: 2048 });
    const jwk = { ...(await exportJWK(signing.publicKey)), kid: KID, use: "sig", alg: "RS256" };
    return { signing: signing.privateKey, other: other.privateKey, jwk, publicKey: () => signing.publicKey };
  })();
  return keys;
}

function s256(verifier: string): string {
  // Written out here rather than imported from the code under test, so a wrong challenge function
  // there cannot be masked by the same wrong function here.
  return createHash("sha256").update(verifier, "ascii").digest("base64url");
}

function marker(kind: string): string {
  return `${kind}-${randomBytes(12).toString("hex")}`;
}

interface Code {
  sid: string;
  clientId: string;
  redirectUri: string;
  challenge: string;
  nonce: string;
  username: string;
  issuedAt: number;
  used: boolean;
}

export interface Issued {
  accessToken: string;
  refreshToken: string;
  idToken: string;
  accessMarker: string;
  refreshMarker: string;
  /** The provider session this set belongs to. */
  sid: string;
}

/** One person's session at the provider: what a sign-out or a back-channel logout ends. */
export interface ProviderSession {
  sid: string;
  sub: string;
  username: string;
  ended: boolean;
}

/** One refresh grant as the fake answered it: the refresh token it was given, and what it answered. */
export interface RefreshAttempt {
  refreshToken: string;
  status: number;
  error?: string;
}

/** The claims of a logout token a test may bend; a `null` removes the claim. */
export interface LogoutTokenPlant {
  claims?: Record<string, unknown>;
  /** The key it is signed with: the realm's own, another RSA key (same `kid`), an HMAC, or none at all (`alg: none`). */
  signedWith?: "realm" | "other" | "hmac" | "none";
}

export interface FakeKeycloakOptions {
  clientId: string;
  /** The secret the fake holds for the client. The service under test is configured with this, or with another, to be refused. */
  clientSecret: string;
  redirectUri: string;
  /** Whole seconds a code lives, by the fake's own clock. */
  codeTtlSeconds?: number;
  users?: string[];
  /** Whole seconds an access token lives (Keycloak's default is 300). */
  accessTokenSeconds?: number;
  /** Rotate the refresh token at every refresh and revoke the session on reuse of one (default true). */
  rotateRefreshTokens?: boolean;
  /** The addresses a sign-out may return to; Keycloak refuses any other, exactly. */
  postLogoutRedirectUris?: string[];
  /** Seconds a refresh token really lives at the provider, when that is not what it says (see `FakeKeycloak.refreshEnforcedSeconds`). */
  refreshEnforcedSeconds?: number;
}

export interface FakeKeycloak {
  issuer: string;
  clientId: string;
  redirectUri: string;
  /** Bend one claim of the ID token at a time: `aud`, `iss`, `nonce`, `exp`, `sub`, `name`. */
  claimOverrides: Record<string, unknown>;
  signWithOtherKey: boolean;
  omitIdToken: boolean;
  /** Answer the token address with this status, whatever was asked. */
  tokenStatus: number | undefined;
  /** Answer the key-set address (`certs`) with this status, whatever was asked: the realm failing after the code was spent. */
  certsStatus: number | undefined;
  /** Answer the key-set address with a 200 whose body is this text, which need not be a key set. */
  certsBody: string | undefined;
  /** Times the key-set address was asked. */
  certsCalls: number;
  /** Seconds the answer's `refresh_expires_in` says; `undefined` leaves the field out. */
  refreshExpiresIn: number | undefined;
  /**
   * Seconds a refresh token really lives at the provider, when that is not what it said (a realm whose session idle time
   * was shortened since the token was issued): the service believes `refreshExpiresIn`, the provider enforces this.
   */
  refreshEnforcedSeconds: number | undefined;
  /** A 200 refresh answer that carries no new refresh token (a realm with rotation off may answer so). */
  refreshOmitRefreshToken: boolean;
  tokenCalls: number;
  /** Every token set the fake has issued, oldest first. */
  issued: Issued[];
  /** The secret the fake holds for the client; a test changes it to model a realm whose secret was rotated. */
  clientSecret: string;
  /** Answer every refresh grant (and only those) with this status and `{"error": "server_error"}`. */
  refreshStatus: number | undefined;
  /** Answer a refresh grant with a 200 whose body is this text, which need not be a token response. */
  refreshBody: string | undefined;
  /** A 200 refresh answer that leaves the access token out. */
  refreshOmitAccessToken: boolean;
  /** Words the provider puts in `error_description` of a refusal, so a test can look for them in what the service says. */
  refusalDescription: string | undefined;
  /** Refresh grants asked, whatever the answer. */
  refreshCalls: number;
  /** Every refresh grant, in order, with the answer. */
  refreshes: RefreshAttempt[];
  /** The provider's sessions, by `sid`. */
  sessions: Map<string, ProviderSession>;
  /** Ends a provider session as an administrator or another application's sign-out would; queues its logout token. */
  endSession(sid: string): void;
  /** Every end-session request the address answered, in order. */
  endSessionRequests: { query: Record<string, string>; status: number }[];
  /** The logout tokens queued by ended sessions, for a test to deliver to the service as Keycloak's back channel does. */
  takeBackchannel(): string[];
  /** A logout token as Keycloak signs it for a session, with at most one thing bent. */
  logoutToken(sid: string, plant?: LogoutTokenPlant): Promise<string>;
  /** An ID token as the provider signs it, for a person's session (its claims as given at sign-in). */
  idTokenFor(sid: string, claims?: Record<string, unknown>): Promise<string>;
  /** What the browser does once the person has signed in: checks the address and returns the callback address. */
  authorise(authorisationUrl: string, options?: { username?: string; sessionId?: string }): string;
  /** Moves the fake's own clock, which decides when a code, an access token and a refresh token expire. */
  advance(seconds: number): void;
  /** The fake's own clock, in seconds. */
  nowSeconds(): number;
  stop(): Promise<void>;
}

function readBody(request: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    request.on("data", (chunk: Buffer) => chunks.push(chunk));
    request.on("end", () => {
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
    request.on("error", reject);
  });
}

function send(response: ServerResponse, status: number, body: unknown): void {
  const raw = JSON.stringify(body);
  response.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(raw) });
  response.end(raw);
}

/** The client's credentials as the token address reads them: a Basic header, or the form's own fields. */
function credentials(request: IncomingMessage, form: URLSearchParams): { id: string | null; secret: string | null } {
  const header = request.headers.authorization;
  if (typeof header === "string" && header.toLowerCase().startsWith("basic ")) {
    const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
    const at = decoded.indexOf(":");
    if (at > 0) {
      return {
        id: decodeURIComponent(decoded.slice(0, at).replace(/\+/g, " ")),
        secret: decodeURIComponent(decoded.slice(at + 1).replace(/\+/g, " ")),
      };
    }
  }
  return { id: form.get("client_id"), secret: form.get("client_secret") };
}

export const BACKCHANNEL_EVENT = "http://schemas.openid.net/event/backchannel-logout";

export async function startFakeKeycloak(options: FakeKeycloakOptions): Promise<FakeKeycloak> {
  const { signing, other, jwk } = await theKeys();
  const codes = new Map<string, Code>();
  const users = new Set(options.users ?? ["alex"]);
  const codeTtlMs = (options.codeTtlSeconds ?? 60) * 1000;
  const accessSeconds = options.accessTokenSeconds ?? 300;
  const rotate = options.rotateRefreshTokens ?? true;
  const postLogoutUris = options.postLogoutRedirectUris ?? [`${new URL(options.redirectUri).origin}/`];
  /** Refresh tokens by `jti`: whose they are, when they end, and whether one has been spent. */
  const families = new Map<string, { sid: string; expiresAt: number; used: boolean; clientId: string }>();
  const backchannel: string[] = [];
  let offsetMs = 0;
  const fakeNow = (): number => Date.now() + offsetMs;
  const nowSeconds = (): number => Math.floor(fakeNow() / 1000);

  const signGood = (claims: Record<string, unknown>, typ = "JWT"): Promise<string> =>
    new SignJWT(claims).setProtectedHeader({ alg: "RS256", kid: KID, typ }).sign(signing);

  const fake: FakeKeycloak = {
    issuer: "",
    clientId: options.clientId,
    redirectUri: options.redirectUri,
    claimOverrides: {},
    signWithOtherKey: false,
    omitIdToken: false,
    tokenStatus: undefined,
    certsStatus: undefined,
    certsBody: undefined,
    certsCalls: 0,
    refreshExpiresIn: 1800,
    refreshEnforcedSeconds: options.refreshEnforcedSeconds,
    refreshOmitRefreshToken: false,
    tokenCalls: 0,
    issued: [],
    clientSecret: options.clientSecret,
    refreshStatus: undefined,
    refreshBody: undefined,
    refreshOmitAccessToken: false,
    refusalDescription: undefined,
    refreshCalls: 0,
    refreshes: [],
    sessions: new Map(),
    endSessionRequests: [],
    endSession(sid) {
      const session = fake.sessions.get(sid);
      if (!session || session.ended) return;
      session.ended = true;
      for (const family of families.values()) if (family.sid === sid) family.used = true;
      void fake.logoutToken(sid).then((token) => backchannel.push(token));
    },
    takeBackchannel() {
      return backchannel.splice(0, backchannel.length);
    },
    async logoutToken(sid, plant = {}) {
      const session = fake.sessions.get(sid);
      if (!session) throw new Error("no such provider session");
      const claims: Record<string, unknown> = {
        iss: fake.issuer,
        aud: options.clientId,
        iat: nowSeconds(),
        jti: randomBytes(12).toString("hex"),
        sub: session.sub,
        sid: session.sid,
        typ: "Logout",
        events: { [BACKCHANNEL_EVENT]: {} },
        ...plant.claims,
      };
      for (const [key, value] of Object.entries(claims)) if (value === null) delete claims[key];
      const signedWith = plant.signedWith ?? "realm";
      if (signedWith === "none") {
        const part = (value: unknown): string => Buffer.from(JSON.stringify(value)).toString("base64url");
        return `${part({ alg: "none", typ: "Logout" })}.${part(claims)}.`;
      }
      if (signedWith === "hmac") {
        // The classic confusion: the token signed with a shared secret instead of the realm's private key.
        return new SignJWT(claims)
          .setProtectedHeader({ alg: "HS256", kid: KID, typ: "Logout" })
          .sign(new TextEncoder().encode(randomBytes(32).toString("hex")));
      }
      return new SignJWT(claims)
        .setProtectedHeader({ alg: "RS256", kid: KID, typ: "Logout" })
        .sign(signedWith === "other" ? other : signing);
    },
    async idTokenFor(sid, claims = {}) {
      const session = fake.sessions.get(sid);
      if (!session) throw new Error("no such provider session");
      const now = nowSeconds();
      return signGood({
        iss: fake.issuer,
        aud: options.clientId,
        azp: options.clientId,
        sub: session.sub,
        sid,
        preferred_username: session.username,
        name: `Name of ${session.username}`,
        iat: now,
        exp: now + 300,
        ...claims,
      });
    },
    authorise(authorisationUrl, authoriseOptions = {}) {
      const url = new URL(authorisationUrl);
      if (!url.pathname.endsWith("/protocol/openid-connect/auth")) throw new AuthorisationRefused(`not the authorisation address: ${url.pathname}`);
      const query = url.searchParams;
      if (query.get("client_id") !== options.clientId) throw new AuthorisationRefused("unknown client");
      if (query.get("redirect_uri") !== options.redirectUri) throw new AuthorisationRefused("invalid redirect_uri");
      if (query.get("response_type") !== "code") throw new AuthorisationRefused("response_type");
      if (query.get("code_challenge_method") !== "S256" || !query.get("code_challenge")) throw new AuthorisationRefused("PKCE S256 required");
      if (!(query.get("scope") ?? "").split(" ").includes("openid")) throw new AuthorisationRefused("scope openid required");
      const stateParam = query.get("state");
      if (!stateParam) throw new AuthorisationRefused("state required");
      const username = authoriseOptions.username ?? "alex";
      if (!users.has(username)) throw new AuthorisationRefused("invalid credentials");
      const code = randomBytes(18).toString("base64url");
      // A person already signed in at the provider is given their session again (single sign-on): the same `sid`.
      const reused = authoriseOptions.sessionId === undefined ? undefined : fake.sessions.get(authoriseOptions.sessionId);
      const sid = reused && !reused.ended ? reused.sid : randomBytes(12).toString("hex");
      if (!fake.sessions.has(sid)) fake.sessions.set(sid, { sid, sub: `sub-${username}`, username, ended: false });
      codes.set(code, {
        sid,
        clientId: options.clientId,
        redirectUri: options.redirectUri,
        challenge: query.get("code_challenge") as string,
        nonce: query.get("nonce") ?? "",
        username,
        issuedAt: fakeNow(),
        used: false,
      });
      // Keycloak 26 names itself on the way back (RFC 9207), so the service has an `iss` to check.
      return `${options.redirectUri}?${new URLSearchParams({ code, state: stateParam, iss: fake.issuer }).toString()}`;
    },
    advance(seconds) {
      offsetMs += seconds * 1000;
    },
    nowSeconds,
    stop: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => {
          resolve();
        });
      }),
  };

  /** A refusal in Keycloak's own shape: the error, and the words it gives (a test may put a marker in them). */
  function refuse(response: ServerResponse, status: number, error: string, description: string): void {
    send(response, status, { error, error_description: fake.refusalDescription ?? description });
  }

  /** What a refresh token of ours is, or why not. A wrong signature, a wrong type, an unknown `jti` are all "Invalid refresh token". */
  async function readRefreshToken(raw: string): Promise<Record<string, unknown> | undefined> {
    try {
      const { payload } = await jwtVerify(raw, (await theKeys()).publicKey(), { algorithms: ["RS256"], clockTolerance: 1e9 });
      return payload as Record<string, unknown>;
    } catch {
      return undefined;
    }
  }

  /** The tokens for a session, signed as the realm signs them. */
  async function mint(sid: string, session: ProviderSession, clientId: string, nonce: string | undefined): Promise<Record<string, unknown>> {
    const now = nowSeconds();
    const accessMarker = marker("ACCESS");
    const refreshMarker = marker("REFRESH");
    const jti = randomBytes(12).toString("hex");
    const accessToken = await signGood({
      iss: fake.issuer,
      aud: CONDUIT_AUDIENCE,
      azp: clientId,
      sub: session.sub,
      sid,
      typ: "Bearer",
      jti: randomBytes(12).toString("hex"),
      marker: accessMarker,
      iat: now,
      exp: now + accessSeconds,
    });
    const refreshLife = fake.refreshExpiresIn ?? 1800;
    const refreshToken = await signGood({
      iss: fake.issuer,
      aud: fake.issuer,
      sub: session.sub,
      sid,
      azp: clientId,
      typ: "Refresh",
      jti,
      marker: refreshMarker,
      iat: now,
      exp: now + refreshLife,
    });
    families.set(jti, { sid, expiresAt: fakeNow() + (fake.refreshEnforcedSeconds ?? refreshLife) * 1000, used: false, clientId });
    const body: Record<string, unknown> = {
      access_token: accessToken,
      expires_in: accessSeconds,
      refresh_token: refreshToken,
      token_type: "Bearer",
      scope: "openid",
    };
    if (fake.refreshExpiresIn !== undefined) body["refresh_expires_in"] = fake.refreshExpiresIn;
    let idToken = "";
    if (nonce !== undefined) {
      // The code grant's ID token, which a test bends claim by claim; a refresh grant's carries no nonce.
      if (!fake.omitIdToken) {
        const idClaims: Record<string, unknown> = {
          iss: fake.issuer,
          aud: clientId,
          azp: clientId,
          sub: session.sub,
          sid,
          preferred_username: session.username,
          name: `Name of ${session.username}`,
          nonce,
          iat: now,
          exp: now + 300,
          ...fake.claimOverrides,
        };
        idToken = await new SignJWT(idClaims)
          .setProtectedHeader({ alg: "RS256", kid: KID, typ: "JWT" })
          .sign(fake.signWithOtherKey ? other : signing);
        body["id_token"] = idToken;
      }
    } else {
      idToken = await fake.idTokenFor(sid);
      body["id_token"] = idToken;
    }
    fake.issued.push({ accessToken, refreshToken, idToken, accessMarker, refreshMarker, sid });
    return body;
  }

  async function refreshGrant(form: URLSearchParams, response: ServerResponse): Promise<void> {
    fake.refreshCalls += 1;
    const raw = form.get("refresh_token") ?? "";
    const record = (status: number, error?: string): void => {
      fake.refreshes.push({ refreshToken: raw, status, ...(error === undefined ? {} : { error }) });
    };
    const refusing = (status: number, error: string, description: string): void => {
      record(status, error);
      refuse(response, status, error, description);
    };
    if (fake.refreshStatus !== undefined) {
      record(fake.refreshStatus, "server_error");
      send(response, fake.refreshStatus, { error: "server_error" });
      return;
    }
    if (raw === "") {
      refusing(400, "invalid_request", "Missing parameter: refresh_token");
      return;
    }
    const claims = await readRefreshToken(raw);
    if (!claims || claims["typ"] !== "Refresh" || typeof claims["jti"] !== "string") {
      refusing(400, "invalid_grant", "Invalid refresh token");
      return;
    }
    const family = families.get(claims["jti"]);
    const session = fake.sessions.get(String(claims["sid"]));
    if (!family || !session) {
      refusing(400, "invalid_grant", "Invalid refresh token");
      return;
    }
    if (family.clientId !== options.clientId) {
      refusing(400, "invalid_grant", "Invalid refresh token. Token client and authorized client don't match");
      return;
    }
    if (family.expiresAt <= fakeNow()) {
      refusing(400, "invalid_grant", "Token is not active");
      return;
    }
    if (session.ended) {
      refusing(400, "invalid_grant", "Session not active");
      return;
    }
    if (rotate && family.used) {
      // Keycloak's "revoke refresh token", reuse not allowed: the token was already spent, so the whole session is revoked.
      session.ended = true;
      for (const other of families.values()) if (other.sid === session.sid) other.used = true;
      refusing(400, "invalid_grant", "Maximum allowed refresh token reuse exceeded");
      return;
    }
    if (rotate) family.used = true;
    if (fake.refreshBody !== undefined) {
      record(200);
      response.writeHead(200, { "content-type": "application/json" });
      response.end(fake.refreshBody);
      return;
    }
    const body = await mint(session.sid, session, options.clientId, undefined);
    if (!rotate) body["refresh_token"] = raw;
    if (fake.refreshOmitAccessToken) delete body["access_token"];
    if (fake.refreshOmitRefreshToken) delete body["refresh_token"];
    record(200);
    send(response, 200, body);
  }

  async function token(request: IncomingMessage, response: ServerResponse): Promise<void> {
    fake.tokenCalls += 1;
    const form = new URLSearchParams(await readBody(request));
    const isRefresh = form.get("grant_type") === "refresh_token";
    if (fake.tokenStatus !== undefined) {
      send(response, fake.tokenStatus, { error: "server_error" });
      return;
    }
    // The client is authenticated before the code is looked at, as Keycloak does: a wrong secret
    // does not burn the code.
    const { id, secret } = credentials(request, form);
    if (id !== options.clientId || secret === null || secret !== fake.clientSecret) {
      if (isRefresh) {
        fake.refreshCalls += 1;
        fake.refreshes.push({ refreshToken: form.get("refresh_token") ?? "", status: 401, error: "invalid_client" });
      }
      send(response, 401, { error: "invalid_client", error_description: "Invalid client or Invalid client credentials" });
      return;
    }
    if (isRefresh) {
      await refreshGrant(form, response);
      return;
    }
    if (form.get("grant_type") !== "authorization_code") {
      send(response, 400, { error: "unsupported_grant_type" });
      return;
    }
    const code = codes.get(form.get("code") ?? "");
    if (!code || code.used) {
      send(response, 400, { error: "invalid_grant", error_description: "Code not valid" });
      return;
    }
    code.used = true; // single use, even when the rest is wrong or the code has expired
    if (fakeNow() - code.issuedAt > codeTtlMs) {
      send(response, 400, { error: "invalid_grant", error_description: "Code not valid" });
      return;
    }
    if (form.get("redirect_uri") !== code.redirectUri) {
      send(response, 400, { error: "invalid_grant", error_description: "Incorrect redirect_uri" });
      return;
    }
    const verifier = form.get("code_verifier") ?? "";
    if (verifier === "" || s256(verifier) !== code.challenge) {
      send(response, 400, { error: "invalid_grant", error_description: "PKCE verification failed" });
      return;
    }
    const session = fake.sessions.get(code.sid) as ProviderSession;
    send(response, 200, await mint(code.sid, session, code.clientId, code.nonce));
  }

  /** `GET .../logout`: RP-initiated logout, as Keycloak 26 answers it. */
  async function endSessionAddress(url: URL, response: ServerResponse): Promise<void> {
    const query = Object.fromEntries(url.searchParams.entries());
    const answer = (status: number, headers: Record<string, string>, body: string): void => {
      fake.endSessionRequests.push({ query, status });
      response.writeHead(status, headers);
      response.end(body);
    };
    const hint = query["id_token_hint"];
    const target = query["post_logout_redirect_uri"];
    if (target !== undefined && !postLogoutUris.includes(target)) {
      answer(400, { "content-type": "text/plain" }, "Invalid redirect uri");
      return;
    }
    if (hint === undefined) {
      // No hint: Keycloak asks the person to confirm, and ends nothing until they do.
      answer(200, { "content-type": "text/html" }, "<html><body>Do you want to log out?</body></html>");
      return;
    }
    let claims: Record<string, unknown>;
    try {
      // An expired hint is accepted (Keycloak skips the expiry check here); a bad signature is not.
      claims = (await jwtVerify(hint, (await theKeys()).publicKey(), { algorithms: ["RS256"], clockTolerance: 1e9 })).payload as Record<string, unknown>;
    } catch {
      answer(400, { "content-type": "text/plain" }, "Invalid parameter: id_token_hint");
      return;
    }
    if (query["client_id"] !== undefined && query["client_id"] !== claims["azp"]) {
      answer(400, { "content-type": "text/plain" }, "Invalid parameter: client_id");
      return;
    }
    fake.endSession(String(claims["sid"]));
    if (target === undefined) {
      answer(200, { "content-type": "text/html" }, "<html><body>You are logged out</body></html>");
      return;
    }
    const back = new URL(target);
    if (query["state"] !== undefined) back.searchParams.set("state", query["state"]);
    answer(302, { Location: back.toString() }, "");
  }

  const server: Server = createServer((request, response) => {
    const path = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
    const base = `/realms/${REALM}`;
    void (async () => {
      if (request.method === "GET" && path === `${base}/.well-known/openid-configuration`) {
        const oidc = `${fake.issuer}/protocol/openid-connect`;
        send(response, 200, {
          issuer: fake.issuer,
          authorization_endpoint: `${oidc}/auth`,
          token_endpoint: `${oidc}/token`,
          jwks_uri: `${oidc}/certs`,
          end_session_endpoint: `${oidc}/logout`,
          response_types_supported: ["code"],
          subject_types_supported: ["public"],
          id_token_signing_alg_values_supported: ["RS256"],
          code_challenge_methods_supported: ["S256"],
          token_endpoint_auth_methods_supported: ["client_secret_basic", "client_secret_post"],
          authorization_response_iss_parameter_supported: true,
          backchannel_logout_supported: true,
          backchannel_logout_session_supported: true,
        });
      } else if (request.method === "GET" && path === `${base}/protocol/openid-connect/certs`) {
        fake.certsCalls += 1;
        if (fake.certsStatus !== undefined) send(response, fake.certsStatus, { error: "server_error" });
        else if (fake.certsBody !== undefined) {
          response.writeHead(200, { "content-type": "application/json" });
          response.end(fake.certsBody);
        } else send(response, 200, { keys: [jwk] });
      } else if (request.method === "POST" && path === `${base}/protocol/openid-connect/token`) {
        await token(request, response);
      } else if (request.method === "GET" && path === `${base}/protocol/openid-connect/logout`) {
        await endSessionAddress(new URL(request.url ?? "/", "http://127.0.0.1"), response);
      } else {
        send(response, 404, { error: "not_found" });
      }
    })().catch(() => {
      if (!response.headersSent) send(response, 500, { error: "server_error" });
      else response.destroy();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  fake.issuer = `http://127.0.0.1:${(server.address() as AddressInfo).port}/realms/${REALM}`;
  return fake;
}
