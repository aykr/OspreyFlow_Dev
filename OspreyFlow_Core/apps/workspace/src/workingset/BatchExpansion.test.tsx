// @vitest-environment jsdom
// ADR-151 (spec/00 §4's third choice): an expansion the cap refused, run whole on the server as a
// batch job (rules-b's route, lane/rules-b-v052batch 208c397), its result saved as a private view of
// the case and opened as the lens. Every state is said in words: the server's own sentence for each
// stage, refusal and failure, shown as given, and the Glass's own for what it did with the result.
// The refusals are the route's (rule 15: the fake refuses what the real one does): a reader below
// Editor (403), a case not opened (404), a job already running here (409, followed), the job refused
// with figures or for another reason, a failed job, a job not this reader's (404), and a result view
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

function job(state: string, words: string, more: Record<string, unknown> = {}) {
  return { id: "j1", state, words, view: null, nodes: null, links: null, refusal: null, ...more };
}
const QUEUED = { status: 202, body: job("queued", "Waiting for the batch expansion to start.") };
const DONE = {
  status: 200,
  body: job("done", "Saved 61,200 nodes and 140,388 links as your private view “Expansion of Ada Lovelace”.", { view: VIEW, nodes: 61_200, links: 140_388 }),
};

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
const statusText = () => screen.getByRole("status").textContent ?? "";
const reads = (calls: Call[]) => calls.filter((c) => c.method === "GET" && c.url.includes("/batch-expansions/"));

