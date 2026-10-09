// The case's questions to the model (ADR-098 decision 4): the analyst asks, the model answers from
// the Documents in the case's view that the analyst can see, citing them, and what it proposes is
// listed with Accept and Reject — inferred until accepted, and accepted onto this case's canvas.
// The conversation is the case's, and shown to each reader as far as they may see it.
import { useEffect, useState } from "react";

import { candidateLabel, candidateSource, type EmailCandidate } from "../inspector/linkEventsApi";
import {
  acceptProposal,
  askQuestion,
  listQuestions,
  rejectProposal,
  type QuestionAnswer,
} from "./questionsApi";

export interface QuestionsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** An accepted proposal's change to the view. */
  onDelta: (delta: unknown) => void;
  onOpenDocument?: (documentId: string) => void;
}

const WHEN = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

export function QuestionsPanel({
  apiBaseUrl,
  bearerToken,
  investigationId,
  onDelta,
  onOpenDocument,
}: QuestionsPanelProps) {
  const [entries, setEntries] = useState<QuestionAnswer[] | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listQuestions(apiBaseUrl, bearerToken, investigationId)
      .then((found) => !cancelled && setEntries(found))
      .catch((err: unknown) => {
        if (cancelled) return;
        setEntries([]);
        setProblem(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId]);

  async function ask(): Promise<void> {
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setProblem(null);
    try {
      const answered = await askQuestion(apiBaseUrl, bearerToken, investigationId, text);
      setEntries((prev) => [...(prev ?? []), answered]);
      setQuestion("");
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setAsking(false);
    }
  }

  function settle(candidateId: string, status: EmailCandidate["status"]): void {
    setEntries((prev) =>
      (prev ?? []).map((entry) => ({
        ...entry,
        candidates: entry.candidates.map((c) => (c.id === candidateId ? { ...c, status } : c)),
      })),
    );
  }

  async function decide(candidate: EmailCandidate, accept: boolean): Promise<void> {
    setDeciding(candidate.id);
    setProblem(null);
    try {
      if (accept) {
        const result = await acceptProposal(apiBaseUrl, bearerToken, investigationId, candidate.id);
        onDelta(result.delta);
        settle(candidate.id, "accepted");
      } else {
        await rejectProposal(apiBaseUrl, bearerToken, investigationId, candidate.id);
        settle(candidate.id, "rejected");
      }
    } catch (err) {
      setProblem(err instanceof Error ? err.message : String(err));
    } finally {
      setDeciding(null);
    }
  }

  return (
    <section aria-label="Questions to the model" style={{ display: "grid", gap: "var(--sp-12)" }}>
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        The model reads the documents in this case that you can see, whole, and answers from them
        only. What it proposes is a suggestion until you accept it.
      </p>
      {entries === null && <p style={{ margin: 0 }}>Loading the questions…</p>}
      {entries !== null && entries.length === 0 && (
        <p style={{ color: "var(--text-tertiary)", margin: 0 }}>No questions asked in this case yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ol role="list" aria-label="Questions asked" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-16)" }}>
          {entries.map((entry) => (
            <li key={entry.id} style={{ display: "grid", gap: "var(--sp-8)" }}>
              <p style={{ margin: 0, fontWeight: 600 }}>{entry.question}</p>
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                {entry.author_name ?? entry.author} · {WHEN.format(new Date(entry.created_at))} UTC
              </p>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{entry.answer || "The model gave no answer."}</p>
              {entry.citations.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-4)", alignItems: "center" }}>
                  <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>Draws on</span>
                  {entry.citations.map((citation) => (
                    <button
                      key={citation.document_id}
                      type="button"
                      className="btn btn--quiet"
                      disabled={!onOpenDocument}
                      onClick={() => onOpenDocument?.(citation.document_id)}
                    >
                      {citation.title ?? citation.document_id}
                    </button>
                  ))}
                </div>
              )}
              {entry.candidates.length > 0 && (
                <ul role="list" aria-label="Proposed by the model" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
                  {entry.candidates.map((candidate) => (
                    <li key={candidate.id} style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)", alignItems: "center" }}>
                      <span className="value">
                        {candidateLabel(candidate)}
                        <span style={{ color: "var(--text-tertiary)" }}> · {candidateSource(candidate)}</span>
                      </span>
                      {candidate.status === "pending" ? (
                        <span style={{ display: "flex", gap: "var(--sp-4)" }}>
                          <button
                            type="button"
                            className="btn"
                            disabled={deciding !== null}
                            aria-label={`Accept ${candidateLabel(candidate)}`}
                            onClick={() => void decide(candidate, true)}
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            className="btn btn--quiet"
                            disabled={deciding !== null}
                            aria-label={`Reject ${candidateLabel(candidate)}`}
                            onClick={() => void decide(candidate, false)}
                          >
                            Reject
                          </button>
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                          {candidate.status === "accepted" ? "Accepted" : "Rejected"}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {entry.unplaced > 0 && (
                <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                  {entry.unplaced === 1
                    ? "1 proposal was left out: its words are not in the document the model named."
                    : `${entry.unplaced} proposals were left out: their words are not in the documents the model named.`}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask();
        }}
        style={{ display: "grid", gap: "var(--sp-8)" }}
      >
        <label htmlFor="questions-input" style={{ fontSize: "var(--fs-12)" }}>
          Your question
        </label>
        <textarea
          id="questions-input"
          className="input"
          rows={3}
          maxLength={2000}
          value={question}
          disabled={asking}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void ask();
            }
          }}
        />
        <div style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          <button type="submit" className="btn" disabled={asking || question.trim() === ""}>
            {asking ? "Asking…" : "Ask"}
          </button>
          {asking && (
            <span role="status" style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
              The model is reading the documents…
            </span>
          )}
        </div>
      </form>
      {problem && (
        <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
          {problem}
        </p>
      )}
    </section>
  );
}
