// Shared by the trend, pack and published-pack tests: a fake server that records every call, and
// synthetic fixtures (rule 9 — nothing here is real data). The fake answers only what a test gives
// it; anything else is a 404 in the server's own words, so a call the screen should not make fails
// loudly instead of being quietly accepted.
import { vi } from "vitest";

import type { PackDraft, PackExport, PackItem, ReportPack, TrendFigures, TrendOptions } from "../../../../packages/schemas/generated";

export const json = (status: number, body: unknown) => new Response(status === 204 ? null : JSON.stringify(body), { status });

export interface Call {
  method: string;
  /** Relative to the case, e.g. `packs/p1/order`; the handling scheme keeps its full path. */
  path: string;
  body: unknown;
}

export function serve(handler: (call: Call) => Response | null): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (raw: string, init?: RequestInit) => {
      const url = new URL(raw);
      const call: Call = {
        method: init?.method ?? "GET",
        path: url.pathname.replace("/v1/investigations/c1/", ""),
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      };
      calls.push(call);
      return handler(call) ?? json(404, { detail: "not found" });
    }),
  );
  return calls;
}

export const OPTIONS: TrendOptions = {
  event_types: [
    { name: "payment", label: "Payments", fields: [{ name: "amount", kind: "number" }, { name: "channel", kind: "category", values: ["card", "wire"] }] },
    { name: "transfer", label: "Transfers", fields: [{ name: "amount", kind: "number" }, { name: "fee", kind: "number" }, { name: "channel", kind: "category" }] },
    { name: "login", label: "Logins", fields: [{ name: "country", kind: "category" }] },
  ],
};

export function figures(over: Partial<TrendFigures["definition"]> = {}, marking: string | null = "OFFICIAL"): TrendFigures {
  const periods = ["2026-09-14", "2026-09-21", "2026-09-28"];
  return {
    definition: { title: "Payments by channel", event_types: ["payment"], measure: "sum", measure_field: "amount", interval: "week", weeks: 12, group_by: "channel", filters: [], ...over },
    result: {
      interval: "week",
      measure: "sum",
      points: periods.flatMap((period_start, i) => [
        { period_start, series: "card", value: 100 * (i + 1) },
        { period_start, series: "wire", value: 50 },
      ]),
      series: ["card", "wire"],
      total: 12400,
      events: 31,
      unvalued: 2,
    },
    as_of: "2026-10-11T08:00:00Z",
    window_start: "2026-07-19T00:00:00Z",
    marking,
  };
}

export const PACK: ReportPack = {
  id: "p1",
  investigation_id: "c1",
  title: "Quarter pack",
  created_by: "ana",
  created_at: "2026-10-01T09:00:00Z",
  updated_at: "2026-10-01T09:00:00Z",
  versions: [],
};

export const PUBLISHED_PACK: ReportPack = {
  ...PACK,
  versions: [{ version: 1, published_at: "2026-10-03T09:00:00Z", published_by: "ana", withdrawn_at: null, withdrawn_by: null, withdrawal_reason: null }],
};

export const TREND_ITEM: PackItem = { id: "i1", kind: "trend", marking: "OFFICIAL", added_by: "ana", added_at: "2026-10-01T09:00:00Z", trend_id: "t1", trend: figures() };
export const ASSESSMENT_ITEM: PackItem = {
  id: "i2", kind: "assessment", marking: "OFFICIAL-SENSITIVE", added_by: "ana", added_at: "2026-10-01T09:00:00Z",
  assessment: { judgement_id: "j1", statement: "The two firms share a director", probability_band: "likely", author: "ana", created_at: "2026-10-01T09:00:00Z" },
};
export const NOTE_ITEM: PackItem = { id: "i3", kind: "note", marking: "SECRET", added_by: "ana", added_at: "2026-10-01T09:00:00Z", note: "Handle with care" };

