// Fetch wrappers for the case brief's routes (`services/api/case_brief.py`, ADR-128 decision 3):
// `GET /v1/investigations/{id}/brief` and the Author's edits under it. Every call answers with the
// brief as the caller may now read it, so what is shown is always what the server says. The shapes
// are written by hand: `case_brief.py` is not in `schemas-check`'s model list, which covers
// `schemas.*` only, the same disclosed gap `cases.ts` names for the case listing.
import { listJudgements } from "../assessment/api";
import { listPatterns } from "../patterns/api";
import { fieldOf, refusal, send, type Reply } from "../reports/caseHttp";
import { listTrends } from "../reports/trendsApi";
import { listCases } from "./cases";

export type AttachmentKind = "trend" | "pattern" | "assessment" | "view";
export type RequirementStatus = "open" | "answered";

/** What marks an attachment: its kind, the id the Conduit holds it by, and the title the Conduit
 * gave this reader. An attachment the reader may not read is not in the list at all. */
export interface BriefAttachment {
  kind: AttachmentKind;
  id: string;
  title: string;
}

export interface BriefRequirement {
  id: string;
  text: string;
  status: RequirementStatus;
  answered_at: string | null;
  attachments: BriefAttachment[];
}

export interface CaseBriefView {
  priority: string;
  requirements: BriefRequirement[];
}

export interface BriefApi {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
}

/** ADR-128: the most requirements a brief holds; the Conduit refuses the next, by name. */
export const MAX_REQUIREMENTS = 20;
/** The most characters a brief's text holds; the Conduit refuses more rather than cut it. */
export const MAX_TEXT_CHARS = 2000;

export const KIND_CHOICES: readonly { value: AttachmentKind; label: string }[] = [
  { value: "trend", label: "Trend" },
  { value: "pattern", label: "Saved pattern" },
  { value: "assessment", label: "Assessment" },
  { value: "view", label: "Canvas view" },
];

function briefOf(reply: Reply, what: string): CaseBriefView {
  if (!reply.ok) throw refusal(reply, what);
  const body = reply.body;
  const requirements = fieldOf(body, "requirements");
  if (!Array.isArray(requirements)) throw new Error(`Could not ${what}: the server's answer was not a brief.`);
  return body as CaseBriefView;
}

const requirementPath = (id: string) => `brief/requirements/${encodeURIComponent(id)}`;

export async function readBrief(api: BriefApi): Promise<CaseBriefView> {
  return briefOf(await send(api, "GET", "brief"), "read the brief");
}

export async function setPriority(api: BriefApi, text: string): Promise<CaseBriefView> {
  return briefOf(await send(api, "PUT", "brief/priority", { text }), "save the priority requirement");
}

export async function addRequirement(api: BriefApi, text: string): Promise<CaseBriefView> {
  return briefOf(await send(api, "POST", "brief/requirements", { text }), "add the requirement");
}

export async function editRequirement(api: BriefApi, id: string, text: string): Promise<CaseBriefView> {
  return briefOf(await send(api, "PUT", requirementPath(id), { text }), "save the requirement");
}

export async function removeRequirement(api: BriefApi, id: string): Promise<CaseBriefView> {
  return briefOf(await send(api, "DELETE", requirementPath(id)), "remove the requirement");
}

/** The one call that marks a requirement answered, and a person's: nothing the Glass does for a
 * model calls it (rule 5). */
export async function setStatus(api: BriefApi, id: string, status: RequirementStatus): Promise<CaseBriefView> {
  return briefOf(await send(api, "PUT", `${requirementPath(id)}/status`, { status }), "change the status");
}

export async function attach(api: BriefApi, id: string, kind: AttachmentKind, attachmentId: string): Promise<CaseBriefView> {
  return briefOf(
    await send(api, "POST", `${requirementPath(id)}/attachments`, { kind, id: attachmentId }),
    "attach that",
  );
}

export async function detach(api: BriefApi, id: string, kind: AttachmentKind, attachmentId: string): Promise<CaseBriefView> {
  return briefOf(
    await send(api, "DELETE", `${requirementPath(id)}/attachments/${kind}/${encodeURIComponent(attachmentId)}`),
    "detach that",
  );
}

export interface Candidate {
  id: string;
  label: string;
}

const ONE_LINE = 120;
function firstLine(text: string): string {
  const line = text.trim().split("\n")[0] ?? "";
  return line.length > ONE_LINE ? `${line.slice(0, ONE_LINE - 1).trimEnd()}…` : line;
}

/** What the Author may attach of one kind: each list is the Conduit's own, already limited to what
 * this person may read (their own saved patterns, the case's trends, the assessments they may see,
 * the cases they may open), so the picker offers nothing the attach would then refuse. */
export async function candidatesFor(api: BriefApi, kind: AttachmentKind): Promise<Candidate[]> {
  switch (kind) {
    case "trend":
      return (await listTrends(api)).map((t) => ({ id: t.id, label: t.title }));
    case "pattern":
      return (await listPatterns(api.apiBaseUrl, api.bearerToken, api.investigationId)).map((p) => ({
        id: p.pattern_id,
        label: p.name,
      }));
    case "assessment":
      return (await listJudgements(api.apiBaseUrl, api.bearerToken, api.investigationId)).map((j) => ({
        id: j.id,
        label: firstLine(j.statement),
      }));
    case "view":
      return (await listCases(api.apiBaseUrl, api.bearerToken))
        .filter((c) => c.id !== api.investigationId)
        .map((c) => ({ id: c.id, label: c.name || "Untitled view" }));
  }
}
