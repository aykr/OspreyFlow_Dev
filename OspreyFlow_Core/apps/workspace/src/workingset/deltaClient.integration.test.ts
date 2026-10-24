// Drives `deltaClient.ts` against the *real* `services.api.app` FastAPI
// app over a real socket — this phase's own
// constraint: "a test that actually drives the client against the real
// WebSocket, not a canned fixture of deltas... a mock that only ever
// sends well-formed sequential ops won't catch a client that mishandles a
// resnapshot." `apps/workspace/test/glass_test_server.py` is the harness
// that starts that real process; see its module docstring for why.
//
// Needs `make dev-up`'s stack (ArcadeDB, Valkey, Postgres) running on its
// standard local ports — the same stack `make test-all` already requires.
// Skipped automatically (not failed) when the harness cannot start within
// its timeout, the same shape `tests/services/api/test_valkey_store.py`
// and friends use server-side for a live-infra dependency.
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { createInterface } from "node:readline";

import { afterAll, beforeAll, describe, expect, it } from "vitest";
import WebSocket from "ws";

import type { WorkingSetDelta } from "./models";
import { connectDeltaClient, type SocketLike } from "./deltaClient";

const REPO_ROOT = new URL("../../../../", import.meta.url).pathname;
const PYTHON = `${REPO_ROOT}.venv/bin/python`;
const HARNESS = `${REPO_ROOT}apps/workspace/test/glass_test_server.py`;

interface ServerHandle {
  port: number;
  token: string;
  process: ChildProcessWithoutNullStreams;
}

async function startServer(): Promise<ServerHandle> {
  const proc = spawn(PYTHON, [HARNESS], { cwd: REPO_ROOT });
  const rl = createInterface({ input: proc.stdout });
  const ready = new Promise<{ port: number; token: string }>((resolve, reject) => {
    rl.once("line", (line) => {
      try {
        resolve(JSON.parse(line));
      } catch (error) {
        reject(error);
      }
    });
    proc.once("error", reject);
    proc.stderr.on("data", (chunk) => {
      // Surfaced on test failure via the thrown error below, not printed
      // eagerly — uvicorn logs some routine startup lines to stderr too.
      lastStderr += chunk.toString();
    });
  });
  let lastStderr = "";
  const { port, token } = await Promise.race([
    ready,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`glass_test_server.py did not start: ${lastStderr}`)), 20_000),
    ),
  ]);
  return { port, token, process: proc };
}

async function waitUntilReady(baseUrl: string, token: string): Promise<void> {
  const deadline = Date.now() + 20_000;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/v1/investigations`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) return;
      lastError = new Error(`unexpected status ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw lastError;
}

