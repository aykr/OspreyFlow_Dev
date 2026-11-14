// Questions to the model about a case's documents (ADR-098 decision 4): the five routes under
// `/v1/investigations/{id}/questions`. The Conduit decides what the model reads (the Documents in
// the case's view the analyst can see) and what the reader sees of the conversation; nothing here
// widens either.
import type { EmailCandidate } from "../inspector/linkEventsApi";
import type { ReadSummary, UnusableEngine, WillRead } from "../../../../packages/schemas/generated";
import type { GraphCitation, SearchCitation } from "./graphFacts";
import { modelDeadline, unreachedWords } from "../models/modelDeadline";

export type { GraphCitation, SearchCitation };

/** What a question reads from (ADR-098 Amendments 7 and 9): *Selected items*, *Everything on the
 * graph*, or *Whole case* (the case's search, with the question's own words). */
export type ReadFrom = "selection" | "graph" | "case";

export type { ReadSummary, UnusableEngine, WillRead };

export interface Citation {
  document_id: string;
  title: string | null;
}

/** `services/api/questions.py`'s `QuestionAnswer`. */
export interface QuestionAnswer {
  id: string;
  author: string;
  /** Resolved at read time, never stored (ADR-106); absent, the id is shown. */
  author_name?: string | null;
  question: string;
  answer: string;
  citations: Citation[];
  candidates: EmailCandidate[];
  /** The `[G-n]` facts the answer cites, each with the ids it stands for (ADR-129); the Glass maps
   * a number to ids from here and nowhere else. Absent on an answer kept before graph facts. */
  graph_citations?: GraphCitation[];
  /** Proposals whose words are not in the document the model named, and citations of a fact it was
   * never given: left out, counted. */
  unplaced: number;
  created_at: string;
  /** ADR-135 decision 4: the engine that answered (`local` or a provider's name) and its model;
   * absent on an answer kept before engines were named. */
  engine?: string | null;
  model?: string | null;
  /** ADR-098 Amendment 7: what the question read; absent on an answer kept before it was. */
  read?: ReadSummary | null;
  /** ADR-129 Amendment 5: the `[S-n]` it cites, under *Whole case*. */
  search_citations?: SearchCitation[];
}

