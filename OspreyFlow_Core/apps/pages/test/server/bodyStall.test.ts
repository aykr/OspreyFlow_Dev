/**
 * A browser that stops sending part-way through a body does not hold the page service's connection open for ever
 * (slice PL10, round 3). `start.ts` switches Node's whole-request timeout off so that a long upload is not cut for its
 * length; what replaces it is a STALL timer: no byte of the browser's body for `bodyStallMs`. A body that keeps
 * arriving, however slowly and however long in all, is never cut.
 *
 * Each case drives the real server, started as `main.ts` starts it, over a raw socket that sends part of a body and
 * then goes silent (a `fetch` cannot be made to stop mid-body). The Conduit is a fake that counts connections.
 *
 * WHICH TEST FAILS IF A STALLED BODY IS HELD OPEN (rule 12). With the stall timer removed, each of the "stalled"
 * cases below waits out its deadline with the socket still open and fails: a small `/v1` body, the parts of a form
 * before its file, a raw upload part-way, and a POST to a page route (which never reaches the forwarder). The "steady
 * slow body" case fails if the timer is armed on the wrong clock (the whole request, not the silence between bytes).
 */
import { createServer } from "node:http";
import type { Server } from "node:http";
import { connect } from "node:net";
import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { IdentityProvider } from "../../server/identity.js";
import { MemorySessionStore } from "../../server/sessionStore.js";
import { main } from "../../server/start.js";
import type { Running } from "../../server/start.js";
import { testClock } from "../support/clock.js";
import { cookieFrom, csrfFromPage, request as pageRequest, TEST_SESSION_SECRET } from "../support/http.js";
import { generateSecret } from "../support/secret.js";

vi.setConfig({ testTimeout: 20_000 });

const STALL_MS = 300;
const UPLOAD = "/v1/investigations/inv-1/documents?name=a.txt";
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

let conduit: { server: Server; connections: number; bodies: number[] } | undefined;
let running: Running | undefined;

afterEach(async () => {
  await running?.stop();
  running = undefined;
  await new Promise<void>((resolve) => {
    if (!conduit) resolve();
    else {
      conduit.server.closeAllConnections();
      conduit.server.close(() => resolve());
    }
  });
  conduit = undefined;
});

async function boot(): Promise<{ port: number; cookie: string; csrf: string }> {
  const fake = { server: createServer(), connections: 0, bodies: [] as number[] };
  fake.server.on("connection", () => {
    fake.connections += 1;
  });
  fake.server.on("request", (req, res) => {
    let length = 0;
    req.on("data", (chunk: Buffer) => {
      length += chunk.length;
    });
    req.on("end", () => {
      fake.bodies.push(length);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end("{}");
    });
  });
  await new Promise<void>((resolve) => fake.server.listen(0, "127.0.0.1", resolve));
  conduit = fake;
  const clock = testClock();
  const provider: IdentityProvider = {
    async signIn() {
      return {
        subject: "sub-a",
        displayName: "Person a",
        accessToken: `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`,
        refreshToken: `eyJ${generateSecret(24)}.${generateSecret(40)}.${generateSecret(43)}`,
        idpSessionExpiresAt: clock() + 36000 * 1000,
      };
    },
  };
  running = await main(
    {
      OSPREY_PAGES_PORT: "0",
      OSPREY_PAGES_SESSION_SECRET: TEST_SESSION_SECRET,
      OSPREY_PAGES_CONDUIT_URL: `http://127.0.0.1:${(fake.server.address() as AddressInfo).port}`,
      OSPREY_PAGES_PUBLIC_ORIGIN: "https://osprey.test",
    },
    { log: () => undefined, error: () => undefined, exit: () => undefined },
    { store: new MemorySessionStore({ clock }), identityProvider: provider, host: "127.0.0.1", clock, bodyStallMs: STALL_MS },
  );
  if (!running) throw new Error("the service did not start");
  const base = `http://127.0.0.1:${running.port}`;
  const res = await pageRequest(base).get("/session/sign-in");
  const cookie = cookieFrom(res);
  const page = await pageRequest(base).get("/").set("Cookie", cookie);
  return { port: running.port, cookie, csrf: csrfFromPage(page.text) };
}

interface Raw {
  write(data: string | Buffer): Promise<void>;
  /** Resolves with what the server said, once it has closed the connection; rejects at the deadline with it still open. */
  closed(ms: number): Promise<string>;
  said(): string;
  destroy(): void;
}

