// @vitest-environment jsdom
// ADR-151 (spec/00 §4's third choice): an expansion the cap refused, run whole on the server as a
// batch job, its result saved as a view of the case and opened as the lens. Every state is said in
// words, and so is each refusal the route gives (rule 15: the stand-in refuses what the real one
// will): no right to edit the case, a case the reader cannot open, an expansion past the batch job's
// own limit at the start or as it runs, a job that failed, a job no longer found, and a result view
// past the canvas's limit. Nothing is cut to fit.
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BatchExpansion } from "./BatchExpansion";
import type { BatchExpansionRequest } from "./batchExpansionApi";
import type { LimitExceeded } from "./models";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const REFUSED: LimitExceeded = {
  error: "limit_exceeded",
  cap_kind: "nodes",
  cap: 50_000,
  would_be: 61_200,
  options: ["save_as_view", "filter", "promote_to_batch"],
};
const REQUEST: BatchExpansionRequest = { nodeId: "n1", edgeType: "ASSOCIATE_OF", depth: 2, refused: REFUSED };
const VIEW = { id: "v9", case_id: "c1", name: "Expansion of Ada Lovelace", created_by: "a", created_at: "2026-11-14T10:00:00Z", shared: false, chosen: null };
const OPENED = { view: VIEW, nodes: [{ id: "n1", type: "Person" }], edges: [], layout: {}, missing: 0 };

type Reply = { status: number; body?: unknown };
type Call = { url: string; method: string; body: unknown; auth: string | undefined };

/** The Conduit: the start answers `start`, each read of the job answers the next of `reads` (the
 * last repeated), and opening a view answers `opening`. Every call is kept. */
function conduit(start: Reply, reads: Reply[] = [], opening: Reply = { status: 200, body: OPENED }) {
  const calls: Call[] = [];
  let read = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      calls.push({
        url,
        method,
        body: init.body ? JSON.parse(init.body as string) : undefined,
        auth: (init.headers as Record<string, string> | undefined)?.Authorization,
      });
      const reply = url.includes("/views/")
        ? opening
        : method === "POST"
          ? start
          : (reads[Math.min(read++, reads.length - 1)] ?? { status: 500 });
      return new Response(reply.body === undefined ? null : JSON.stringify(reply.body), { status: reply.status });
    }),
  );
  return calls;
}

function show(onViewOpened = vi.fn(), onClose = vi.fn()) {
  render(
    <BatchExpansion
      request={REQUEST}
      apiBaseUrl="http://conduit"
      bearerToken="tok"
      investigationId="c1"
      onViewOpened={onViewOpened}
      onClose={onClose}
      pollMs={5}
    />,
  );
  return { onViewOpened, onClose };
}

const alertText = async () => (await screen.findByRole("alert")).textContent ?? "";

