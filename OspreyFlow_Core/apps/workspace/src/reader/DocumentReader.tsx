// A Document opened full screen to read (ADR-092 decision 4): an overlay over the whole work area,
// canvas and panels, with the title, for an email its sender, recipient and date, and the full text
// with the entities already accepted marked in place. *Extract entities* for an email; Close or
// Escape returns to the view exactly as it was, since nothing behind the overlay is touched.
import { useCallback, useEffect, useRef, useState } from "react";

import { HighlightedMessage } from "../dossier/HighlightedMessage";
import {
  acceptEmailCandidate,
  candidateLabel,
  extractEmail,
  type EmailCandidate,
} from "../inspector/linkEventsApi";
import type { OntologyRegistry } from "../ontology/schema";
import { fetchDocumentReader, type DocumentReaderView } from "./readerApi";

export interface DocumentReaderProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  documentId: string;
  ontology: OntologyRegistry;
  /** The name an end of the email is drawn with on the canvas, or its id. */
  labelOf: (nodeId: string) => string;
  onClose: () => void;
  /** What the working set gained from an extraction or an acceptance. */
  onDelta?: (delta: unknown) => void;
}

const SENT = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "UTC",
});

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "ready"; view: DocumentReaderView };

type Findings =
  | { state: "idle" }
  | { state: "running" }
  | { state: "failed"; message: string }
  | { state: "ready"; candidates: EmailCandidate[] };

export function DocumentReader({
  apiBaseUrl,
  bearerToken,
  investigationId,
  documentId,
  ontology,
  labelOf,
  onClose,
  onDelta,
}: DocumentReaderProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [findings, setFindings] = useState<Findings>({ state: "idle" });
  const [accepting, setAccepting] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  const read = useCallback(async () => {
    try {
      const view = await fetchDocumentReader(apiBaseUrl, bearerToken, investigationId, documentId);
      setLoad({ state: "ready", view });
    } catch (err) {
      setLoad({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    }
  }, [apiBaseUrl, bearerToken, investigationId, documentId]);

  useEffect(() => {
    void read();
  }, [read]);

  useEffect(() => {
    closeRef.current?.focus();
  }, [load.state]);

  async function extract(view: DocumentReaderView) {
    if (!view.edge_id || !view.event_id) return;
    setFindings({ state: "running" });
    try {
      const result = await extractEmail(apiBaseUrl, bearerToken, investigationId, view.edge_id, view.event_id);
      onDelta?.(result.delta);
      setFindings({ state: "ready", candidates: result.candidates });
    } catch (err) {
      setFindings({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    }
  }

  async function accept(view: DocumentReaderView, candidate: EmailCandidate) {
    if (!view.edge_id || !view.event_id || findings.state !== "ready") return;
    setAccepting(candidate.id);
    try {
      const result = await acceptEmailCandidate(
        apiBaseUrl,
        bearerToken,
        investigationId,
        view.edge_id,
        view.event_id,
        candidate.id,
      );
      onDelta?.(result.delta);
      setFindings({
        state: "ready",
        candidates: findings.candidates.map((c) => (c.id === candidate.id ? { ...c, status: "accepted" } : c)),
      });
      await read(); // an accepted finding is marked in the text
    } catch (err) {
      setFindings({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    } finally {
      setAccepting(null);
    }
  }

  const title = load.state === "ready" ? load.view.title ?? "(no title)" : "Document";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Reading: ${title}`}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onClose();
        }
      }}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 50,
        background: "var(--surface-app)",
        overflow: "auto",
        padding: "var(--sp-24) var(--sp-32)",
      }}
    >
      <div style={{ maxWidth: "72ch", margin: "0 auto", display: "grid", gap: "var(--sp-16)" }}>
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "var(--sp-16)" }}>
          <h2 style={{ margin: 0, fontSize: "var(--fs-19)", color: "var(--text-primary)" }}>{title}</h2>
          <button ref={closeRef} type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </header>

        {load.state === "loading" && <p style={{ color: "var(--text-tertiary)", margin: 0 }}>Opening…</p>}
        {load.state === "failed" && (
          <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
            {load.message}
          </p>
        )}
        {load.state === "ready" && (
          <>
            {(load.view.sender_id || load.view.sent_at) && (
              <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "var(--sp-4) var(--sp-16)" }}>
                {load.view.sender_id && (
                  <>
                    <dt style={{ color: "var(--text-secondary)" }}>From</dt>
                    <dd className="value" style={{ margin: 0 }}>{labelOf(load.view.sender_id)}</dd>
                  </>
                )}
                {load.view.recipient_id && (
                  <>
                    <dt style={{ color: "var(--text-secondary)" }}>To</dt>
                    <dd className="value" style={{ margin: 0 }}>{labelOf(load.view.recipient_id)}</dd>
                  </>
                )}
                {load.view.sent_at && (
                  <>
                    <dt style={{ color: "var(--text-secondary)" }}>Sent</dt>
                    <dd className="value" style={{ margin: 0 }}>{SENT.format(new Date(load.view.sent_at))}</dd>
                  </>
                )}
              </dl>
            )}

            <div style={{ fontSize: "var(--fs-16)", lineHeight: 1.6, color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>
              {load.view.text ? (
                <HighlightedMessage
                  document={{ document_id: load.view.document_id, text: load.view.text, spans: load.view.spans }}
                  ontology={ontology}
                />
              ) : (
                <p style={{ color: "var(--text-tertiary)", margin: 0 }}>This document has no text to show.</p>
              )}
            </div>
            {load.view.truncated && (
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                This is the first 4,000 characters; the message runs on.
              </p>
            )}

            {load.view.edge_id && load.view.event_id && (
              <section aria-label="Entities in this email" style={{ display: "grid", gap: "var(--sp-8)" }}>
                {findings.state !== "ready" && (
                  <button
                    type="button"
                    className="btn"
                    disabled={findings.state === "running"}
                    onClick={() => void extract(load.view)}
                    style={{ justifySelf: "start" }}
                  >
                    {findings.state === "running" ? "Extracting…" : "Extract entities"}
                  </button>
                )}
                {findings.state === "failed" && (
                  <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
                    {findings.message}
                  </p>
                )}
                {findings.state === "ready" && findings.candidates.length === 0 && (
                  <p style={{ color: "var(--text-tertiary)", margin: 0 }}>The model found no entities in this email.</p>
                )}
                {findings.state === "ready" && findings.candidates.length > 0 && (
                  <ul role="list" aria-label="Entities found" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
                    {findings.candidates.map((candidate) => (
                      <li key={candidate.id} style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)", alignItems: "center" }}>
                        <span className="value">
                          {candidateLabel(candidate)}
                          <span style={{ color: "var(--text-tertiary)" }}> · {Math.round(candidate.confidence * 100)}%</span>
                        </span>
                        {candidate.status === "accepted" ? (
                          <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>Accepted</span>
                        ) : (
                          <button
                            type="button"
                            className="btn"
                            disabled={accepting !== null}
                            aria-label={`Accept ${candidateLabel(candidate)}`}
                            onClick={() => void accept(load.view, candidate)}
                          >
                            Accept
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
