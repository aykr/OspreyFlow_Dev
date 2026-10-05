// The Inspector's **Emails** (or **Events**) section for a selected link (ADR-089): every event the
// link stands for, newest first, fifty at a time, and one of them opened to read. For an Enron link
// each event is one email, with its subject and an excerpt of up to 4,000 characters; an excerpt
// that was cut says so. Reached from the link menu's *Show emails (n)*; the list and the opened
// email are reachable by keyboard (`keyboard/link-events.spec.ts`).
import { useEffect, useRef, useState } from "react";

import type { EventRecord } from "../../../../packages/schemas/generated";
import {
  EVENTS_PAGE_SIZE,
  LinkEventsError,
  acceptEmailCandidate,
  candidateLabel,
  extractEmail,
  fetchLinkEvents,
  type EmailCandidate,
  type LinkEventPage,
} from "./linkEventsApi";
import { emailDocumentId, type DocumentReaderView } from "../reader/readerApi";

export interface LinkEventsProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  edgeId: string;
  /** "emails" between two addresses, or "events" for any other link. */
  noun: "emails" | "events";
  /** How the two ends read, for "From" and "To". */
  sourceLabel: string;
  targetLabel: string;
  /** Each time this counts up, the section opens and takes focus (the link menu's own hand-over). */
  focusSignal?: number;
  /** Told of what the working set gained (the email's Document node, an accepted entity), so the
   * canvas shows it at once (ADR-089 step 3). Omitted, extraction is not offered. */
  onDelta?: (delta: unknown) => void;
  /** ADR-092 Amendment 3: open the email in the full-screen reader. Left out, not offered. */
  onReadFullScreen?: (view: DocumentReaderView) => void;
}

type Load =
  | { state: "loading" }
  | { state: "ready"; page: LinkEventPage; events: EventRecord[] }
  | { state: "refused"; message: string };

