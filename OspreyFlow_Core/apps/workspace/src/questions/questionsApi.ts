// Questions to the model about a case's documents (ADR-098 decision 4): the four routes under
// `/v1/investigations/{id}/questions`. The Conduit decides what the model reads (the Documents in
// the case's view the analyst can see) and what the reader sees of the conversation; nothing here
// widens either.
import type { EmailCandidate } from "../inspector/linkEventsApi";

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
  /** Proposals whose words the model gave are not in the document it named: left out, counted. */
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

/** What a refused question says, in words: never a bare status. */
export async function askQuestion(
  apiBaseUrl: string,
  bearerToken: string,
  investigationId: string,
  question: string,
): Promise<QuestionAnswer> {
  const response = await send(questionsUrl(apiBaseUrl, investigationId), bearerToken, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
  if (response.ok) return (await response.json()) as QuestionAnswer;
  const body = await detailOf(response);
  if (response.status === 403) throw new Error("Asking needs Editor access to this case.");
  if (response.status === 413) {
    const count = new Intl.NumberFormat("en-GB");
    const wouldBe = typeof body.would_be === "number" ? count.format(body.would_be) : "more";
    const limit = typeof body.limit === "number" ? count.format(body.limit) : "the limit";
    throw new Error(
      `These documents come to ${wouldBe} characters, more than the model can read at once ` +
        `(${limit}). Remove some from the view and ask again.`,
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
