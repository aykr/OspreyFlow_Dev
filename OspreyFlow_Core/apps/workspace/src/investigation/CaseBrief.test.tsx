// @vitest-environment jsdom
// ADR-128 decision 3: the case's brief, in the Cases drawer beside the case's other settings. Every
// reader of the case reads it; only its Author edits, through the routes of `services/api/app.py`,
// which refuse anyone else whatever is shown here. These prove the Glass offers each edit to the
// Author alone, sends what was typed, shows what the server answers, and shows nothing about an
// attachment the server left out (rule 3: no title, no placeholder, no count).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaseBrief } from "./CaseBrief";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

type Requirement = {
  id: string;
  text: string;
  status: "open" | "answered";
  answered_at: string | null;
  attachments: { kind: string; id: string; title: string }[];
};
type Brief = { priority: string; requirements: Requirement[] };

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const requirement = (id: string, text: string, over: Partial<Requirement> = {}): Requirement => ({
  id,
  text,
  status: "open",
  answered_at: null,
  attachments: [],
  ...over,
});

function serve(options: { level?: string; brief?: Brief; extra?: Record<string, (init?: RequestInit) => Response> } = {}) {
  const { level = "author" } = options;
  let brief: Brief = options.brief ?? { priority: "Who is orchestrating the throw-overs?", requirements: [] };
  const calls: { key: string; body: unknown }[] = [];
  // What the next edit's route answers (the brief as it then stands), in the order they are made.
  const replies: Response[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
      calls.push({ key, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (init?.method && init.method !== "GET") {
        const reply = replies.shift();
        if (!reply) throw new Error(`no reply given for ${key}`);
        return reply;
      }
      if (key === "GET /v1/investigations")
        return json(200, [{ id: "c1", name: "C", level, created_at: "", created_by: "" }, { id: "c2", name: "Yards", level: "viewer", created_at: "", created_by: "" }]);
      if (key === "GET /v1/investigations/c1/brief") return json(200, brief);
      const handler = options.extra?.[key];
      if (handler) return handler(init);
      throw new Error(`unexpected ${key}`);
    }),
  );
  return {
    calls,
    set: (next: Brief) => {
      brief = next;
    },
    reply: (response: Response) => {
      replies.push(response);
    },
  };
}

const AUTHOR_RIGHTS = new Set(["share_case", "investigate"]);

function show(extra: Partial<React.ComponentProps<typeof CaseBrief>> = {}) {
  return render(
    <CaseBrief apiBaseUrl="http://api" bearerToken="t" investigationId="c1" rights={AUTHOR_RIGHTS} {...extra} />,
  );
}