function when(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function subjectOf(event: EventRecord): string {
  const subject = event.properties?.subject;
  return typeof subject === "string" && subject.trim() !== "" ? subject : "(no subject)";
}

function excerptOf(event: EventRecord): string {
  const text = event.properties?.excerpt;
  return typeof text === "string" ? text : "";
}

function wasTruncated(event: EventRecord): boolean {
  return event.properties?.truncated === true;
}

/** The reader's view of an email still to be written as a Document (ADR-092 Amendment 3). */
export function readerViewOf(event: EventRecord): DocumentReaderView {
  const inbound = event.direction === "inbound";
  return {
    document_id: emailDocumentId(event.event_id),
    title: subjectOf(event),
    text: excerptOf(event),
    truncated: wasTruncated(event),
    spans: [],
    sent_at: event.occurred_at,
    sender_id: inbound ? event.target_id : event.source_id,
    recipient_id: inbound ? event.source_id : event.target_id,
    edge_id: event.edge_id,
    event_id: event.event_id,
  };
}

export function LinkEvents({
  apiBaseUrl,
  bearerToken,
  investigationId,
  edgeId,
  noun,
  sourceLabel,
  targetLabel,
  focusSignal = 0,
  onDelta,
  onReadFullScreen,
}: LinkEventsProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [open, setOpen] = useState<EventRecord | null>(null);
  const [more, setMore] = useState(false);
  // ADR-089 step 3: the model's findings for the open email, pending until accepted.
  const [findings, setFindings] = useState<
    | { state: "idle" }
    | { state: "running" }
    | { state: "ready"; candidates: EmailCandidate[] }
    | { state: "failed"; message: string }
  >({ state: "idle" });
  const [accepting, setAccepting] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  // Opening an email removes the row that had focus, so focus moves into the email (its Back
  // button); Back returns it to the section's heading, so a keyboard user is never left on the body.
  useEffect(() => {
    if (open !== null) backRef.current?.focus();
  }, [open]);
  const closeEmail = () => {
    setOpen(null);
    setFindings({ state: "idle" });
    setProblem(null);
    requestAnimationFrame(() => headingRef.current?.focus());
  };

  const extract = async () => {
    if (open === null || findings.state === "running") return;
    setFindings({ state: "running" });
    setProblem(null);
    try {
      const result = await extractEmail(apiBaseUrl, bearerToken, investigationId, edgeId, open.event_id);
      onDelta?.(result.delta);
      setFindings({ state: "ready", candidates: result.candidates });
    } catch (error) {
      setFindings({
        state: "failed",
        message: error instanceof Error ? error.message : "The extraction could not be run.",
      });
    }
  };

  const accept = async (candidate: EmailCandidate) => {
    if (open === null || accepting !== null) return;
    setAccepting(candidate.id);
    setProblem(null);
    try {
      const result = await acceptEmailCandidate(
        apiBaseUrl,
        bearerToken,
        investigationId,
        edgeId,
        open.event_id,
        candidate.id,
      );
      onDelta?.(result.delta);
      setFindings((current) =>
        current.state === "ready"
          ? {
              state: "ready",
              candidates: current.candidates.map((c) =>
                c.id === candidate.id ? { ...c, status: "accepted", node_id: result.node_id } : c,
              ),
            }
          : current,
      );
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The finding could not be accepted.");
    } finally {
      setAccepting(null);
    }
  };
  const Noun = noun === "emails" ? "Emails" : "Events";

  useEffect(() => {
    let current = true;
    setLoad({ state: "loading" });
    setOpen(null);
    fetchLinkEvents(apiBaseUrl, bearerToken, investigationId, edgeId).then(
      (page) => {
        if (current) setLoad({ state: "ready", page, events: page.events });
      },
      (error: unknown) => {
        if (!current) return;
        setLoad({
          state: "refused",
          message:
            error instanceof LinkEventsError && error.kind === "link_not_found"
              ? `This link is not in your view, so its ${noun} cannot be shown.`
              : `The ${noun} could not be loaded. Select the link again to retry.`,
        });
      },
    );
    return () => {
      current = false;
    };
  }, [apiBaseUrl, bearerToken, investigationId, edgeId, noun]);

  useEffect(() => {
    if (focusSignal > 0) headingRef.current?.focus();
  }, [focusSignal]);

  const showMore = async () => {
    if (load.state !== "ready" || more) return;
    setMore(true);
    try {
      const next = await fetchLinkEvents(
        apiBaseUrl,
        bearerToken,
        investigationId,
        edgeId,
        load.events.length,
        EVENTS_PAGE_SIZE,
      );
      setLoad({ state: "ready", page: next, events: [...load.events, ...next.events] });
    } finally {
      setMore(false);
    }
  };

  return (
    <section aria-label={Noun} style={{ marginTop: "var(--sp-16)" }}>
      <h3
        ref={headingRef}
        tabIndex={-1}
        style={{ margin: 0, fontSize: "var(--fs-13)", color: "var(--text-secondary)", outline: "none" }}
      >
        {Noun}
        {load.state === "ready" ? ` (${load.page.total})` : ""}
      </h3>
      {load.state === "loading" && <p style={{ color: "var(--text-tertiary)" }}>Loading {noun}…</p>}
      {load.state === "refused" && (
        <p role="alert" style={{ color: "var(--text-secondary)" }}>
          {load.message}
        </p>
      )}
      {load.state === "ready" && load.page.total === 0 && (
        <p style={{ color: "var(--text-tertiary)" }}>This link has no dated {noun} behind it.</p>
      )}
      {load.state === "ready" && open === null && load.events.length > 0 && (
        <>
          <ul role="list" aria-label={Noun} style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
            {load.events.map((event) => (
              <li key={event.event_id}>
                <button
                  type="button"
                  className="metrics-panel__row"
                  style={{ width: "100%", display: "grid", gap: 2, textAlign: "left" }}
                  onClick={() => setOpen(event)}
                >
                  <span style={{ display: "flex", justifyContent: "space-between", gap: "var(--sp-8)" }}>
                    <span className="value">{subjectOf(event)}</span>
                    <span style={{ color: "var(--text-tertiary)", whiteSpace: "nowrap" }}>{when(event.occurred_at)}</span>
                  </span>
                  <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                    {event.direction === "inbound" ? `${targetLabel} → ${sourceLabel}` : `${sourceLabel} → ${targetLabel}`}
                    {excerptOf(event) ? ` · ${excerptOf(event).slice(0, 80)}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {load.events.length < load.page.total && (
            <button type="button" className="btn" disabled={more} onClick={() => void showMore()} style={{ marginTop: "var(--sp-8)" }}>
              Show more ({load.page.total - load.events.length} left)
            </button>
          )}
        </>
      )}
      {load.state === "ready" && open !== null && (
        <article aria-label={`${noun === "emails" ? "Email" : "Event"}: ${subjectOf(open)}`} style={{ display: "grid", gap: "var(--sp-8)" }}>
          <span style={{ display: "flex", gap: "var(--sp-8)" }}>
            <button ref={backRef} type="button" className="btn" onClick={closeEmail}>
              Back to the list
            </button>
            {onReadFullScreen && (
              <button type="button" className="btn" onClick={() => onReadFullScreen(readerViewOf(open))}>
                Read full screen
              </button>
            )}
          </span>
          <dl style={{ margin: 0 }}>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>Subject</dt>
              <dd className="value">{subjectOf(open)}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>From</dt>
              <dd className="value">{open.direction === "inbound" ? targetLabel : sourceLabel}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>To</dt>
              <dd className="value">{open.direction === "inbound" ? sourceLabel : targetLabel}</dd>
            </div>
            <div>
              <dt style={{ color: "var(--text-secondary)" }}>Sent</dt>
              <dd className="value">{when(open.occurred_at)}</dd>
            </div>
          </dl>
          <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{excerptOf(open) || "(no text)"}</p>
          {wasTruncated(open) && (
            <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
              This is the first 4,000 characters; the message runs on.
            </p>
          )}
          {onDelta && (
            <section aria-label="Entities in this email" style={{ display: "grid", gap: "var(--sp-8)" }}>
              {findings.state !== "ready" && (
                <button
                  type="button"
                  className="btn"
                  disabled={findings.state === "running"}
                  onClick={() => void extract()}
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
                <>
                  <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                    {findings.candidates.length} found. Each is a suggestion until you accept it; an accepted
                    entity joins the canvas as inferred, linked to this email, and is confirmed from the
                    Inspector as any inferred node is.
                  </p>
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
                            onClick={() => void accept(candidate)}
                          >
                            Accept
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {problem && (
                <p role="alert" style={{ color: "var(--text-secondary)", margin: 0 }}>
                  {problem}
                </p>
              )}
            </section>
          )}
        </article>
      )}
    </section>
  );
}