describe("BatchExpansion", () => {
  it("starts exactly the refused expansion as a batch job, as the reader", async () => {
    const calls = conduit(QUEUED, [QUEUED]);
    show();
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("http://conduit/v1/investigations/c1/batch-expansions");
    expect(post?.auth).toBe("Bearer tok");
    expect(post?.body).toEqual({ request: { node_ids: ["n1"], depth: 2, edge_types: ["ASSOCIATE_OF"] } });
    expect(screen.getByRole("region", { name: "Batch job: the whole expansion" }).textContent).toContain(
      "The canvas refused 61,200 nodes against its limit of 50,000.",
    );
    await waitFor(() => expect(reads(calls)[0]?.url).toBe("http://conduit/v1/investigations/c1/batch-expansions/j1"));
  });

  it("says each stage in the server's own words", async () => {
    conduit(QUEUED, [
      { status: 200, body: job("running", "Expanding from 12 nodes.") },
      { status: 200, body: job("running", "Counting the links among 41,203 nodes.") },
      { status: 200, body: job("running", "Saving the view.") },
    ]);
    show();
    await screen.findByText("Waiting for the batch expansion to start.");
    await screen.findByText("Expanding from 12 nodes.");
    await screen.findByText("Counting the links among 41,203 nodes.");
    await screen.findByText("Saving the view.");
  });

  it("opens the job's result as the view, and says the server's words and that it is open", async () => {
    const calls = conduit(QUEUED, [DONE]);
    const { onViewOpened } = show();
    await waitFor(() => expect(onViewOpened).toHaveBeenCalledWith(OPENED));
    expect(statusText()).toBe(
      "Saved 61,200 nodes and 140,388 links as your private view “Expansion of Ada Lovelace”. Its result is open as the view “Expansion of Ada Lovelace”.",
    );
    expect(calls.some((c) => c.url === "http://conduit/v1/investigations/c1/views/v9")).toBe(true);
  });

  it("follows the job already running when the reader has one on this case", async () => {
    const calls = conduit(
      { status: 409, body: { error: "batch_expansion_running", detail: "A batch expansion of yours is already running in this case, so another was not started. Follow that one, or wait for it to finish.", id: "j7" } },
      [{ status: 200, body: { ...job("running", "Expanding from 3 nodes."), id: "j7" } }],
    );
    show();
    await screen.findByText("Expanding from 3 nodes.");
    expect(reads(calls).every((c) => c.url.endsWith("/batch-expansions/j7"))).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
    // It is another expansion, so this request's figures are not said of it.
    expect(screen.getByRole("region").textContent).not.toContain("61,200");
  });

  it("says a reader below Editor cannot start one in the Conduit's own sentence, and asks nothing more", async () => {
    const calls = conduit({ status: 403, body: { detail: "You hold Reader in this case; this needs Editor." } });
    show();
    expect(await alertText()).toBe("You hold Reader in this case; this needs Editor.");
    expect(reads(calls)).toHaveLength(0);
  });

  it("says it in its own words when the 403 sent no sentence", async () => {
    conduit({ status: 403, body: {} });
    show();
    expect(await alertText()).toBe(
      "You cannot run a batch job in this case: it needs the Editor level, since its result is saved as a view of the case. No job was started.",
    );
  });

  it("says an account without the right to expand cannot start one", async () => {
    conduit({ status: 403, body: { detail: { error: "right_required", right: "investigate" } } });
    show();
    expect(await alertText()).toBe(
      "Your account does not hold the right to expand a case, so it cannot run a batch job. No job was started.",
    );
  });

  it("says a case the reader cannot open could not be, and starts nothing", async () => {
    conduit({ status: 404 });
    show();
    expect(await alertText()).toBe("This case could not be opened. It may have been closed, or not shared with you. No job was started.");
  });

  it("says a refused job in the server's words, and opens nothing", async () => {
    const words = "Too many for a batch job: 812,000 nodes against a limit of 500,000. Nothing was saved. Choose a link type, a smaller depth or dates, and run it again.";
    const { onViewOpened } = (conduit(QUEUED, [
      { status: 200, body: job("refused", words, { refusal: { code: "too_many_nodes", cap_kind: "nodes", cap: 500_000, would_be: 812_000 } }) },
    ]), show());
    expect(await alertText()).toBe(words);
    expect(onViewOpened).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Try the batch job again" })).toBeNull();
  });

  it("says a refusal in its own figures when the server sent no words", async () => {
    conduit(QUEUED, [{ status: 200, body: job("refused", "", { refusal: { code: "too_many_links", cap_kind: "edges", cap: 500_000, would_be: 640_000 } }) }]);
    show();
    expect(await alertText()).toBe(
      "The batch expansion was refused: 640,000 links against a limit of 500,000. Nothing was saved. Narrow it by link type, depth or dates and try again.",
    );
  });

  it("says a failed job in the server's words, and offers to try it again", async () => {
    const calls = conduit(QUEUED, [{ status: 200, body: job("failed", "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion.") }]);
    show();
    expect(await alertText()).toBe("The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion.");
    fireEvent.click(screen.getByRole("button", { name: "Try the batch job again" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(2));
  });

  it("says a done job whose view has since been deleted in the server's words, and opens nothing", async () => {
    const words = "The batch expansion finished, but the view it saved has since been deleted.";
    const calls = conduit(QUEUED, [{ status: 200, body: job("done", words, { view: null }) }]);
    const { onViewOpened } = show();
    expect(await alertText()).toBe(words);
    expect(onViewOpened).not.toHaveBeenCalled();
    expect(calls.some((c) => c.url.includes("/views/"))).toBe(false);
  });

  it("says the job carries on when closed, only while it runs", async () => {
    conduit(QUEUED, [QUEUED, DONE]);
    show();
    await screen.findByText("Closing this does not stop the job. While it runs, asking for a batch expansion in this case again follows it.");
    await screen.findByText(/Its result is open as the view/);
    expect(screen.queryByText(/Closing this does not stop the job/)).toBeNull();
  });

  it("says a job that is not this reader's, or is gone, can no longer be found", async () => {
    conduit(QUEUED, [{ status: 404 }]);
    show();
    expect(await alertText()).toBe(
      "The batch expansion can no longer be found: it is not one of yours in this case, or the case is no longer shared with you.",
    );
  });

  it("says a result view past the canvas's limit is kept and was not cut to fit", async () => {
    const { onViewOpened } = (conduit(QUEUED, [DONE], { status: 409, body: { ...REFUSED, would_be: 58_000 } }), show());
    expect(await alertText()).toBe(
      "The batch job saved its result as the view “Expansion of Ada Lovelace”, but it holds more than the canvas can: 58,000 nodes against a limit of 50,000. Nothing was cut to fit; the view is kept in Views in this case.",
    );
    expect(onViewOpened).not.toHaveBeenCalled();
  });

  it("says a result view that could not be opened could not be", async () => {
    conduit(QUEUED, [DONE], { status: 404 });
    show();
    expect(await alertText()).toBe(
      "The batch job saved its result as the view “Expansion of Ada Lovelace”, but it could not be opened. It may have been deleted.",
    );
  });

  it("never reads a state it does not know as progress", async () => {
    conduit(QUEUED, [{ status: 200, body: job("paused", "Paused.") }]);
    show();
    expect(await alertText()).toBe("The server answered with a state the Glass does not know.");
  });

  it("says when the progress could not be read, and goes on asking", async () => {
    const calls = conduit(QUEUED, [{ status: 503 }, { status: 503 }, DONE]);
    const { onViewOpened } = show();
    await screen.findByText("The job's progress could not be read (503). Still trying.");
    await waitFor(() => expect(onViewOpened).toHaveBeenCalled());
    expect(reads(calls)).toHaveLength(3);
  });

  it("stops asking, and says so, when its sign-in has ended", async () => {
    const calls = conduit(QUEUED, [{ status: 401 }]);
    show();
    expect(await alertText()).toBe("The job's progress could not be read: your sign-in has ended. Sign in again.");
    const asked = reads(calls).length;
    await new Promise((r) => setTimeout(r, 40));
    expect(reads(calls)).toHaveLength(asked);
  });

  it("stops asking after a minute of readings that fail, and says the job carries on", async () => {
    const calls = conduit(QUEUED, [{ status: 503 }]);
    show();
    expect(await alertText()).toBe(
      "The job's progress could not be read (503). The batch expansion carries on on the server; while it runs, asking for a batch expansion in this case again follows it.",
    );
    expect(reads(calls)).toHaveLength(30);
  });

  it("starts one job, whatever the panel is given later: a new request object, a renewed token", async () => {
    const calls = conduit(QUEUED, [...Array<typeof QUEUED>(20).fill(QUEUED), DONE]);
    const onViewOpened = vi.fn();
    const props = { apiBaseUrl: "http://conduit", investigationId: "c1", onViewOpened, onClose: vi.fn(), pollMs: 5 };
    const { rerender } = render(<BatchExpansion {...props} request={REQUEST} bearerToken="tok" />);
    await waitFor(() => expect(reads(calls).length).toBeGreaterThan(0));
    rerender(<BatchExpansion {...props} request={{ ...REQUEST }} bearerToken="renewed" />);
    await waitFor(() => expect(onViewOpened).toHaveBeenCalledTimes(1));
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(1);
    // The readings after the renewal, and the view's opening, carry the renewed token.
    expect(calls.at(-1)?.url).toBe("http://conduit/v1/investigations/c1/views/v9");
    expect(calls.at(-1)?.auth).toBe("Bearer renewed");
  });

  it("stops asking once closed", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = conduit(QUEUED, [QUEUED]);
    const { onClose } = show();
    await screen.findByText("Waiting for the batch expansion to start.");
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
