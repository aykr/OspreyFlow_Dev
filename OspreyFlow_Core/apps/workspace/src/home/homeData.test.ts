// ADR-115 E3: Home's figures, from the routes each place already has — every one counted as its
// reader, case by case (rule 3), so Home adds no read path of its own. A case that could not be read
// is said, never counted as nothing (rule 2's spirit: no silent shortfall).
import { describe, expect, it } from "vitest";

import { loadHome, openInQueue, summariseHome, whenLabel, type HomeInputs } from "./homeData";

const NOW = new Date("2026-10-13T09:00:00Z");
const CASES = [
  { id: "c1", name: "Operation Ledger — AML review", level: "editor" as const, created_at: "2026-10-11T09:00:00Z", created_by: "a" },
  { id: "c2", name: "HMP fixture (synthetic demo)", level: "viewer" as const, created_at: "2026-10-09T09:00:00Z", created_by: "b" },
];

function alert(id: string, status: string, assignee: string | null, at: string, typology = "kyc_screening") {
  return { alert: { id, status, assignee, typology, created_at: at, investigation_id: "c1" }, summary: `Finding ${id} in words.` };
}

const BASE: HomeInputs = {
  me: "u-me",
  now: NOW,
  cases: CASES,
  lastCaseId: "c1",
  perCase: {
    c1: {
      alerts: [alert("a1", "open", null, "2026-10-13T06:46:00Z"), alert("a2", "claimed", "u-me", "2026-10-12T15:00:00Z"),
               alert("a3", "claimed", "u-other", "2026-10-13T07:00:00Z"), alert("a4", "closed", "u-me", "2026-10-10T07:00:00Z")],
      held: [{ id: "h1", status: "held", reason: "A rule could not reach its screening list.", held_at: "2026-10-13T06:13:00Z" },
             { id: "h2", status: "held", reason: "A rule could not reach its screening list.", held_at: "2026-10-13T06:13:00Z" },
             { id: "h3", status: "released", reason: "x", held_at: "2026-10-12T06:13:00Z" }],
      recipes: [{ status: "flagged" }, { status: "published" }],
      entities: 68,
    },
    c2: { alerts: "unreadable", held: [], recipes: [], entities: 1041 },
  },
  system: { components: [{ name: "Graph store", ok: true }, { name: "Cache", ok: true }, { name: "Identity", ok: false }] },
  dashboards: [{ client_id: "osprey-dashboard-compliance-board", last_failure: "the token was rejected", failed_at: "2026-10-13T08:15:00Z" },
               { client_id: "osprey-dashboard-ok", last_failure: null, failed_at: null }],
}; // prettier-ignore

describe("Home's figures", () => {
  const home = summariseHome(BASE);

  it("counts the team's queue and what is claimed by the reader, and says which cases it could not read", () => {
    expect(home.glass.map((f) => f.text)).toEqual([
      "3 alerts in your team's queue, 1 claimed by you",
      "The queue of 1 case could not be read",
      "2 cases open to you, last worked on Operation Ledger — AML review",
    ]);
    expect(home.glass[1]!.tone).toBe("error");
  });

  it("counts rows still held and recipes flagged", () => {
    expect(home.studio.map((f) => [f.tone, f.text])).toEqual([
      ["warn", "2 rows held for review"],
      ["warn", "1 recipe flagged after an ontology change"],
    ]);
  });

  it("says how many services answered and which dashboard pulls are failing", () => {
    expect(home.admin.map((f) => [f.tone, f.text])).toEqual([
      ["warn", "2 of 3 services healthy"],
      ["error", "report-sync: 1 dashboard pull failing"],
    ]);
    expect(home.services).toEqual([{ name: "Graph store", ok: true }, { name: "Cache", ok: true }, { name: "Identity", ok: false }]);
  });

  it("lists what needs the reader, newest first: their own and unclaimed alerts, held rows by case, failing pulls", () => {
    expect(home.attention.map((a) => [a.place, a.title])).toEqual([
      ["admin", "osprey-dashboard-compliance-board is not updating"],
      ["glass", "KYC screening alert in Operation Ledger — AML review"],
      ["ingest", "2 rows held for review in Operation Ledger — AML review"],
      ["glass", "KYC screening alert in Operation Ledger — AML review"],
    ]);
    expect(home.attention[3]!.detail).toBe("Finding a2 in words. Claimed by you.");
    expect(home.attention.some((a) => a.detail.includes("a3"))).toBe(false);
  });

  it("lists the reader's cases with their level and what each holds as the reader sees it", () => {
    expect(home.recent).toEqual([
      { id: "c1", name: "Operation Ledger — AML review", level: "Editor", entities: 68, created: "2026-10-11T09:00:00Z" },
      { id: "c2", name: "HMP fixture (synthetic demo)", level: "Viewer", entities: 1041, created: "2026-10-09T09:00:00Z" },
    ]);
  });

  it("says nothing for a place whose figures the reader may not read", () => {
    const reader = summariseHome({ ...BASE, perCase: { c1: { entities: 68 }, c2: { entities: 1041 } }, system: undefined, dashboards: undefined });
    expect(reader.studio).toEqual([]);
    expect(reader.admin).toEqual([]);
    expect(reader.glass.map((f) => f.text)).toEqual(["2 cases open to you, last worked on Operation Ledger — AML review"]);
    expect(reader.services).toBeNull();
  });

  it("names a time as the hour today, yesterday, or the day", () => {
    expect(whenLabel("2026-10-13T06:46:00Z", NOW)).toMatch(/^\d\d:\d\d$/);
    expect(whenLabel("2026-10-12T06:46:00Z", NOW)).toBe("yesterday");
    expect(whenLabel("2026-10-09T06:46:00Z", NOW)).toBe("9 Oct");
  });
});

describe("reading Home's figures", () => {
  it("asks only what the reader's rights open, leaves out a case that refuses, and says one that fails", async () => {
    const asked: string[] = [];
    const fetcher = (async (url: string) => {
      const path = url.replace("http://api", "");
      asked.push(path);
      if (path === "/v1/investigations") return new Response(JSON.stringify(CASES));
      if (path === "/v1/investigations/c2/held-rows") return new Response("{}", { status: 403 });
      if (path === "/v1/investigations/c2/explore/counts") return new Response("{}", { status: 500 });
      if (path.endsWith("/held-rows")) return new Response("[]");
      if (path.endsWith("/explore/counts")) return new Response(JSON.stringify({ nodes: { Person: 3, Account: 4 } }));
      return new Response("{}", { status: 404 });
    }) as unknown as typeof fetch;
    const read = await loadHome({ apiBaseUrl: "http://api", bearerToken: "t", rights: new Set(["investigate", "read_held_rows"]),
                                  me: "u-me", lastCaseId: null, now: NOW, fetcher });  // prettier-ignore
    expect(asked.filter((p) => /alert-queue|recipes|admin/.test(p))).toEqual([]);
    expect(read.perCase.c1).toEqual({ alerts: undefined, held: [], recipes: undefined, entities: 7 });
    expect(read.perCase.c2!.held).toBeUndefined();
    expect(read.perCase.c2!.entities).toBe("unreadable");
    expect(read.system).toBeUndefined();
  });
});

describe("the team queue's count", () => {
  it("counts open and claimed alerts, never decided ones", () => {
    const at = (status: string) => ({ alert: { status } });
    expect(openInQueue([at("open"), at("claimed"), at("closed"), at("open")])).toBe(3);
  });
});