describe("CaseBrief", () => {
  it("shows a reader the priority requirement and each requirement with its status, and offers no edit", async () => {
    serve({
      level: "viewer",
      brief: {
        priority: "Who is orchestrating the throw-overs?",
        requirements: [requirement("r1", "Who orchestrates?"), requirement("r2", "Where and when?", { status: "answered", answered_at: "2026-10-26T09:00:00Z" })],
      },
    });
    show();
    const section = await screen.findByRole("region", { name: "Brief" });
    expect(await within(section).findByText("Who is orchestrating the throw-overs?")).toBeTruthy();
    expect(within(section).getByText("Who orchestrates?")).toBeTruthy();
    expect(within(section).getByText("Where and when?")).toBeTruthy();
    expect(within(section).getByText("Open")).toBeTruthy();
    expect(within(section).getByText("Answered")).toBeTruthy();
    expect(within(section).queryAllByRole("button")).toEqual([]);
  });

  it("offers an Author without share_case no edit either, since the Conduit would refuse it", async () => {
    serve({ brief: { priority: "P", requirements: [requirement("r1", "R")] } });
    show({ rights: new Set(["investigate"]) });
    await screen.findByText("R");
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("says plainly when no priority is set and no requirement is held, and offers an Author the first", async () => {
    serve({ brief: { priority: "", requirements: [] } });
    show();
    expect(await screen.findByText("No priority information requirement is set.")).toBeTruthy();
    expect(screen.getByText("No information requirements yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add a requirement" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit the priority requirement" })).toBeTruthy();
  });

  it("lets the Author set the priority requirement, sending only its text", async () => {
    const world = serve({ brief: { priority: "", requirements: [] } });
    world.calls.length = 0;
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Edit the priority requirement" }));
    const box = screen.getByRole("textbox", { name: "Priority information requirement" });
    fireEvent.change(box, { target: { value: "Who is orchestrating?" } });
    // `serve` answers the mutating routes by key, so register the one this test needs.
    world.reply(json(200, { priority: "Who is orchestrating?", requirements: [] }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("Who is orchestrating?")).toBeTruthy());
    expect(world.calls.at(-1)).toEqual({ key: "PUT /v1/investigations/c1/brief/priority", body: { text: "Who is orchestrating?" } });
  });

  it("lets the Author add a requirement, sending its text and showing the brief the server answers", async () => {
    const world = serve({ brief: { priority: "P", requirements: [] } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add a requirement" }));
    fireEvent.change(screen.getByRole("textbox", { name: "New information requirement" }), { target: { value: "Who orchestrates?" } });
    world.reply(json(201, { priority: "P", requirements: [requirement("r1", "Who orchestrates?")] }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("Who orchestrates?")).toBeTruthy();
    expect(world.calls.at(-1)).toEqual({ key: "POST /v1/investigations/c1/brief/requirements", body: { text: "Who orchestrates?" } });
    expect(screen.queryByRole("textbox", { name: "New information requirement" })).toBeNull();
  });

  it("lets the Author edit a requirement's text with Save, and Escape cancels and returns focus to Edit", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Draft")] } });
    show();
    const edit = await screen.findByRole("button", { name: "Edit requirement 1" });
    fireEvent.click(edit);
    const box = screen.getByRole("textbox", { name: "Requirement 1" });
    fireEvent.change(box, { target: { value: "Dropped" } });
    fireEvent.keyDown(box, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: "Requirement 1" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Edit requirement 1" })));
    expect(screen.getByText("Draft")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Edit requirement 1" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Requirement 1" }), { target: { value: "Final" } });
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Final")] }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Final")).toBeTruthy();
    expect(world.calls.at(-1)).toEqual({ key: "PUT /v1/investigations/c1/brief/requirements/r1", body: { text: "Final" } });
  });

  it("lets the Author mark a requirement answered and reopen it, each by the status route alone", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?")] } });
    show();
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?", { status: "answered", answered_at: "2026-10-26T09:00:00Z" })] }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark requirement 1 answered" }));
    expect(await screen.findByText("Answered")).toBeTruthy();
    expect(world.calls.at(-1)).toEqual({ key: "PUT /v1/investigations/c1/brief/requirements/r1/status", body: { status: "answered" } });

    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?")] }));
    fireEvent.click(screen.getByRole("button", { name: "Reopen requirement 1" }));
    expect(await screen.findByText("Open")).toBeTruthy();
    expect(world.calls.at(-1)).toEqual({ key: "PUT /v1/investigations/c1/brief/requirements/r1/status", body: { status: "open" } });
  });

  it("sends no status when a requirement is added or edited", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?")] } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Edit requirement 1" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Requirement 1" }), { target: { value: "Who, then?" } });
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who, then?")] }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Who, then?");
    for (const call of world.calls.filter((c) => c.key.startsWith("PUT") || c.key.startsWith("POST"))) {
      expect(Object.keys(call.body as object)).not.toContain("status");
    }
  });

  it("removes a requirement only after a confirmation, and Keep leaves it", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?")] } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Remove requirement 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep requirement 1" }));
    expect(screen.getByText("Who?")).toBeTruthy();
    expect(world.calls.some((c) => c.key.startsWith("DELETE"))).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Remove requirement 1" }));
    world.reply(json(200, { priority: "P", requirements: [] }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove requirement 1" }));
    await waitFor(() => expect(screen.queryByText("Who?")).toBeNull());
    expect(world.calls.at(-1)?.key).toBe("DELETE /v1/investigations/c1/brief/requirements/r1");
  });

  it("opens an attachment from its own button, for a reader as for the Author", async () => {
    serve({
      level: "viewer",
      brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [{ kind: "trend", id: "t1", title: "Throw-overs by week" }, { kind: "assessment", id: "j1", title: "The wing's organiser" }] })] },
    });
    const onOpenAttachment = vi.fn();
    show({ onOpenAttachment });
    fireEvent.click(await screen.findByRole("button", { name: "Open trend: Throw-overs by week" }));
    expect(onOpenAttachment).toHaveBeenLastCalledWith("trend", "t1");
    fireEvent.click(screen.getByRole("button", { name: "Open assessment: The wing's organiser" }));
    expect(onOpenAttachment).toHaveBeenLastCalledWith("assessment", "j1");
  });

  it("shows nothing about attachments to a reader when the server left every one out (rule 3)", async () => {
    // The server's answer for a reader who may read none of what is attached: no title, no
    // placeholder and no count. The Glass adds none of its own.
    serve({ level: "viewer", brief: { priority: "P", requirements: [requirement("r1", "Who?"), requirement("r2", "Where?")] } });
    const { container } = show();
    await screen.findByText("Who?");
    expect(container.textContent ?? "").not.toMatch(/attach|cannot see|hidden|\b0\b|\(\d+\)/i);
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("lets the Author detach an attachment", async () => {
    const world = serve({
      brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [{ kind: "pattern", id: "p1", title: "Wing links" }] })] },
    });
    show();
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?")] }));
    fireEvent.click(await screen.findByRole("button", { name: "Detach pattern: Wing links" }));
    await waitFor(() => expect(screen.queryByText("Wing links")).toBeNull());
    expect(world.calls.at(-1)?.key).toBe("DELETE /v1/investigations/c1/brief/requirements/r1/attachments/pattern/p1");
  });

  it("lets the Author attach a trend chosen from the case's own saved trends, and offers none already attached", async () => {
    const world = serve({
      brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [{ kind: "trend", id: "t1", title: "Already here" }] })] },
      extra: {
        "GET /v1/investigations/c1/trends": () =>
          json(200, [
            { id: "t1", title: "Already here" },
            { id: "t2", title: "Throw-overs by week" },
          ]),
      },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Attach to requirement 1" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Kind of attachment" }), { target: { value: "trend" } });
    const choice = await screen.findByRole("combobox", { name: "What to attach" });
    expect(within(choice).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "Throw-overs by week"]);
    fireEvent.change(choice, { target: { value: "t2" } });
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [{ kind: "trend", id: "t1", title: "Already here" }, { kind: "trend", id: "t2", title: "Throw-overs by week" }] })] }));
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    expect(await screen.findByRole("button", { name: "Open trend: Throw-overs by week" })).toBeTruthy();
    expect(world.calls.at(-1)).toEqual({ key: "POST /v1/investigations/c1/brief/requirements/r1/attachments", body: { kind: "trend", id: "t2" } });
  });

  it("offers saved patterns, assessments and the cases other than this one as views", async () => {
    serve({
      brief: { priority: "P", requirements: [requirement("r1", "Who?")] },
      extra: {
        "GET /v1/investigations/c1/patterns": () => json(200, { patterns: [{ id: "x", pattern_id: "p1", version: 1, name: "Wing links", owner_id: "o", created_at: "", definition: {} }] }),
        "GET /v1/investigations/c1/judgements": () => json(200, { judgements: [{ id: "j1", statement: "The wing's organiser is X." }] }),
      },
    });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Attach to requirement 1" }));
    const kind = screen.getByRole("combobox", { name: "Kind of attachment" });
    const optionsFor = async (value: string) => {
      fireEvent.change(kind, { target: { value } });
      const choice = await screen.findByRole("combobox", { name: "What to attach" });
      await waitFor(() => expect(within(choice).getAllByRole("option").length).toBeGreaterThan(1));
      return within(choice).getAllByRole("option").map((o) => o.textContent);
    };
    expect(await optionsFor("pattern")).toEqual(["Choose…", "Wing links"]);
    expect(await optionsFor("assessment")).toEqual(["Choose…", "The wing's organiser is X."]);
    expect(await optionsFor("view")).toEqual(["Choose…", "Yards"]);
  });

  it("says in the server's words when an edit is refused, and keeps the brief as it was", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?")] } });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add a requirement" }));
    fireEvent.change(screen.getByRole("textbox", { name: "New information requirement" }), { target: { value: "One too many" } });
    world.reply(json(409, { error: "too_many_requirements", detail: "A brief can hold at most 20 requirements." }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect((await screen.findByRole("alert")).textContent).toContain("A brief can hold at most 20 requirements.");
    expect(screen.getByText("Who?")).toBeTruthy();
  });

  it("offers no further requirement once twenty are held, and says why", async () => {
    const twenty = Array.from({ length: 20 }, (_, n) => requirement(`r${n}`, `Requirement ${n + 1}`));
    serve({ brief: { priority: "P", requirements: twenty } });
    show();
    await screen.findByText("Requirement 20");
    expect(screen.queryByRole("button", { name: "Add a requirement" })).toBeNull();
    expect(screen.getByText("A brief holds at most 20 requirements.")).toBeTruthy();
  });

  it("says so, and shows no brief, when the case's brief cannot be read", async () => {
    serve({ brief: { priority: "P", requirements: [] } });
    (fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (url: string) =>
      String(url).endsWith("/v1/investigations") ? json(200, []) : json(404, { error: "investigation_not_found" }),
    );
    show();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("P")).toBeNull();
  });
});