describe("BatchExpansion", () => {
  it("starts the refused expansion as a batch job, with its node, type and depth, as the reader", async () => {
    const calls = conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "queued" } }]);
    show();
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("http://conduit/v1/investigations/c1/expand/batch");
    expect(post?.auth).toBe("Bearer tok");
    expect(post?.body).toEqual({ request: { node_ids: ["n1"], depth: 2, edge_types: ["ASSOCIATE_OF"] } });
    expect(screen.getByRole("region", { name: "Batch job: the whole expansion" }).textContent).toContain(
      "The canvas refused 61,200 nodes against its limit of 50,000",
    );
  });

  it("says it is waiting, then how far it has run, with a progress bar in figures", async () => {
    conduit({ status: 202, body: { job_id: "j1" } }, [
      { status: 200, body: { state: "queued" } },
      { status: 200, body: { state: "running", done: 1200, total: 4000 } },
    ]);
    show();
    await screen.findByText("The batch job is waiting for the server to start it.");
    await screen.findByText("Running the batch job: 30% done (1,200 of 4,000).");
    const bar = screen.getByRole("progressbar", { name: "Batch job progress" });
    expect(bar.getAttribute("value")).toBe("1200");
    expect(bar.getAttribute("max")).toBe("4000");
  });

  it("says it is running, without a bar, when the job gives no figures", async () => {
    conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "running" } }]);
    show();
    await screen.findByText("Running the batch job.");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("opens the job's result as the view and says so when the job is done", async () => {
    const calls = conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "done", view_id: "v9" } }]);
    const { onViewOpened } = show();
    await screen.findByText("The batch job has finished. Its result is open as the view “Expansion of Ada Lovelace”.");
    expect(onViewOpened).toHaveBeenCalledWith(OPENED);
    expect(calls.some((c) => c.url === "http://conduit/v1/investigations/c1/views/v9")).toBe(true);
  });

  it("says a reader without the right to edit the case cannot start one, and starts nothing", async () => {
    const calls = conduit({ status: 403, body: { detail: "forbidden" } });
    show();
    expect(await alertText()).toBe(
      "You cannot run a batch job in this case: its result is saved as a view of the case, and you do not have the right to edit it. No job was started.",
    );
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(0);
  });

  it("says a case the reader cannot open could not be, and starts nothing", async () => {
    conduit({ status: 404 });
    show();
    expect(await alertText()).toBe("This case could not be opened. It may have been closed, or not shared with you. No job was started.");
  });

  it("says an expansion past the batch job's own limit is refused at the start, in the reader's figure", async () => {
    conduit({ status: 409, body: { ...REFUSED, cap: 500_000, would_be: 812_000 } });
    show();
    expect(await alertText()).toBe(
      "Too large even for a batch job: 812,000 nodes against the batch job's limit of 500,000. No job was started. Expand by one relationship instead.",
    );
  });

  it("says a job whose result passed its limit stopped, saved nothing and cut nothing", async () => {
    const { onViewOpened } = (conduit({ status: 202, body: { job_id: "j1" } }, [
      { status: 200, body: { state: "refused", refused: { ...REFUSED, cap_kind: "edges", cap: 500_000, would_be: 640_000 } } },
    ]), show());
    expect(await alertText()).toBe(
      "The batch job stopped: its result would be 640,000 links against the batch job's limit of 500,000. Nothing was cut to fit, and no view was saved. Expand by one relationship instead.",
    );
    expect(onViewOpened).not.toHaveBeenCalled();
  });

  it("says a failed job failed, in the server's words, and offers to try it again", async () => {
    const calls = conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "failed", message: "The graph store stopped answering." } }]);
    show();
    expect(await alertText()).toBe("The batch job failed on the server: The graph store stopped answering. No view was saved.");
    fireEvent.click(screen.getByRole("button", { name: "Try the batch job again" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
  });

  it("says a job no longer found could not be", async () => {
    conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 404 }]);
    show();
    expect(await alertText()).toBe(
      "The batch job can no longer be found. It may have been cancelled, or the case closed or no longer shared with you.",
    );
  });

  it("says a result view past the canvas's limit is kept and was not cut to fit", async () => {
    const { onViewOpened } = (conduit(
      { status: 202, body: { job_id: "j1" } },
      [{ status: 200, body: { state: "done", view_id: "v9" } }],
      { status: 409, body: { ...REFUSED, would_be: 58_000 } },
    ), show());
    expect(await alertText()).toBe(
      "The batch job finished and saved its result as a view of this case, but the view holds more than the canvas can: 58,000 nodes against a limit of 50,000. Nothing was cut to fit; the view is kept in Views in this case.",
    );
    expect(onViewOpened).not.toHaveBeenCalled();
  });

  it("says a result view the reader cannot open could not be", async () => {
    conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "done", view_id: "v9" } }], { status: 404 });
    show();
    expect(await alertText()).toBe(
      "The batch job finished, but the view holding its result could not be opened. It may have been deleted, or not shared with you.",
    );
  });

  it("never reads a state it does not know as progress", async () => {
    conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "paused" } }]);
    show();
    expect(await alertText()).toBe("The batch job failed on the server: The server answered with a state the Glass does not know. No view was saved.");
  });

  it("says when the progress could not be read, and goes on asking", async () => {
    const calls = conduit({ status: 202, body: { job_id: "j1" } }, [
      { status: 503 },
      { status: 200, body: { state: "done", view_id: "v9" } },
    ]);
    const { onViewOpened } = show();
    await waitFor(() => expect(onViewOpened).toHaveBeenCalled());
    expect(calls.filter((c) => c.method === "GET" && c.url.includes("/expand/batch/j1")).length).toBe(2);
  });

  it("stops asking once closed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = conduit({ status: 202, body: { job_id: "j1" } }, [{ status: 200, body: { state: "queued" } }]);
    const { onClose } = show();
    await screen.findByText("The batch job is waiting for the server to start it.");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
    cleanup();
    const before = calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(calls.length).toBe(before);
  });
});