export const OFFICIAL_ITEM_FOR_EXPORT: PackItem = { id: "n1", kind: "note", marking: "OFFICIAL", added_by: "ana", added_at: "2026-10-01T09:00:00Z", note: "A public matter" };

export function draft(over: Partial<PackDraft> = {}): PackDraft {
  return { pack: PACK, items: [TREND_ITEM, ASSESSMENT_ITEM, NOTE_ITEM], withheld: false, marking: "SECRET", ...over };
}

export function manifest(items: PackItem[], over: Partial<PackExport> = {}): PackExport {
  return {
    mark: { osprey_mark: "OspreyFlow", investigation_id: "c1", pack_id: "p1", version: 1, exported_at: "2026-10-11T09:30:00Z", exported_by: "ben", handling_level: "SECRET", rests_on_retracted_evidence: false },
    title: "Quarter pack",
    version: 1,
    published_at: "2026-10-03T09:00:00Z",
    published_by: "ana",
    items,
    policy: "disclose",
    withheld: null,
    ledger_entry_id: "led-1",
    ...over,
  };
}

// ADR-134 decision 1: an alert as a pack item — synthetic, open, its match not yet confirmed.
export const ALERT_ITEM: PackItem = {
  id: "i4", kind: "alert", marking: "OFFICIAL", added_by: "ana", added_at: "2026-10-01T09:00:00Z",
  alert: {
    alert_id: "a1", kind: "typology", severity: "high", typology: "rapid_movement",
    explanation: "Money in and straight out again through Halcyon Marine Ltd",
    raised_at: "2026-09-29T14:00:00Z",
    entities: [{ node_id: "n1", entity_type: "Organisation", name: "Halcyon Marine Ltd" }],
    links: [{ edge_id: "e1", type: "TRANSACTED", source_name: "Halcyon Marine Ltd", target_name: "Ardent Freight" }],
    transactions: [{ occurred_at: "2026-09-28T10:00:00Z", amount: 9500, source_name: "Halcyon Marine Ltd", target_name: "Ardent Freight" }],
    status: "open", outcome: null, reason: null, match: "inferred", node_ids: ["n1"],
  },
};

export const CLOSED_ALERT_ITEM: PackItem = {
  ...ALERT_ITEM, id: "i5",
  alert: { ...ALERT_ITEM.alert!, alert_id: "a2", status: "closed", outcome: "true_positive", reason: "Confirmed with the bank", match: "confirmed" },
};

/** The one queue's rows (`GET alert-queue`), as the pack editor lists them to add. */
export const QUEUED = [
  { alert: { id: "a1", rule_id: "typology:r1", owner_id: "ana", mode: "full", referent_node_ids: ["n1"], created_at: "2026-09-29T14:00:00Z", status: "open" },
    summary: "Money in and straight out again through Halcyon Marine Ltd", kind: "typology", severity: "high", audience: "case" },
  { alert: { id: "a3", rule_id: "hotlist:h1", owner_id: "ana", mode: "full", referent_node_ids: ["n2"], created_at: "2026-09-30T08:00:00Z", status: "claimed" },
    summary: "A hotlisted identifier appeared: +447700900310", kind: "hotlist", severity: "high", audience: "owner" },
];

/** ADR-134 decision 3: what an alert trend may split by and filter on, with this case's rules. */
export const ALERT_OPTIONS: TrendOptions = {
  ...OPTIONS,
  alert_fields: [
    { name: "rule", kind: "category", values: ["typology:r1", "hotlists", "monitors"], labels: ["Rapid movement over £9,000", "Hotlists", "Monitors"] },
    { name: "typology", kind: "category", values: ["rapid_movement"], labels: [] },
    { name: "severity", kind: "category", values: ["high", "medium", "low"], labels: ["High", "Medium", "Low"] },
    { name: "outcome", kind: "category", values: ["open", "claimed", "true_positive", "false_positive", "closed"], labels: ["Open", "Claimed", "True positive", "False positive", "Closed, no outcome"] },
  ],
};
