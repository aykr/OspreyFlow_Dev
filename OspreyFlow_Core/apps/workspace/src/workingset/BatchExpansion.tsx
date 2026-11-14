import { useEffect, useRef, useState } from "react";

import { type CaseViewOpened, openView } from "../views/viewsApi";
import {
  type BatchExpansionJob,
  type BatchExpansionRequest,
  readBatchExpansion,
  startBatchExpansion,
} from "./batchExpansionApi";
import type { LimitExceeded } from "./models";

const COUNT = new Intl.NumberFormat("en-GB");

export interface BatchExpansionProps {
  /** The expansion the cap refused, as the canvas handed it over. Held by the caller, so it is the
   * same object for the panel's whole life: a new one starts a new job. */
  request: BatchExpansionRequest;
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The job's result was opened as a view of the case: show it as the read-only lens (ADR-144). */
  onViewOpened: (opened: CaseViewOpened) => void;
  onClose: () => void;
  /** How often the job is asked where it is, in milliseconds (ADR-151: every 2 s). */
  pollMs?: number;
}

type Shown =
  | { phase: "starting" }
  | { phase: "watching"; words: string; trouble: string | null }
  | { phase: "opening"; words: string }
  | { phase: "opened"; words: string; name: string }
  | { phase: "stopped"; words: string; again: boolean };

function what(kind: "nodes" | "edges" | undefined): string {
  return kind === "edges" ? "links" : "nodes";
}

/** A refusal's words are the server's, shown as given; these stand in only if it sent none. */
function refusalWords(job: BatchExpansionJob): string {
  if (job.words) return job.words;
  const refusal = job.refusal;
  if (refusal && refusal.cap !== undefined && refusal.would_be !== undefined) {
    return `The batch job was refused: ${COUNT.format(refusal.would_be)} ${what(refusal.cap_kind)} against a limit of ${COUNT.format(refusal.cap)}. Nothing was saved.`;
  }
  return "The batch job was refused. Nothing was saved.";
}

/**
 * The third of the cap's three choices (spec/00 §4, ADR-151): the refused expansion run whole on the
 * server as a batch job, under the reader's own access, its result saved as a private view of the
 * case and opened as the lens when it finishes. Nothing joins the working set and nothing is cut to
 * fit. Every state is said in words — the server's own sentence for each stage, refusal and failure,
 * and the Glass's own for what it did with the result. Not modal: the reader may go on working on the
 * canvas while the job runs.
 */