describe("deltaClient against the real Conduit WebSocket", () => {
  let server: ServerHandle;
  let baseUrl: string;

  beforeAll(async () => {
    server = await startServer();
    baseUrl = `http://127.0.0.1:${server.port}`;
    await waitUntilReady(baseUrl, server.token);
  }, 30_000);

  afterAll(() => {
    server?.process.kill();
  });

  async function createInvestigation(): Promise<string> {
    const response = await fetch(`${baseUrl}/v1/investigations`, {
      method: "POST",
      headers: { Authorization: `Bearer ${server.token}` },
    });
    const body = (await response.json()) as { id: string };
    return body.id;
  }

  // Since ADR-099 a case reads only its own datasets, and seeding drops a node the case could not
  // read (CI, 15 October 2026: every snapshot came back empty). A seeded node is in the case's.
  async function caseDatasets(investigationId: string): Promise<string[]> {
    const response = await fetch(`${baseUrl}/v1/investigations/${investigationId}/datasets`, {
      headers: { Authorization: `Bearer ${server.token}` },
    });
    expect(response.ok).toBe(true);
    return ((await response.json()) as { id: string }[]).map((d) => d.id);
  }

  async function seedOneNode(investigationId: string, nodeId: string): Promise<void> {
    const datasets = await caseDatasets(investigationId);
    const response = await fetch(`${baseUrl}/v1/investigations/${investigationId}/seed`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${server.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        nodes: [
          {
            id: nodeId,
            type: "Person",
            provenance: {
              state: "asserted",
              sources: [{ document_id: "doc-1", locator: "p.1", excerpt_hash: "a".repeat(64) }],
              first_seen: "2026-01-01T00:00:00Z",
            },
            handling: {
              classification: "OFFICIAL",
              handling_code: "P",
              originator: "unit-1",
              owning_unit: "unit-1",
            },
            audit: { created_at: "2026-01-01T00:00:00Z", created_by: "loader-1" },
            datasets,
          },
        ],
        edges: [],
      }),
    });
    expect(response.ok).toBe(true);
  }

  function openSocket(investigationId: string): SocketLike {
    const ws = new WebSocket(`ws://127.0.0.1:${server.port}/v1/investigations/${investigationId}/stream`, {
      headers: { Authorization: `Bearer ${server.token}` },
    });
    return ws as unknown as SocketLike;
  }

  it("receives a snapshot on first connect", async () => {
    const investigationId = await createInvestigation();
    await seedOneNode(investigationId, "n1");

    const deltas: WorkingSetDelta[] = [];
    await new Promise<void>((resolve, reject) => {
      const client = connectDeltaClient(() => openSocket(investigationId), {
        onDelta: (delta) => {
          deltas.push(delta);
          if (delta.op === "snapshot") {
            client.close();
            resolve();
          }
        },
        onError: reject,
      });
    });

    expect(deltas).toHaveLength(1);
    expect(deltas[0]).toMatchObject({ op: "snapshot" });
    expect((deltas[0] as { nodes: { id: string }[] }).nodes.map((n) => n.id)).toEqual(["n1"]);
  }, 15_000);

  it("applies a real live delta pushed over Pub/Sub while connected", async () => {
    const investigationId = await createInvestigation();

    const deltas: WorkingSetDelta[] = [];
    let resolveGotSnapshot!: () => void;
    const gotSnapshot = new Promise<void>((resolve) => {
      resolveGotSnapshot = resolve;
    });
    const client = connectDeltaClient(() => openSocket(investigationId), {
      onDelta: (delta) => {
        deltas.push(delta);
        if (delta.op === "snapshot") resolveGotSnapshot();
      },
    });

    // Seed *after* the socket is open and has resnapshotted onto an empty
    // working set, so the next thing it sees is a genuine live push, not
    // part of the initial catch-up.
    await gotSnapshot;
    await seedOneNode(investigationId, "n-live");

    // Poll briefly for the live "add" to arrive — it comes over Pub/Sub
    // asynchronously relative to the HTTP call that triggered it.
    const deadline = Date.now() + 4_000;
    while (Date.now() < deadline && !deltas.some((d) => d.op === "add")) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    client.close();

    const added = deltas.find((d) => d.op === "add");
    expect(added).toBeDefined();
    expect((added as { nodes: { id: string }[] }).nodes.map((n) => n.id)).toEqual(["n-live"]);
  }, 15_000);

  it("requesting a resync after the delta history is gone gets a snapshot, not a patch", async () => {
    // A real, exact `XTRIM ... MAXLEN 0` against Valkey — not a fabricated
    // out-of-range sequence number — so this exercises the same
    // `deltas_after` "nothing retained" branch
    // (`services/api/working_set/store.py`) a long-lived investigation's
    // real, approximate trimming would eventually hit on its own; forcing
    // it exactly is what keeps this test fast.
    const Redis = (await import("ioredis")).default;
    const redis = new Redis({ host: "localhost", port: 6379, lazyConnect: true });
    await redis.connect();

    try {
      const investigationId = await createInvestigation();
      await seedOneNode(investigationId, "a");
      await seedOneNode(investigationId, "b");
      await redis.call("XTRIM", `ws:${investigationId}:deltas`, "MAXLEN", "0");

      const deltas: WorkingSetDelta[] = [];
      const gaps: Array<{ expected: number; actual: number }> = [];

      await new Promise<void>((resolve, reject) => {
        let resyncSent = false;
        const client = connectDeltaClient(() => openSocket(investigationId), {
          onDelta: (delta) => {
            deltas.push(delta);
            if (delta.op === "snapshot" && !resyncSent) {
              resyncSent = true;
              // A seq (1) strictly less than `current` (2, since two
              // nodes were seeded before this connection ever opened) —
              // legitimate a moment ago, now unresolvable purely because
              // the retained history behind it is gone. `since_seq >=
              // current` must be false here, or the server takes the
              // "already caught up" branch instead of the trimmed-gap one.
              client.requestResync(1);
            } else if (delta.op === "snapshot" && resyncSent) {
              client.close();
              resolve();
            }
          },
          onGapDetected: (expected, actual) => gaps.push({ expected, actual }),
          onError: reject,
        });
      });

      const snapshots = deltas.filter((d) => d.op === "snapshot");
      expect(snapshots).toHaveLength(2);
      expect(
        (snapshots[1] as { nodes: { id: string }[] }).nodes.map((n) => n.id).sort(),
      ).toEqual(["a", "b"]);
    } finally {
      redis.disconnect();
    }
  }, 15_000);
});