function questionsUrl(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/questions`;
}

/** `?view_id=` for a conversation kept with a case view (ADR-144 decision 4), or nothing. */
function inView(viewId: string | null | undefined): string {
  return viewId ? `?view_id=${encodeURIComponent(viewId)}` : "";
}

async function send(url: string, bearerToken: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(url, {
      ...init,
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    });
  } catch (thrown) {
    throw new Error(unreachedWords(thrown, "The server could not be reached."));
  }
}

async function detailOf(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export async function listQuestions(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  viewId?: string | null,
): Promise<QuestionAnswer[]> {
  const response = await send(`${questionsUrl(apiBaseUrl, investigationId)}${inView(viewId)}`, bearerToken);
  if (!response.ok) throw new Error(`The questions could not be loaded (${response.status}).`);
  return (await response.json()) as QuestionAnswer[];
}

/** What the question is asked about (ADR-129): the nodes and links selected on the canvas, which the
 * evidence brief is built from with one link around them (none selected: the whole view), and the
 * timeline window, when one is set. */
export interface AskScope {
  nodeIds: string[];
  linkIds: string[];
  window?: { validFrom: string; validTo: string | null } | null;
  /** ADR-135: the engine the analyst chose, from `GET /v1/models/engines`; absent, the role's
   * default. The Conduit still decides, and a refusal comes back in words (422 `engine_refused`). */
  engine?: string | null;
  /** ADR-144 decision 4: asked in a case view (*Ask the model about these*): the question reads only
   * what the view holds, and is kept with the view. */
  viewId?: string | null;
  /** ADR-098 Amendment 7: what to read from; absent, the selection when there is one, else the
   * graph. */
  readFrom?: ReadFrom | null;
}

/** *Will read*'s scope: under *Whole case* the question as typed so far goes with it, since its
 * words are what the case's search is asked (ADR-098 Amendment 9). */
export interface WillReadScope extends AskScope {
  question?: string | null;
}

function scopeBody(scope: AskScope): Record<string, unknown> {
  return {
    selected_node_ids: scope.nodeIds,
    selected_link_ids: scope.linkIds,
    ...(scope.window ? { window: { valid_from: scope.window.validFrom, valid_to: scope.window.validTo } } : {}),
    ...(scope.engine ? { engine: scope.engine } : {}),
    ...(scope.viewId ? { view_id: scope.viewId } : {}),
    ...(scope.readFrom ? { read_from: scope.readFrom } : {}),
  };
}

/** The typed `limit_exceeded` (rule 2), in words, with its three ways out. */
function limitWords(body: Record<string, unknown>): string {
  const count = new Intl.NumberFormat("en-GB");
  const figure = (value: unknown, otherwise: string) => (typeof value === "number" ? count.format(value) : otherwise);
  return (
    `This question comes to ${figure(body.would_be, "more")} characters, more than the model ` +
    `can read at once (${figure(body.cap, "the limit")}): the documents are ` +
    `${figure(body.documents_chars, "some")} and the graph facts ` +
    `${figure(body.evidence_brief_chars, "some")}. Nothing was sent. ` +
    "Narrow the selection, narrow the timeline window, or ask in a smaller view, then ask again."
  );
}

/** What will be read and who will answer, from the Conduit, before anything is sent. A refusal is
 * said in the Conduit's words (nothing to read, nothing found, a question too long to search, too
 * long to read). */
export async function willRead(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  scope: WillReadScope,
): Promise<WillRead> {
  const response = await send(`${questionsUrl(apiBaseUrl, investigationId)}/will-read`, bearerToken, {
    method: "POST",
    body: JSON.stringify({ ...scopeBody(scope), ...(scope.question ? { question: scope.question } : {}) }),
  });
  if (response.ok) return (await response.json()) as WillRead;
  const body = await detailOf(response);
  if (response.status === 403) throw new Error("Asking needs Editor access to this case.");
  if (response.status === 409 && body.error === "limit_exceeded") throw new Error(limitWords(body));
  if (typeof body.detail === "string") throw new Error(body.detail);
  throw new Error(`What will be read could not be worked out (${response.status}).`);
}

/** What a refused question says, in words: never a bare status. */
export async function askQuestion(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  question: string,
  scope: AskScope = { nodeIds: [], linkIds: [] },
): Promise<QuestionAnswer> {
  const response = await send(questionsUrl(apiBaseUrl, investigationId), bearerToken, {
    method: "POST",
    body: JSON.stringify({ question, ...scopeBody(scope) }),
    // ADR-135 Amendment 13 (a): the answer waits for a model, so it is never left endless.
    signal: modelDeadline(),
  });
  if (response.ok) return (await response.json()) as QuestionAnswer;
  const body = await detailOf(response);
  if (response.status === 403) throw new Error("Asking needs Editor access to this case.");
  if (response.status === 409 && body.error === "limit_exceeded") throw new Error(limitWords(body));
  if (typeof body.detail === "string") throw new Error(body.detail);
  throw new Error(`The question could not be asked (${response.status}). Try again.`);
}

export async function acceptProposal(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  candidateId: string,
  viewId?: string | null,
): Promise<{ node_id: string; delta: unknown }> {
  const response = await send(
    `${questionsUrl(apiBaseUrl, investigationId)}/candidates/${encodeURIComponent(candidateId)}/accept${inView(viewId)}`,
    bearerToken,
    { method: "POST", body: "{}" },
  );
  if (response.ok) return (await response.json()) as { node_id: string; delta: unknown };
  if (response.status === 409) throw new Error("The view is full: remove some nodes and try again.");
  if (response.status === 404) throw new Error("That document is no longer in your view.");
  throw new Error(`Accepting failed (${response.status}). Try again.`);
}

export async function rejectProposal(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  candidateId: string,
  viewId?: string | null,
): Promise<void> {
  const response = await send(
    `${questionsUrl(apiBaseUrl, investigationId)}/candidates/${encodeURIComponent(candidateId)}/reject${inView(viewId)}`,
    bearerToken,
    { method: "POST", body: "{}" },
  );
  if (!response.ok) throw new Error(`Rejecting failed (${response.status}). Try again.`);
}
