// A Document opened full screen to read (ADR-092 decision 4): an overlay over the whole work area,
// canvas and panels, with the title, for an email its sender, recipient and date, and the full text
// with the entities already accepted marked in place. *Quick scan* and *Deep read (model)* for an
// email (ADR-098 Amendment 3); Close or
// Escape returns to the view exactly as it was, since nothing behind the overlay is touched.
import { useCallback, useEffect, useRef, useState } from "react";

import { HighlightLegend, HighlightedMessage } from "../dossier/HighlightedMessage";
import { pendingSpansIn, type PendingSpan } from "./pendingSpans";
import {
  acceptEmailCandidate,
  candidateLabel,
  candidateSource,
  rejectEmailCandidate,
  withNewFindings,
  type ExtractUsing,
  extractEmail,
  type EmailCandidate,
} from "../inspector/linkEventsApi";
import type { OntologyRegistry } from "../ontology/schema";
import { placeOf, selectionIn, type SelectedWords } from "./designation";
import {
  acceptDocumentFinding,
  designateInDocument,
  extractDocument,
  rejectDocumentFinding,
  fetchDocumentFile,
  fetchDocumentReader,
  type DocumentReaderView,
} from "./readerApi";

/** What words can be marked as by hand (the server's `DESIGNATABLE_TYPES`). */
const MARK_TYPES = ["Person", "Organisation", "Location", "Endpoint"] as const;

