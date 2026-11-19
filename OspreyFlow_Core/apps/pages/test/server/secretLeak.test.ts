/**
 * The owner's rule for `OSPREY_PAGES_SESSION_SECRET` (19 November 2026): it is never printed or sent.
 * The service is given a generated sentinel as its secret, every route is driven with and without a session,
 * and the sentinel must be in no response body or header, no cookie (the signed value included), and
 * nothing the service wrote to the console, `process.stdout` or `process.stderr`.
 */
import { afterEach, describe, expect, it } from "vitest";

import { loadConfig } from "../../server/config.js";
import { COOKIE_NAME } from "../../server/sessionPolicy.js";
import { build } from "../support/build.js";
import { captureOutput } from "../support/capture.js";
import type { Captured } from "../support/capture.js";
import { cookieFrom, csrfFromPage, everythingIn, request, setCookies, signIn } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

/** The sentinel as it could appear: whole, URL-encoded, in base64 and base64url, and in its first and last pieces. */
function forms(secret: string): Array<[string, string]> {
  return [
    ["whole", secret],
    ["URL-encoded", encodeURIComponent(secret)],
    ["base64", Buffer.from(secret).toString("base64")],
    ["base64url", Buffer.from(secret).toString("base64url")],
    ["its first 12 characters", secret.slice(0, 12)],
    ["its last 12 characters", secret.slice(-12)],
  ];
}

/** Which form of the secret is in the text, if any: the form's name, never the secret itself. */
function mentions(text: string, secret: string): string | undefined {
  return forms(secret).find(([, f]) => text.includes(f))?.[0];
}

let captured: Captured | undefined;
afterEach(() => {
  captured?.restore();
  captured = undefined;
});

describe("the secret is never printed or sent", () => {
  it("is in no response, cookie or output, on any route, with or without a session", async () => {
    const sentinel = generateSecret();
    const { app } = build({
      sessionSecret: sentinel,
      routes: (router) => {
        // The 500 path writes to the log: the capture below is shown to see it (the control).
        router.get("/_test/boom", () => {
          throw new Error("a failure of the service's own");
        });
      },
    });
    captured = captureOutput();

    const seen: Array<{ where: string; text: string }> = [];
    const note = (where: string, res: { headers: Record<string, unknown>; text: string }): void => {
      seen.push({ where, text: everythingIn(res as never) });
    };

    // Without a session.
    note("GET /", await request(app).get("/"));
    note("GET /healthz", await request(app).get("/healthz"));
    note("GET /no-such-page", await request(app).get("/no-such-page"));
    note("OPTIONS /", await request(app).options("/"));
    note("POST /session/sign-out, no token", await request(app).post("/session/sign-out"));
    note("POST /session/sign-out, wrong token", await request(app).post("/session/sign-out").type("form").send("_csrf=wrong"));
    note("GET /_test/boom", await request(app).get("/_test/boom"));
    const signInResponse = await request(app).get("/session/sign-in");
    note("GET /session/sign-in", signInResponse);

    // With a session.
    const cookie = cookieFrom(signInResponse);
    const home = await request(app).get("/").set("Cookie", cookie);
    note("GET / (session)", home);
    note("HEAD / (session)", await request(app).head("/").set("Cookie", cookie));
    note("GET /healthz (session)", await request(app).get("/healthz").set("Cookie", cookie));
    note("GET /no-such-page (session)", await request(app).get("/no-such-page").set("Cookie", cookie));
    note("GET /_test/boom (session)", await request(app).get("/_test/boom").set("Cookie", cookie));
    note("POST /session/sign-out, no token (session)", await request(app).post("/session/sign-out").set("Cookie", cookie));
    note("PUT /_test/echo, no token (session)", await request(app).put("/_test/echo").set("Cookie", cookie));
    const csrf = csrfFromPage(home.text);
    note("GET /session/sign-in again (session)", await request(app).get("/session/sign-in").set("Cookie", cookie));
    const fresh = await signIn(app);
    note(
      "POST /session/sign-out (session, token)",
      await request(app).post("/session/sign-out").set("Cookie", fresh.cookie).type("form").send(`_csrf=${fresh.csrf}`),
    );
    expect(csrf).not.toBe("");

    captured.restore();
    const output = captured.text();

    // The control: the capture saw the service write to its log, so "nothing" below means something.
    expect(output).toContain("pages: unhandled error:");

    expect(seen.length).toBeGreaterThanOrEqual(15);
    for (const { where, text } of seen) {
      expect(mentions(text, sentinel), `${where}: the secret is in the response`).toBeUndefined();
    }
    expect(mentions(output, sentinel), "the secret is in the service's output").toBeUndefined();
  });

  it("is not in the signed cookie's value, however it is decoded", async () => {
    const sentinel = generateSecret();
    const { app } = build({ sessionSecret: sentinel });
    const res = await request(app).get("/session/sign-in");
    const cookies = setCookies(res);
    expect(cookies.some((c) => c.startsWith(`${COOKIE_NAME}=`))).toBe(true);
    for (const cookie of cookies) {
      const value = cookie.split(";")[0] as string;
      expect(mentions(value, sentinel)).toBeUndefined();
      expect(mentions(decodeURIComponent(value), sentinel)).toBeUndefined();
    }
  });

  it("is not in the service's output when the configuration is logged on its way to the app", () => {
    const sentinel = generateSecret();
    const config = loadConfig({ OSPREY_PAGES_SESSION_SECRET: sentinel });
    captured = captureOutput();
    console.log("pages: starting with", config);
    console.log(JSON.stringify(config));
    captured.restore();
    expect(captured.text()).toContain("pages: starting with");
    expect(mentions(captured.text(), sentinel)).toBeUndefined();
  });
});