// A different case opened (ADR-128 decision 3): the brief on screen is the new case's alone.
describe("CaseBrief when the open case changes", () => {
  type Deferred = { promise: Promise<Response>; resolve: (r: Response) => void };
  const deferred = (): Deferred => {
    let resolve!: (r: Response) => void;
    const promise = new Promise<Response>((r) => {
      resolve = r;
    });
    return { promise, resolve };
  };

  /** c1 answers at once, as its Author; c2's reads are held until the test lets them through. */
  function serveTwoCases() {
    const c2Brief = deferred();
    const c2Cases = deferred();
    const posts: { url: string; reply: Deferred }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        const key = `${init?.method ?? "GET"} ${url.replace("http://api", "")}`;
        if (init?.method === "POST") {
          const reply = deferred();
          posts.push({ url: key, reply });
          return reply.promise;
        }
        if (key === "GET /v1/investigations") {
          // The listing is asked for once per case opened; the second is held with c2's brief.
          return listingCalls++ === 0
            ? json(200, [{ id: "c1", name: "A", level: "author", created_at: "", created_by: "" }])
            : c2Cases.promise;
        }
        if (key === "GET /v1/investigations/c1/brief") return json(200, { priority: "Case A priority", requirements: [requirement("a1", "Case A requirement")] });
        if (key === "GET /v1/investigations/c2/brief") return c2Brief.promise;
        throw new Error(`unexpected ${key}`);
      }),
    );
    let listingCalls = 0;
    return { c2Brief, c2Cases, posts };
  }

  const view = (id: string) => (
    <CaseBrief apiBaseUrl="http://api" bearerToken="t" investigationId={id} rights={AUTHOR_RIGHTS} />
  );

  it("shows nothing of the previous case while the new one is read: no brief, no edit, no open Add box", async () => {
    serveTwoCases();
    const { rerender } = render(view("c1"));
    await screen.findByText("Case A priority");
    fireEvent.click(await screen.findByRole("button", { name: "Add a requirement" }));
    expect(screen.getByRole("textbox", { name: "New information requirement" })).toBeTruthy();
    rerender(view("c2"));
    expect(screen.queryByText("Case A priority")).toBeNull();
    expect(screen.queryByText("Case A requirement")).toBeNull();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a requirement" })).toBeNull();
    expect(screen.queryAllByRole("button")).toEqual([]);
  });

  it("does not let a change made in the previous case land in the new one", async () => {
    const world = serveTwoCases();
    const { rerender } = render(view("c1"));
    await screen.findByText("Case A priority");
    fireEvent.click(await screen.findByRole("button", { name: "Add a requirement" }));
    fireEvent.change(screen.getByRole("textbox", { name: "New information requirement" }), { target: { value: "Posted in A" } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "New information requirement" }), { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(world.posts).toHaveLength(1));
    expect(world.posts[0]!.url).toBe("POST /v1/investigations/c1/brief/requirements");
    rerender(view("c2"));
    world.c2Brief.resolve(json(200, { priority: "Case B priority", requirements: [] }));
    world.c2Cases.resolve(json(200, [{ id: "c2", name: "B", level: "viewer", created_at: "", created_by: "" }]));
    await screen.findByText("Case B priority");
    // A's request answers late, with A's brief.
    world.posts[0]!.reply.resolve(json(200, { priority: "Case A priority", requirements: [requirement("a2", "Posted in A")] }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Case B priority")).toBeTruthy();
    expect(screen.queryByText("Case A priority")).toBeNull();
    expect(screen.queryByText("Posted in A")).toBeNull();
    // Nor is B, which this reader may only read, offered A's edits.
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(world.posts).toHaveLength(1);
  });
});