export function BatchExpansion({
  request,
  apiBaseUrl,
  bearerToken,
  investigationId,
  onViewOpened,
  onClose,
  pollMs = 2000,
}: BatchExpansionProps) {
  const [shown, setShown] = useState<Shown>({ phase: "starting" });
  const [attempt, setAttempt] = useState(0);
  const onViewOpenedRef = useRef(onViewOpened);
  onViewOpenedRef.current = onViewOpened;
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function finish(job: BatchExpansionJob): Promise<void> {
      if (!job.view) {
        setShown({ phase: "stopped", again: false, words: `${job.words} The server did not say which view holds the result.`.trim() });
        return;
      }
      setShown({ phase: "opening", words: job.words });
      const result = await openView(apiBaseUrl, bearerToken, investigationId, job.view.id);
      if (!live) return;
      const name = job.view.name;
      if (result.ok) {
        setShown({ phase: "opened", words: job.words, name: result.opened.view.name });
        onViewOpenedRef.current(result.opened);
      } else if (result.kind === "limit_exceeded") {
        const wouldBe: LimitExceeded = result.wouldBe;
        setShown({
          phase: "stopped",
          again: false,
          words: `The batch job saved its result as the view “${name}”, but it holds more than the canvas can: ${COUNT.format(wouldBe.would_be)} ${what(wouldBe.cap_kind)} against a limit of ${COUNT.format(wouldBe.cap)}. Nothing was cut to fit; the view is kept in Views in this case.`,
        });
      } else if (result.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: `The batch job saved its result as the view “${name}”, but it could not be opened. It may have been deleted.`,
        });
      } else {
        setShown({ phase: "stopped", again: false, words: `The batch job saved its result as the view “${name}”, but it could not be opened: ${result.message}` });
      }
    }

    async function watch(jobId: string): Promise<void> {
      const read = await readBatchExpansion(apiBaseUrl, bearerToken, investigationId, jobId);
      if (!live) return;
      if (read.ok) {
        const job = read.job;
        if (job.state === "done") return finish(job);
        if (job.state === "refused") {
          setShown({ phase: "stopped", again: false, words: refusalWords(job) });
          return;
        }
        if (job.state === "failed") {
          setShown({ phase: "stopped", again: true, words: job.words || "The batch job failed on the server." });
          return;
        }
        setShown({ phase: "watching", words: job.words || "The batch job is under way.", trouble: null });
      } else if (read.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: "The batch job can no longer be found. It may have been cancelled, or the case closed or no longer shared with you.",
        });
        return;
      } else if (read.kind === "unknown") {
        setShown({ phase: "stopped", again: false, words: read.message });
        return;
      } else {
        const trouble = `${read.message} Still trying.`;
        setShown((current) => ({
          phase: "watching",
          words: current.phase === "watching" ? current.words : "The batch job is under way.",
          trouble,
        }));
      }
      timer = setTimeout(() => void watch(jobId), pollMs);
    }

    async function start(): Promise<void> {
      setShown({ phase: "starting" });
      const started = await startBatchExpansion(apiBaseUrl, bearerToken, investigationId, request);
      if (!live) return;
      if (started.ok) {
        const [id, words] = "job" in started ? [started.job.id, started.job.words] : [started.running.id, started.running.words];
        setShown({ phase: "watching", words: words || "The batch job is under way.", trouble: null });
        timer = setTimeout(() => void watch(id), pollMs);
        return;
      }
      if (started.kind === "forbidden") {
        setShown({
          phase: "stopped",
          again: false,
          words: "You cannot run a batch job in this case: it needs the Editor level, since its result is saved as a view of the case. No job was started.",
        });
      } else if (started.kind === "right_required") {
        setShown({
          phase: "stopped",
          again: false,
          words: "Your account does not hold the right to expand a case, so it cannot run a batch job. No job was started.",
        });
      } else if (started.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: "This case could not be opened. It may have been closed, or not shared with you. No job was started.",
        });
      } else {
        setShown({ phase: "stopped", again: true, words: `${started.message} No job was started.` });
      }
    }

    void start();
    return () => {
      live = false;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [apiBaseUrl, bearerToken, investigationId, request, pollMs, attempt]);

  return (
    <section className="batch-expansion" role="region" aria-labelledby="batch-expansion-title">
      <h2 id="batch-expansion-title" className="batch-expansion__title" tabIndex={-1} ref={headingRef}>
        Batch job: the whole expansion
      </h2>
      <p className="batch-expansion__figure">
        The canvas refused {COUNT.format(request.refused.would_be)} {what(request.refused.cap_kind)} against its limit of{" "}
        {COUNT.format(request.refused.cap)}. The server runs the whole expansion instead and saves the result as a view of
        this case, private to you; nothing is added to the canvas.
      </p>
      <div role="status" aria-live="polite" className="batch-expansion__status">
        {shown.phase === "starting" && "Starting the batch job."}
        {shown.phase === "watching" && shown.words}
        {shown.phase === "opening" && `${shown.words} Opening the view.`.trim()}
        {shown.phase === "opened" && `${shown.words} Its result is open as the view “${shown.name}”.`.trim()}
      </div>
      {shown.phase === "watching" && shown.trouble !== null && (
        <p className="batch-expansion__trouble">{shown.trouble}</p>
      )}
      {shown.phase === "stopped" && (
        <p className="batch-expansion__message" role="alert">
          {shown.words}
        </p>
      )}
      <div className="batch-expansion__actions">
        {shown.phase === "stopped" && shown.again && (
          <button type="button" className="btn btn--primary" onClick={() => setAttempt((n) => n + 1)}>
            Try the batch job again
          </button>
        )}
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </section>
  );
}
