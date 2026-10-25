// A small stateful fake of the trend and pack routes (ADR-113), shared by `trends.spec.ts` and
// `packs.spec.ts`. Synthetic data only (rule 9). It records each call so a spec can assert that a
// keyboard action reached the server with the right body; anything it does not know is a 404, so a
// call the screen should not make fails instead of being quietly accepted.
import type { Page } from "@playwright/test";

export interface Call {
  method: string;
  path: string;
  body: unknown;
}

type Json = Record<string, unknown>;

export const FIGURES = {
  period_weeks: 12, as_of: "2026-10-11", generated_at: "2026-10-11T08:00:00Z", alerts_total: 0,
  alerts_by_week: [], open_by_age: [], outcomes: [], held: null,
  kyc: { customers: 0, verified: 0, unverified: 0, by_band: [] },
};  // prettier-ignore

const OPTIONS = {
  event_types: [
    { name: "payment", label: "Payments", fields: [{ name: "amount", kind: "number" }, { name: "channel", kind: "category", values: ["card", "wire"] }] },
    { name: "login", label: "Logins", fields: [{ name: "country", kind: "category" }] },
  ],
};

export function trendFigures(title = "Payments by channel", marking = "OFFICIAL"): Json {
  return {
    definition: { title, event_types: ["payment"], measure: "sum", measure_field: "amount", interval: "week", weeks: 12, group_by: "channel", filters: [] },
    result: {
      interval: "week", measure: "sum", total: 600, events: 6, unvalued: 0, series: ["card", "wire"],
      points: ["2026-09-14", "2026-09-21", "2026-09-28"].flatMap((period_start) => [
        { period_start, series: "card", value: 100 }, { period_start, series: "wire", value: 100 }]),
    },
    as_of: "2026-10-11T08:00:00Z", window_start: "2026-07-19T00:00:00Z", marking,
  };  // prettier-ignore
}

export const SAVED_TREND = {
  id: "t1", investigation_id: "inv-1", created_by: "ana", created_at: "2026-10-01T09:00:00Z", updated_at: "2026-10-01T09:00:00Z",
  ...(trendFigures().definition as Json),
};

const base = { added_by: "ana", added_at: "2026-10-01T09:00:00Z" };
export const TREND_ITEM = { id: "i1", kind: "trend", marking: "OFFICIAL", trend_id: "t1", trend: trendFigures(), ...base };
export const ASSESSMENT_ITEM = {
  id: "i2", kind: "assessment", marking: "OFFICIAL-SENSITIVE", ...base,
  assessment: { judgement_id: "j1", statement: "The two firms share a director", probability_band: "likely", author: "ana", created_at: "2026-10-01T09:00:00Z" },
};  // prettier-ignore
export const NOTE_ITEM = { id: "i3", kind: "note", marking: "SECRET", note: "Handle with care", ...base };

export const PACK = { id: "p1", investigation_id: "inv-1", title: "Quarter pack", created_by: "ana", created_at: "2026-10-01T09:00:00Z", updated_at: "2026-10-01T09:00:00Z", versions: [] as unknown[] };
export const LIVE_VERSION = { version: 1, published_at: "2026-10-03T09:00:00Z", published_by: "ana", withdrawn_at: null, withdrawn_by: null, withdrawal_reason: null };

export interface World {
  trends: Json[];
  packs: (typeof PACK)[];
  items: Json[];
  withheld: boolean;
}

export function world(over: Partial<World> = {}): World {
  return { trends: [], packs: [], items: [], withheld: false, ...over, packs: (over.packs ?? []).map((p) => ({ ...p })) };
}