describe("CaseBrief attachments", () => {
  const two = [
    { kind: "pattern", id: "p1", title: "Wing links" },
    { kind: "trend", id: "t1", title: "By week" },
  ];

  it("moves focus to the next attachment's Detach button after a detach, not to the page", async () => {
    const world = serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: two })] } });
    show();
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [two[1]!] })] }));
    const detach = await screen.findByRole("button", { name: "Detach pattern: Wing links" });
    detach.focus();
    fireEvent.click(detach);
    await waitFor(() => expect(screen.queryByText("Wing links")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Detach trend: By week" })));
  });

  it("moves focus to Attach after the last attachment is detached", async () => {
    const world = serve({
      brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [two[0]!] })] },
    });
    show();
    world.reply(json(200, { priority: "P", requirements: [requirement("r1", "Who?")] }));
    const detach = await screen.findByRole("button", { name: "Detach pattern: Wing links" });
    detach.focus();
    fireEvent.click(detach);
    await waitFor(() => expect(screen.queryByText("Wing links")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Attach to requirement 1" })));
  });

  it("does not offer Open when nothing was given to open an attachment with", async () => {
    serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [two[0]!] })] } });
    show();
    const open = (await screen.findByRole("button", { name: "Open pattern: Wing links" })) as HTMLButtonElement;
    expect(open.disabled).toBe(true);
  });

  it("offers Open, live, when it was", async () => {
    serve({ brief: { priority: "P", requirements: [requirement("r1", "Who?", { attachments: [two[0]!] })] } });
    const onOpenAttachment = vi.fn();
    show({ onOpenAttachment });
    const open = (await screen.findByRole("button", { name: "Open pattern: Wing links" })) as HTMLButtonElement;
    expect(open.disabled).toBe(false);
    fireEvent.click(open);
    expect(onOpenAttachment).toHaveBeenCalledWith("pattern", "p1");
  });
});

