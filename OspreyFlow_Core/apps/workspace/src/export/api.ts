// Fetch wrappers for `POST /v1/investigations/{id}/export` (`services/api/export.py`,
// `services/api/app.py::submit_export_route`) — Phase 8 Stage 4e. Mirrors `assessment/api.ts`'s
// own conventions (Bearer auth, throw a typed error carrying the server's own named-item body
// rather than a bare "export failed" string, `02_GLASS_FRONTEND.md` §4.1's own copy discipline).
//
// **`BlockedItem`/`ExportResult`/`ExportMark`/`ExportManifest` are hand-mirrored here, not
// imported from `packages/schemas/generated/`** — the same disclosed gap `assessment/api.ts`'s
// own header comment already names for `Yardstick`: these types live in `services/api/export.py`,
// outside `packages/schemas/generate_ts.py`'s own `schemas.{analytics,compute,domain,ingest,
// model,profile,provider_profile}` model list.

import { WITHHELD_SENTENCE } from "../statusbar/StatusBar";

export interface BlockedItem {
  id: string;
  kind: "node" | "edge" | "judgement";
  label: string;
  reason: "access_denied" | "consult_originator" | "citation_unverifiable";
}

/** `services/api/app.py::_export_blocked_handler` — every named blocking item, whatever the mix
 * of reasons. Thrown for `access_denied`/`citation_unverifiable` items (never overridable) and
 * for a `consult_originator` item with no override attempted at all. */
export class ExportBlockedApiError extends Error {
  blocked: BlockedItem[];
  constructor(message: string, blocked: BlockedItem[]) {
    super(message);
    this.name = "ExportBlockedApiError";
    this.blocked = blocked;
  }
}

/** `services/api/app.py::_override_required_handler` — a subclass, not a sibling: every
 * `OverrideRequiredError` is also an `ExportBlockedError` server-side
 * (`services/api/export.py::OverrideRequiredError`'s own docstring), so a caller that only
 * catches the parent still sees it; one building the override form specifically catches this one
 * to distinguish "overridable, try again with both fields" from "never overridable". */
export class OverrideRequiredApiError extends ExportBlockedApiError {
  constructor(message: string, blocked: BlockedItem[]) {
    super(message, blocked);
    this.name = "OverrideRequiredApiError";
  }
}

export interface ExportMark {
  osprey_mark: "OspreyFlow";
  investigation_id: string;
  exported_at: string;
  resolution_threshold: number;
  handling_level: string;
}

/** The export's manifest (ADR-045, ADR-124 decision 9): a yes or no, never a number. Under
 * `disclose`, `withheld` is whether the case holds material the exporter may not view; under
 * `omit` it is `null`. Mirrors `ExportManifest` in `services/api/export.py`. */
export interface ExportManifest {
  policy: "disclose" | "omit";
  withheld: boolean | null;
}

/** The pack's own sentence: the flag on a pack export means some of the pack's items are left out
 * of this export (its handling, a stale or superseded item, a dataset), which is not what the
 * case's standing sentence says. */
export const PACK_WITHHELD_SENTENCE = "Some items of this pack are not included in this export.";

/** What every renderer of an export's manifest says, for a case export (`"case"`, the default: the
 * status bar's standing sentence) or a pack export (`"pack"`): its sentence while the flag is true
 * and the deployment discloses it, otherwise nothing. */
export function manifestSentence(
  manifest: { policy: "disclose" | "omit"; withheld?: boolean | null },
  kind: "case" | "pack" = "case",
): string | null {
  if (manifest.policy !== "disclose" || manifest.withheld !== true) return null;
  return kind === "pack" ? PACK_WITHHELD_SENTENCE : WITHHELD_SENTENCE;
}

export interface ExportResult {
  mark: ExportMark;
  manifest: ExportManifest;
  ledger_entry_id: string;
}

export interface ExportItemRequest {
  id: string;
  kind: "node" | "edge";
  handling: Record<string, unknown>;
  label?: string;
}

export interface SubmitExportRequest {
  artefact_kind: "chart" | "subgraph" | "report";
  items: ExportItemRequest[];
  judgement_ids?: string[];
  resolution_threshold: number;
  justification?: string;
  originator_reference?: string;
}

function authHeaders(bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}` };
}

export async function submitExport(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  request: SubmitExportRequest,
): Promise<ExportResult> {
  const response = await fetch(`${apiBaseUrl}/v1/investigations/${investigationId}/export`, {
    method: "POST",
    headers: { ...authHeaders(bearerToken), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    let body: { error?: string; detail?: string; blocked?: BlockedItem[] } = {};
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body — fall through to the generic message below.
    }
    if (body.error === "override_required" && body.blocked) {
      throw new OverrideRequiredApiError(
        body.detail ?? "a justification and an originator reference are both required",
        body.blocked,
      );
    }
    if (body.error === "export_blocked" && body.blocked) {
      throw new ExportBlockedApiError(body.detail ?? "export blocked", body.blocked);
    }
    throw new Error(`POST .../export failed: ${response.status}`);
  }
  return (await response.json()) as ExportResult;
}

export async function getResolutionThreshold(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
): Promise<number> {
  const response = await fetch(
    `${apiBaseUrl}/v1/investigations/${investigationId}/resolution/threshold`,
    { headers: authHeaders(bearerToken) },
  );
  if (!response.ok) {
    throw new Error(`GET .../resolution/threshold failed: ${response.status}`);
  }
  const body = (await response.json()) as { threshold: number };
  return body.threshold;
}