describe("the scan itself: a secret that is printed or sent is found, in the shape the service would do it", () => {
  const leaks: Array<[string, (router: import("express").Router, secret: string) => void]> = [
    [
      "logged to the console on an error path",
      (router, secret) => {
        router.get("/_test/leak", () => {
          console.error("pages: unhandled error:", secret);
          throw new Error("x");
        });
      },
    ],
    [
      "written to standard error",
      (router, secret) => {
        router.get("/_test/leak", (_req, res) => {
          process.stderr.write(`${secret}\n`);
          res.send("ok");
        });
      },
    ],
    [
      "sent in a header",
      (router, secret) => {
        router.get("/_test/leak", (_req, res) => {
          res.set("X-Debug", secret).send("ok");
        });
      },
    ],
    [
      "sent in a body, URL-encoded",
      (router, secret) => {
        router.get("/_test/leak", (_req, res) => {
          res.send(`<a href="/?s=${encodeURIComponent(secret)}">x</a>`);
        });
      },
    ],
    [
      "sent in a cookie",
      (router, secret) => {
        router.get("/_test/leak", (_req, res) => {
          res.cookie("osprey_debug", secret).send("ok");
        });
      },
    ],
  ];

  it.each(leaks)("finds a secret %s", async (_name, plant) => {
    const sentinel = generateSecret();
    const { app } = build({ sessionSecret: sentinel, routes: (router) => plant(router, sentinel) });
    captured = captureOutput();
    const res = await request(app).get("/_test/leak");
    captured.restore();
    const everywhere = `${everythingIn(res)}\n${captured.text()}`;
    expect(mentions(everywhere, sentinel)).toBeDefined();
  });

  it("finds nothing on a route that leaks nothing (the control)", async () => {
    const sentinel = generateSecret();
    const { app } = build({
      sessionSecret: sentinel,
      routes: (router) => {
        router.get("/_test/leak", (_req, res) => {
          console.error("pages: a line of the log");
          res.send("ok");
        });
      },
    });
    captured = captureOutput();
    const res = await request(app).get("/_test/leak");
    captured.restore();
    expect(captured.text()).toContain("a line of the log");
    expect(mentions(`${everythingIn(res)}\n${captured.text()}`, sentinel)).toBeUndefined();
  });
});