/** The Conduit's answer to one call, or null for a route it does not have. */
export function answer(w: World, call: Call): { status: number; body: unknown } | null {
  const { method, path } = call;
  const ok = (body: unknown, status = 200) => ({ status, body });
  const pack = () => w.packs[0] ?? PACK;
  const draft = () => ({ pack: pack(), items: w.items, withheld: w.withheld, marking: "SECRET" });
  if (path === "/v1/handling-scheme") return ok({ classification: ["OFFICIAL", "OFFICIAL-SENSITIVE", "SECRET"] });
  if (path.startsWith("reports?")) return ok(FIGURES);
  if (method === "GET" && path === "trends/options") return ok(OPTIONS);
  if (method === "GET" && path === "trends") return ok(w.trends);
  if (method === "POST" && path === "trends/preview") return ok(trendFigures((call.body as Json).title as string));
  if (method === "POST" && path === "trends") {
    const made = { ...SAVED_TREND, ...(call.body as Json) };
    w.trends.push(made);
    return ok(made, 201);
  }
  if (method === "GET" && path === "trends/t1/figures") return ok(trendFigures());
  if (method === "GET" && path === "packs") return ok(w.packs);
  if (method === "POST" && path === "packs") {
    const made = { ...PACK, title: (call.body as Json).title as string };
    w.packs.push(made);
    return ok(made, 201);
  }
  if (method === "GET" && path === "packs/p1") return ok(draft());
  if (method === "GET" && path === "judgements") return ok({ judgements: [{ id: "j1", statement: "The two firms share a director" }] });
  if (method === "POST" && path === "packs/p1/items") {
    const body = call.body as Json;
    const item = body.kind === "note" ? { ...NOTE_ITEM, id: "i9", note: body.text, marking: body.classification } : { ...TREND_ITEM, id: "i9" };
    w.items.push(item);
    return ok(item, 201);
  }
  if (method === "PUT" && path === "packs/p1/order") {
    const ids = (call.body as { item_ids: string[] }).item_ids;
    w.items = ids.map((id) => w.items.find((i) => i.id === id)!);
    return ok(draft());
  }
  const refresh = /^packs\/p1\/items\/([^/]+)\/refresh$/.exec(path);
  if (method === "POST" && refresh) {
    const at = w.items.findIndex((i) => i.id === refresh[1]);
    const fresh = { ...w.items[at], id: `${refresh[1]}b` };
    w.items[at] = fresh;
    return ok(fresh, 201);
  }
  if (method === "POST" && path === "packs/p1/publish") {
    pack().versions = [...pack().versions, { ...LIVE_VERSION, version: pack().versions.length + 1 }];
    return ok({ pack_id: "p1", title: pack().title, version: pack().versions.length, published_at: LIVE_VERSION.published_at, published_by: "ana", items: w.items, withheld: false, marking: "SECRET" }, 201);
  }
  if (method === "POST" && path === "packs/p1/versions/1/withdraw") {
    pack().versions = pack().versions.map((v) => ({ ...(v as Json), withdrawn_at: "2026-10-05T09:00:00Z", withdrawn_by: "ben", withdrawal_reason: (call.body as Json).reason }));
    return ok(pack());
  }
  if (method === "GET" && path === "published") {
    return ok(pack().versions.length ? [{ pack_id: "p1", title: pack().title, version: 1, published_at: LIVE_VERSION.published_at, published_by: "ana" }] : []);
  }
  if (method === "GET" && path === "packs/p1/published") {
    return ok({ pack_id: "p1", investigation_id: "inv-1", title: pack().title, version: 1, published_at: LIVE_VERSION.published_at, published_by: "ana", items: w.items, withheld: w.withheld, marking: "SECRET" });
  }
  if (method === "POST" && path === "packs/p1/export") {
    return ok({
      mark: { osprey_mark: "OspreyFlow", investigation_id: "inv-1", pack_id: "p1", version: 1, exported_at: "2026-10-11T09:30:00Z", exported_by: "ben", handling_level: "SECRET", rests_on_retracted_evidence: false },
      title: pack().title, version: 1, published_at: LIVE_VERSION.published_at, published_by: "ana", items: w.items, policy: "disclose", withheld: null, ledger_entry_id: "led-1",
    });  // prettier-ignore
  }
  return null;
}

/** Intercepts every call to the harness's server and answers from the world, recording each. */
export async function serveWorld(page: Page, w: World): Promise<Call[]> {
  const calls: Call[] = [];
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const call: Call = {
      method: request.method(),
      path: url.pathname.startsWith("/v1/investigations/inv-1/") ? `${url.pathname.replace("/v1/investigations/inv-1/", "")}${url.search}` : url.pathname,
      body: request.postData() ? JSON.parse(request.postData()!) : undefined,
    };
    calls.push(call);
    const reply = answer(w, call);
    if (!reply) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not found" }) });
    return route.fulfill({ status: reply.status, contentType: "application/json", body: JSON.stringify(reply.body) });
  });
  return calls;
}
