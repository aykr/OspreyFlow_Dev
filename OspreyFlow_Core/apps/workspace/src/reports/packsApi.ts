// The pack calls (ADR-113 stage 5): assembling a pack, publishing it, reading what is published,
// and exporting it. Shapes are the generated ones; refusals are said in words.
import type {
  AddPackItem,
  Judgement,
  PackDraft,
  PackExport,
  PackExportRequest,
  PackHistory,
  PackItem,
  PublishedPack,
  PublishedPackSummary,
  PackWithheldBody,
  ReportPack,
} from "../../../../packages/schemas/generated";
import type { BlockedItem } from "../export/api";
import type { ReportsApi } from "./api";
import { fieldOf, refusal, send } from "./caseHttp";
import { withheldSentence } from "./packText";

const enc = encodeURIComponent;

export async function listPacks(api: ReportsApi): Promise<ReportPack[]> {
  const reply = await send(api, "GET", "packs");
  if (!reply.ok) throw refusal(reply, "read the packs");
  return reply.body as ReportPack[];
}

export async function createPack(api: ReportsApi, title: string): Promise<ReportPack> {
  const reply = await send(api, "POST", "packs", { title });
  if (!reply.ok) throw refusal(reply, "create a pack");
  return reply.body as ReportPack;
}

export async function getDraft(api: ReportsApi, packId: string): Promise<PackDraft> {
  const reply = await send(api, "GET", `packs/${enc(packId)}`);
  if (!reply.ok) throw refusal(reply, "open this pack");
  return reply.body as PackDraft;
}

export async function addItem(api: ReportsApi, packId: string, item: AddPackItem): Promise<PackItem> {
  const reply = await send(api, "POST", `packs/${enc(packId)}/items`, item);
  if (!reply.ok) throw refusal(reply, "add this item");
  return reply.body as PackItem;
}

export async function removeItem(api: ReportsApi, packId: string, itemId: string): Promise<void> {
  const reply = await send(api, "DELETE", `packs/${enc(packId)}/items/${enc(itemId)}`);
  if (!reply.ok) throw refusal(reply, "remove this item");
}

/** `itemIds` is exactly the items you were shown, in the new order. */
export async function reorderItems(api: ReportsApi, packId: string, itemIds: string[]): Promise<PackDraft> {
  const reply = await send(api, "PUT", `packs/${enc(packId)}/order`, { item_ids: itemIds });
  if (!reply.ok) throw refusal(reply, "reorder this pack");
  return reply.body as PackDraft;
}

export async function refreshItem(api: ReportsApi, packId: string, itemId: string): Promise<PackItem> {
  const reply = await send(api, "POST", `packs/${enc(packId)}/items/${enc(itemId)}/refresh`);
  if (!reply.ok) throw refusal(reply, "refresh this snapshot");
  return reply.body as PackItem;
}

export async function fetchHistory(api: ReportsApi, packId: string): Promise<PackHistory> {
  const reply = await send(api, "GET", `packs/${enc(packId)}/history`);
  if (!reply.ok) throw refusal(reply, "read this pack's history");
  return reply.body as PackHistory;
}

export async function publishPack(api: ReportsApi, packId: string): Promise<PublishedPack> {
  const reply = await send(api, "POST", `packs/${enc(packId)}/publish`);
  if (reply.status === 409 && fieldOf(reply.body, "error") === "pack_has_withheld_items") {
    const n = (reply.body as PackWithheldBody).withheld;
    throw new Error(`${withheldSentence(n).replace(/ from you\.$/, " from you, so you cannot publish it.")}`);
  }
  if (!reply.ok) throw refusal(reply, "publish this pack");
  return reply.body as PublishedPack;
}

export async function withdrawVersion(api: ReportsApi, packId: string, version: number, reason: string): Promise<ReportPack> {
  const reply = await send(api, "POST", `packs/${enc(packId)}/versions/${version}/withdraw`, { reason });
  if (!reply.ok) throw refusal(reply, "withdraw this version");
  return reply.body as ReportPack;
}

export async function listPublished(api: ReportsApi): Promise<PublishedPackSummary[]> {
  const reply = await send(api, "GET", "published");
  if (!reply.ok) throw refusal(reply, "read the published packs");
  return reply.body as PublishedPackSummary[];
}

export async function getPublished(api: ReportsApi, packId: string): Promise<PublishedPack> {
  const reply = await send(api, "GET", `packs/${enc(packId)}/published`);
  if (!reply.ok) throw refusal(reply, "open this published pack");
  return reply.body as PublishedPack;
}

export async function listJudgements(api: ReportsApi): Promise<Judgement[]> {
  const reply = await send(api, "GET", "judgements");
  if (!reply.ok) throw refusal(reply, "read the assessments");
  return (fieldOf(reply.body, "judgements") ?? []) as Judgement[];
}

/** The deployment's classifications, lowest first (`GET /v1/handling-scheme`). */
export async function fetchClassifications(api: ReportsApi): Promise<string[]> {
  const response = await fetch(`${api.apiBaseUrl}/v1/handling-scheme`, {
    headers: { Authorization: `Bearer ${api.bearerToken}` },
  });
  if (!response.ok) throw new Error("The handling markings could not be read, so a note cannot be marked. Reload to try again.");
  const scheme = (await response.json()) as { classification?: string[] };
  return scheme.classification ?? [];
}

/** What an export asks for: the manifest, or the blocked items that need a justification. */
export type ExportOutcome =
  | { kind: "exported"; manifest: PackExport }
  | { kind: "override_required"; blocked: BlockedItem[]; detail: string };

export async function exportPack(api: ReportsApi, packId: string, request: PackExportRequest): Promise<ExportOutcome> {
  const reply = await send(api, "POST", `packs/${enc(packId)}/export`, request);
  if (reply.status === 422 && fieldOf(reply.body, "error") === "override_required") {
    return {
      kind: "override_required",
      blocked: (fieldOf(reply.body, "blocked") ?? []) as BlockedItem[],
      detail: String(fieldOf(reply.body, "detail") ?? ""),
    };
  }
  if (!reply.ok) throw refusal(reply, "export this pack");
  return { kind: "exported", manifest: reply.body as PackExport };
}
