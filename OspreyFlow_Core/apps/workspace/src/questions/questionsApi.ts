// Questions to the model about a case's documents (ADR-098 decision 4): the four routes under
// `/v1/investigations/{id}/questions`. The Conduit decides what the model reads (the Documents in
// the case's view the analyst can see) and what the reader sees of the conversation; nothing here
// widens either.
import type { EmailCandidate } from "../inspector/linkEventsApi";
import type { GraphCitation } from "./graphFacts";

export type { GraphCitation };

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
}

function questionsUrl(apiBaseUrl: string, investigationId: string): string {
  return `${apiBaseUrl}/v1/investigations/${encodeURIComponent(investigationId)}/questions`;
}

async function send(url: string, bearerToken: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(url, {
      ...init,
      headers: { Authorization: `Bearer ${bearerToken}`, "Content-Type": "application/json" },
    });
  } catch {
    throw new Error("The server could not be reached.");
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
): Promise<QuestionAnswer[]> {
  const response = await send(questionsUrl(apiBaseUrl, investigationId), bearerToken);
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
    body: JSON.stringify({
      question,
      selected_node_ids: scope.nodeIds,
      selected_link_ids: scope.linkIds,
      ...(scope.window
        ? { window: { valid_from: scope.window.validFrom, valid_to: scope.window.validTo } }
        : {}),
    }),
  });
  if (response.ok) return (await response.json()) as QuestionAnswer;
  const body = await detailOf(response);
  if (response.status === 403) throw new Error("Asking needs Editor access to this case.");
  if (response.status === 409 && body.error === "limit_exceeded") {
    const count = new Intl.NumberFormat("en-GB");
    const figure = (value: unknown, otherwise: string) =>
      typeof value === "number" ? count.format(value) : otherwise;
    throw new Error(
      `This question comes to ${figure(body.would_be, "more")} characters, more than the model ` +
        `can read at once (${figure(body.cap, "the limit")}): the documents are ` +
        `${figure(body.documents_chars, "some")} and the graph facts ` +
        `${figure(body.evidence_brief_chars, "some")}. Nothing was sent. ` +
        "Narrow the selection, narrow the timeline window, or branch the case, then ask again.",
    );
  }
  if (response.status === 422 && body.error === "no_documents") {
    throw new Error("This case holds no document you can see. Put documents on the canvas first.");
  }
  if (typeof body.detail === "string") throw new Error(body.detail);
  throw new Error(`The question could not be asked (${response.status}). Try again.`);
}

export async function acceptProposal(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  candidateId: string,
): Promise<{ node_id: string; delta: unknown }> {
  const response = await send(
    `${questionsUrl(apiBaseUrl, investigationId)}/candidates/${encodeURIComponent(candidateId)}/accept`,
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
): Promise<void> {
  const response = await send(
    `${questionsUrl(apiBaseUrl, investigationId)}/candidates/${encodeURIComponent(candidateId)}/reject`,
    bearerToken,
    { method: "POST", body: "{}" },
  );
  if (!response.ok) throw new Error(`Rejecting failed (${response.status}). Try again.`);
}