export interface DocumentReaderProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  documentId: string;
  ontology: OntologyRegistry;
  /** The name an end of the email is drawn with on the canvas, or its id. */
  labelOf: (nodeId: string) => string;
  onClose: () => void;
  /** What to show if the Document is not there yet: an email opened from the Inspector before
   * anything wrote it as one (ADR-092 Amendment 3). Read again after an extraction, it is. */
  fallback?: DocumentReaderView;
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
  | { state: "running"; listed?: EmailCandidate[] }
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
  fallback,
}: DocumentReaderProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [findings, setFindings] = useState<Findings>({ state: "idle" });
  const [accepting, setAccepting] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // ADR-098 decision 5: words marked as an entity by the analyst.
  const textRef = useRef<HTMLDivElement>(null);
  const [words, setWords] = useState("");
  const [selectedWords, setSelectedWords] = useState<SelectedWords | null>(null);
  const [markType, setMarkType] = useState<(typeof MARK_TYPES)[number]>("Person");
  const [marking, setMarking] = useState<{ busy: boolean; message: string | null }>({ busy: false, message: null });
  // ADR-094: an image's or a video's file, as a URL the element can show.
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const heldMedia =
    load.state === "ready" &&
    load.view.has_file === true &&
    (load.view.media_kind === "image" || load.view.media_kind === "video");

  useEffect(() => {
    if (!heldMedia) return;
    let url: string | null = null;
    let cancelled = false;
    fetchDocumentFile(apiBaseUrl, bearerToken, investigationId, documentId)
      .then((made) => {
        url = made;
        if (!cancelled) setFileUrl(made);
      })
      .catch(() => setFileUrl(null));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [heldMedia, apiBaseUrl, bearerToken, investigationId, documentId]);

  const read = useCallback(async () => {
    try {
      const view = await fetchDocumentReader(apiBaseUrl, bearerToken, investigationId, documentId);
      setLoad({ state: "ready", view });
    } catch (err) {
      if (fallback) setLoad({ state: "ready", view: fallback });
      else setLoad({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    }
  }, [apiBaseUrl, bearerToken, investigationId, documentId, fallback]);

  useEffect(() => {
    void read();
  }, [read]);

  useEffect(() => {
    closeRef.current?.focus();
  }, [load.state]);

  // ADR-098: the fast recogniser first (Quick scan), the language model on request (Deep read);
  // a second pass adds its findings to those already listed.
  async function extract(view: DocumentReaderView, using: ExtractUsing = "recogniser") {
    const listed = findings.state === "ready" ? findings.candidates : [];
    setFindings({ state: "running", listed });
    try {
      if (view.edge_id && view.event_id) {
        const result = await extractEmail(apiBaseUrl, bearerToken, investigationId, view.edge_id, view.event_id, using);
        onDelta?.(result.delta);
        setFindings({ state: "ready", candidates: withNewFindings(listed, result.candidates) });
        return;
      }
      // A held Document (ADR-094): by its kind, through the Document routes.
      const result = await extractDocument(apiBaseUrl, bearerToken, investigationId, view.document_id, using);
      setFindings({ state: "ready", candidates: withNewFindings(listed, result.candidates as EmailCandidate[]) });
      await read(); // the text it was extracted from (a description, a transcript) is shown
    } catch (err) {
      setFindings({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    }
  }

  async function accept(view: DocumentReaderView, candidate: EmailCandidate) {
    if (findings.state !== "ready") return;
    setAccepting(candidate.id);
    try {
      const result =
        view.edge_id && view.event_id
          ? await acceptEmailCandidate(
              apiBaseUrl,
              bearerToken,
              investigationId,
              view.edge_id,
              view.event_id,
              candidate.id,
            )
          : await acceptDocumentFinding(apiBaseUrl, bearerToken, investigationId, view.document_id, candidate.id);
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

  // Owner, 6 October 2026: a finding can be rejected beside Accept; nothing is written.
  async function reject(view: DocumentReaderView, candidate: EmailCandidate) {
    if (findings.state !== "ready") return;
    setAccepting(candidate.id);
    try {
      if (view.edge_id && view.event_id) {
        await rejectEmailCandidate(apiBaseUrl, bearerToken, investigationId, view.edge_id, view.event_id, candidate.id);
      } else {
        await rejectDocumentFinding(apiBaseUrl, bearerToken, investigationId, view.document_id, candidate.id);
      }
      setFindings({
        state: "ready",
        candidates: findings.candidates.map((c) => (c.id === candidate.id ? { ...c, status: "rejected" } : c)),
      });
    } catch (err) {
      setFindings({ state: "failed", message: err instanceof Error ? err.message : String(err) });
    } finally {
      setAccepting(null);
    }
  }

  async function mark(view: DocumentReaderView) {
    const place = placeOf(view.text, words, selectedWords);
    if (!place) {
      setMarking({ busy: false, message: "Those words are not in this document." });
      return;
    }
    const text = view.text.slice(place.start, place.end);
    setMarking({ busy: true, message: null });
    try {
      const result = await designateInDocument(apiBaseUrl, bearerToken, investigationId, view.document_id, {
        entity_type: markType,
        text,
        ...place,
      });
      onDelta?.(result.delta);
      setMarking({ busy: false, message: `Marked “${text}” as ${markType === "Organisation" ? "an" : "a"} ${markType}.` });
      setWords("");
      setSelectedWords(null);
    } catch (err) {
      setMarking({ busy: false, message: err instanceof Error ? err.message : String(err) });
    }
  }

  const title = load.state === "ready" ? load.view.title ?? "(no title)" : "Document";
  // What is listed: the findings, and while a second pass runs, those it will add to.
  const shownFindings =
    findings.state === "ready" ? findings.candidates : findings.state === "running" ? findings.listed ?? [] : [];

  // ADR-098 Amendment 1: a pending finding is shown where it sits in the text. Located against
  // the shown text with each finding's own excerpt hash, so nothing is marked at a wrong place.
  const [pendingSpans, setPendingSpans] = useState<PendingSpan[]>([]);
  useEffect(() => {
    if (load.state !== "ready" || !load.view.text) {
      setPendingSpans([]);
      return;
    }
    const listed =
      findings.state === "ready" ? findings.candidates : findings.state === "running" ? findings.listed ?? [] : [];
    let cancelled = false;
    void pendingSpansIn(load.view.text, listed).then((spans) => {
      if (!cancelled) setPendingSpans(spans);
    });
    return () => {
      cancelled = true;
    };
  }, [load, findings]);

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

            {heldMedia && fileUrl && load.view.media_kind === "image" && (
              <img
                src={fileUrl}
                alt={title}
                style={{ maxWidth: "100%", maxHeight: "60vh", objectFit: "contain", alignSelf: "start" }}
              />
            )}
            {heldMedia && fileUrl && load.view.media_kind === "video" && (
              <video src={fileUrl} controls aria-label={title} style={{ maxWidth: "100%", maxHeight: "60vh" }} />
            )}
            <div
              ref={textRef}
              style={{ fontSize: "var(--fs-16)", lineHeight: 1.6, color: "var(--text-primary)", whiteSpace: "pre-wrap" }}
              onMouseUp={() => {
                // Words selected in the text fill the marking form (ADR-098 decision 5).
                const chosen = textRef.current ? selectionIn(textRef.current) : null;
                if (chosen) {
                  setSelectedWords(chosen);
                  setWords(chosen.text);
                }
              }}
            >
              {load.view.text ? (
                <HighlightedMessage
                  document={{ document_id: load.view.document_id, text: load.view.text, spans: load.view.spans }}
                  ontology={ontology}
                  pending={pendingSpans}
                />
              ) : (
                <p style={{ color: "var(--text-tertiary)", margin: 0 }}>
                  {heldMedia
                    ? "No text yet: Quick scan describes it and reads it first."
                    : "This document has no text to show."}
                </p>
              )}
            </div>
            {load.view.text && (
              <HighlightLegend
                types={[
                  ...new Set([
                    ...load.view.spans.map((s) => s.entity_type),
                    ...pendingSpans.map((p) => p.entity_type),
                  ]),
                ].sort()}
                pendingPresent={pendingSpans.length > 0}
                ontology={ontology}
              />
            )}
            {load.view.truncated && (
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                This is the first 4,000 characters; the message runs on.
              </p>
            )}
            {load.view.text && (
              <form
                className="reader-mark"
                aria-label="Mark an entity"
                onSubmit={(event) => {
                  event.preventDefault();
                  void mark(load.view);
                }}
              >
                <span className="reader-mark__title">Mark an entity</span>
                <input
                  type="text"
                  aria-label="Words to mark"
                  placeholder="Select words above, or type them"
                  value={words}
                  onChange={(event) => {
                    setWords(event.target.value);
                    setMarking({ busy: false, message: null });
                  }}
                />
                <select aria-label="Mark as" value={markType} onChange={(event) => setMarkType(event.target.value as (typeof MARK_TYPES)[number])}>
                  {MARK_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <button type="submit" className="btn" disabled={marking.busy || words.trim() === ""}>
                  Mark
                </button>
                {marking.message && (
                  <span role="status" className="reader-mark__message">
                    {marking.message}
                  </span>
                )}
              </form>
            )}

            {((load.view.edge_id && load.view.event_id) || load.view.has_file) && (
              <section aria-label="Entities in this email" style={{ display: "grid", gap: "var(--sp-8)" }}>
                {/* ADR-098 Amendment 1 (owner, 9 October 2026): the two passes are equal buttons,
                    always offered, each saying what it does — never one that disappears beside
                    one styled like plain text. */}
                <span style={{ display: "flex", gap: "var(--sp-16)", flexWrap: "wrap", alignItems: "start" }}>
                  <span style={{ display: "grid", gap: "var(--sp-4)", justifyItems: "start" }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={findings.state === "running"}
                      onClick={() => void extract(load.view, "recogniser")}
                    >
                      Quick scan
                    </button>
                    <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                      Names, emails and numbers, in seconds
                    </span>
                  </span>
                  <span style={{ display: "grid", gap: "var(--sp-4)", justifyItems: "start" }}>
                    <button
                      type="button"
                      className="btn"
                      disabled={findings.state === "running"}
                      onClick={() => void extract(load.view, "model")}
                    >
                      Deep read (model)
                    </button>
                    <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                      A slower, deeper read; findings are added
                    </span>
                  </span>
                </span>
                {findings.state === "running" && (
                  <p role="status" style={{ color: "var(--text-tertiary)", margin: 0 }}>
                    Extracting…
                  </p>
                )}
                {findings.state === "failed" && (
                  <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
                    {findings.message}
                  </p>
                )}
                {findings.state === "ready" && findings.candidates.length === 0 && (
                  <p style={{ color: "var(--text-tertiary)", margin: 0 }}>No entities were found in this document.</p>
                )}
                {shownFindings.length > 0 && (
                  <ul role="list" aria-label="Entities found" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
                    {shownFindings.map((candidate) => (
                      <li key={candidate.id} style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)", alignItems: "center" }}>
                        <span className="value">
                          {candidateLabel(candidate)}
                          <span style={{ color: "var(--text-tertiary)" }}> · {candidateSource(candidate)}</span>
                        </span>
                        {candidate.status === "accepted" || candidate.status === "rejected" ? (
                          <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                            {candidate.status === "accepted" ? "Accepted" : "Rejected"}
                          </span>
                        ) : (
                          <span style={{ display: "flex", gap: "var(--sp-4)" }}>
                            <button
                              type="button"
                              className="btn"
                              disabled={accepting !== null || findings.state === "running"}
                              aria-label={`Accept ${candidateLabel(candidate)}`}
                              onClick={() => void accept(load.view, candidate)}
                            >
                              Accept
                            </button>
                            <button
                              type="button"
                              className="btn btn--quiet"
                              disabled={accepting !== null || findings.state === "running"}
                              aria-label={`Reject ${candidateLabel(candidate)}`}
                              onClick={() => void reject(load.view, candidate)}
                            >
                              Reject
                            </button>
                          </span>
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
