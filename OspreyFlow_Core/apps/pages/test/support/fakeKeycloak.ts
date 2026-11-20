/**
 * A real loopback identity provider that can say no, for the page service's sign-in tests: the
 * TypeScript twin of `OspreyFlow_Build/tests/harness/fake_idp.py`, with the same rules.
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
 * Nothing here is a real secret: keys, the client secret and every marker are made when the test runs.
 */
import { createServer } from "node:http";
import type { IncomingMessage, Server, ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { createHash, randomBytes } from "node:crypto";

import { SignJWT, exportJWK, generateKeyPair } from "jose";
import type { JWK, KeyLike } from "jose";

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
  signing: KeyLike;
  other: KeyLike;
  jwk: JWK;
}

let keys: Promise<Keys> | undefined;

/** Two keys, made once per test file: 2048-bit generation dominates the run time. */
function theKeys(): Promise<Keys> {
  keys ??= (async () => {
    const signing = await generateKeyPair("RS256", { modulusLength: 2048 });
    const other = await generateKeyPair("RS256", { modulusLength: 2048 });
    const jwk = { ...(await exportJWK(signing.publicKey)), kid: KID, use: "sig", alg: "RS256" };
    return { signing: signing.privateKey, other: other.privateKey, jwk };
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
}

export interface FakeKeycloakOptions {
  clientId: string;
  /** The secret the fake holds for the client. The service under test is configured with this, or with another, to be refused. */
  clientSecret: string;
  redirectUri: string;
  /** Whole seconds a code lives, by the fake's own clock. */
  codeTtlSeconds?: number;
  users?: string[];
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
  /** Seconds the answer's `refresh_expires_in` says; `undefined` leaves the field out. */
  refreshExpiresIn: number | undefined;
  tokenCalls: number;
  /** Every token set the fake has issued, oldest first. */
  issued: Issued[];
  /** What the browser does once the person has signed in: checks the address and returns the callback address. */
  authorise(authorisationUrl: string, options?: { username?: string }): string;
  /** Moves the fake's own clock, which decides when a code expires. */
  advance(seconds: number): void;
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

export async function startFakeKeycloak(options: FakeKeycloakOptions): Promise<FakeKeycloak> {
  const { signing, other, jwk } = await theKeys();
  const codes = new Map<string, Code>();
  const users = new Set(options.users ?? ["alex"]);
  const codeTtlMs = (options.codeTtlSeconds ?? 60) * 1000;
  let offsetMs = 0;
  const fakeNow = (): number => Date.now() + offsetMs;

  const fake: FakeKeycloak = {
    issuer: "",
    clientId: options.clientId,
    redirectUri: options.redirectUri,
    claimOverrides: {},
    signWithOtherKey: false,
    omitIdToken: false,
    tokenStatus: undefined,
    refreshExpiresIn: 1800,
    tokenCalls: 0,
    issued: [],
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
      codes.set(code, {
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
    stop: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => {
          resolve();
        });
      }),
  };

  async function token(request: IncomingMessage, response: ServerResponse): Promise<void> {
    fake.tokenCalls += 1;
    const form = new URLSearchParams(await readBody(request));
    if (fake.tokenStatus !== undefined) {
      send(response, fake.tokenStatus, { error: "server_error" });
      return;
    }
    // The client is authenticated before the code is looked at, as Keycloak does: a wrong secret
    // does not burn the code.
    const { id, secret } = credentials(request, form);
    if (id !== options.clientId || secret === null || secret !== options.clientSecret) {
      send(response, 401, { error: "invalid_client", error_description: "Invalid client or Invalid client credentials" });
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
    const now = Math.floor(Date.now() / 1000);
    const accessMarker = marker("ACCESS");
    const refreshMarker = marker("REFRESH");
    const sign = (claims: Record<string, unknown>): Promise<string> =>
      new SignJWT(claims)
        .setProtectedHeader({ alg: "RS256", kid: KID, typ: "JWT" })
        .sign(fake.signWithOtherKey ? other : signing);
    // Always the real key for the access and refresh tokens: only the ID token is bent.
    const signGood = (claims: Record<string, unknown>): Promise<string> =>
      new SignJWT(claims).setProtectedHeader({ alg: "RS256", kid: KID, typ: "JWT" }).sign(signing);
    const accessToken = await signGood({
      iss: fake.issuer,
      aud: CONDUIT_AUDIENCE,
      azp: code.clientId,
      sub: `sub-${code.username}`,
      typ: "Bearer",
      marker: accessMarker,
      iat: now,
      exp: now + 300,
    });
    const refreshToken = await signGood({
      iss: fake.issuer,
      aud: fake.issuer,
      sub: `sub-${code.username}`,
      typ: "Refresh",
      marker: refreshMarker,
      iat: now,
      exp: now + 1800,
    });
    const idClaims: Record<string, unknown> = {
      iss: fake.issuer,
      aud: code.clientId,
      azp: code.clientId,
      sub: `sub-${code.username}`,
      preferred_username: code.username,
      name: `Name of ${code.username}`,
      nonce: code.nonce,
      iat: now,
      exp: now + 300,
      ...fake.claimOverrides,
    };
    const body: Record<string, unknown> = {
      access_token: accessToken,
      expires_in: 300,
      refresh_token: refreshToken,
      token_type: "Bearer",
      scope: "openid",
    };
    if (fake.refreshExpiresIn !== undefined) body["refresh_expires_in"] = fake.refreshExpiresIn;
    let idToken = "";
    if (!fake.omitIdToken) {
      idToken = await sign(idClaims);
      body["id_token"] = idToken;
    }
    fake.issued.push({ accessToken, refreshToken, idToken, accessMarker, refreshMarker });
    send(response, 200, body);
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
        });
      } else if (request.method === "GET" && path === `${base}/protocol/openid-connect/certs`) {
        send(response, 200, { keys: [jwk] });
      } else if (request.method === "POST" && path === `${base}/protocol/openid-connect/token`) {
        await token(request, response);
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