/** A raw socket, so that a request can stop part-way. The head is written at once; nothing is tidied. */
function raw(port: number, head: string): Raw {
  const socket = connect(port, "127.0.0.1");
  let said = "";
  let ended = false;
  const done = new Promise<void>((resolve) => {
    socket.on("close", () => {
      ended = true;
      resolve();
    });
  });
  socket.on("data", (chunk: Buffer) => {
    said += chunk.toString("latin1");
  });
  socket.on("error", () => undefined);
  socket.write(head);
  return {
    write: (data) => new Promise<void>((resolve) => socket.write(data, () => resolve())),
    closed: async (ms) => {
      const timer = new Promise<never>((_, reject) => {
        setTimeout(() => reject(new Error(`the connection was still open after ${ms} ms`)), ms).unref();
      });
      await Promise.race([done, timer]);
      return said;
    },
    said: () => said,
    destroy: () => {
      if (!ended) socket.destroy();
    },
  };
}

function head(person: { cookie: string; csrf: string }, request: string, contentType: string, length: number, csrf = true): string {
  return [
    `${request} HTTP/1.1`,
    "Host: pages.test",
    "X-Forwarded-Proto: https",
    `Cookie: ${person.cookie}`,
    ...(csrf ? [`X-CSRF-Token: ${person.csrf}`] : []),
    `Content-Type: ${contentType}`,
    `Content-Length: ${length}`,
    "",
    "",
  ].join("\r\n");
}

describe("a body that stops arriving is not held open (Node's whole-request timeout is off)", () => {
  it("a small /v1 body that stalls part-way is ended, and the Conduit is not contacted", async () => {
    const person = await boot();
    const client = raw(person.port, head(person, "POST /v1/investigations", "application/json", 200));
    await client.write('{"name":"a');
    const said = await client.closed(3000).finally(() => client.destroy());
    expect(said).toMatch(/^HTTP\/1\.1 408 /);
    expect(said).toContain('"detail"');
    expect(conduit?.connections).toBe(0);
  });

  it("a form that stalls before its file is ended, and the Conduit is not contacted", async () => {
    const person = await boot();
    const boundary = "stall-boundary";
    const client = raw(person.port, head(person, `POST ${UPLOAD.split("?")[0]}`, `multipart/form-data; boundary=${boundary}`, 5000, false));
    // The first part (the token) is whole; the next part has begun and stops.
    await client.write(`--${boundary}\r\nContent-Disposition: form-data; name="_csrf"\r\n\r\n${person.csrf}\r\n--${boundary}\r\nContent-Disp`);
    const said = await client.closed(3000).finally(() => client.destroy());
    expect(said).toMatch(/^HTTP\/1\.1 408 /);
    expect(conduit?.connections).toBe(0);
  });

  it("a raw upload that stalls part-way is ended and what the Conduit had is abandoned, not completed", async () => {
    const person = await boot();
    const client = raw(person.port, head(person, `POST ${UPLOAD}`, "application/octet-stream", 100_000));
    await client.write(Buffer.alloc(1000, 7));
    const said = await client.closed(3000).finally(() => client.destroy());
    expect(said).toMatch(/^HTTP\/1\.1 408 /);
    expect(conduit?.bodies).toEqual([]); // the Conduit never saw a whole body
  });

  it("a POST to a page route that stalls part-way is ended", async () => {
    const person = await boot();
    const client = raw(person.port, head(person, "POST /session/sign-out", "application/x-www-form-urlencoded", 200, false));
    await client.write("_csrf=abc");
    await client.closed(3000).finally(() => client.destroy());
    expect(conduit?.connections).toBe(0);
  });

  it("a steady slow body is never cut: the timer is the silence between bytes, not the length of the request", async () => {
    const person = await boot();
    const pieces = 6;
    const client = raw(person.port, head(person, `POST ${UPLOAD}`, "application/octet-stream", pieces * 100));
    for (let i = 0; i < pieces; i += 1) {
      await client.write(Buffer.alloc(100, i));
      await sleep(STALL_MS / 2); // the whole is well over the stall time; no gap is
    }
    await until(() => client.said().startsWith("HTTP/1.1 200"));
    expect(conduit?.bodies).toEqual([pieces * 100]);
    client.destroy();
  });
});

async function until(condition: () => boolean, ms = 3000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error("timed out");
    await sleep(10);
  }
}
