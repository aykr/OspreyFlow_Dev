import { useEffect, useRef, useState } from "react";

import { type CaseViewOpened, openView } from "../views/viewsApi";
import {
  type BatchExpansionRequest,
  type JobState,
  readBatchExpansion,
  startBatchExpansion,
} from "./batchExpansionApi";
import type { LimitExceeded } from "./models";

const COUNT = new Intl.NumberFormat("en-GB");

export interface BatchExpansionProps {
  /** The expansion the cap refused, as the canvas handed it over. */
  request: BatchExpansionRequest;
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The job's result was opened as a view of the case: show it as the lens (ADR-144). */
  onViewOpened: (opened: CaseViewOpened) => void;
  onClose: () => void;
  /** How often the job is asked where it is, in milliseconds. */
  pollMs?: number;
}

type Shown =
  | { phase: "starting" }
  | { phase: "watching"; job: JobState; trouble: string | null }
  | { phase: "opening" }
  | { phase: "opened"; name: string }
  | { phase: "stopped"; words: string; again: boolean };

function what(wouldBe: LimitExceeded): string {
  return wouldBe.cap_kind === "nodes" ? "nodes" : "links";
}

/** The words for a job that is still going. */
function progressWords(job: JobState): string {
  if (job.state === "queued") return "The batch job is waiting for the server to start it.";
  if (job.state === "running") {
    if (job.done !== null && job.total !== null && job.total > 0) {
      const percent = Math.min(100, Math.floor((job.done / job.total) * 100));
      return `Running the batch job: ${percent}% done (${COUNT.format(job.done)} of ${COUNT.format(job.total)}).`;
    }
    return "Running the batch job.";
  }
  return "Waiting for the batch job.";
}

/**
 * The third of the cap's three choices (spec/00 §4, ADR-151): the refused expansion run whole on the
 * server as a batch job, under the reader's own access, its result saved as a view of the case and
 * opened as the lens when it finishes. Nothing is truncated: every state is said in words, and every
 * refusal is the Conduit's — no right to edit the case, a case the reader cannot open, a result past
 * the job's own limit, a job that failed — with what was and was not kept. Not modal: the reader may
 * go on working on the canvas while the job runs.
 */
export function BatchExpansion({
  request,
  apiBaseUrl,
  bearerToken,
  investigationId,
  onViewOpened,
  onClose,
  pollMs = 1500,
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

    async function finish(viewId: string): Promise<void> {
      setShown({ phase: "opening" });
      const result = await openView(apiBaseUrl, bearerToken, investigationId, viewId);
      if (!live) return;
      if (result.ok) {
        setShown({ phase: "opened", name: result.opened.view.name });
        onViewOpenedRef.current(result.opened);
      } else if (result.kind === "limit_exceeded") {
        setShown({
          phase: "stopped",
          again: false,
          words: `The batch job finished and saved its result as a view of this case, but the view holds more than the canvas can: ${COUNT.format(result.wouldBe.would_be)} ${what(result.wouldBe)} against a limit of ${COUNT.format(result.wouldBe.cap)}. Nothing was cut to fit; the view is kept in Views in this case.`,
        });
      } else if (result.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: "The batch job finished, but the view holding its result could not be opened. It may have been deleted, or not shared with you.",
        });
      } else {
        setShown({ phase: "stopped", again: false, words: `The batch job finished, but its view could not be opened: ${result.message}` });
      }
    }

    async function watch(jobId: string): Promise<void> {
      const job = await readBatchExpansion(apiBaseUrl, bearerToken, investigationId, jobId);
      if (!live) return;
      switch (job.state) {
        case "done":
          await finish(job.viewId);
          return;
        case "refused":
          setShown({
            phase: "stopped",
            again: false,
            words: `The batch job stopped: its result would be ${COUNT.format(job.wouldBe.would_be)} ${what(job.wouldBe)} against the batch job's limit of ${COUNT.format(job.wouldBe.cap)}. Nothing was cut to fit, and no view was saved. Expand by one relationship instead.`,
          });
          return;
        case "failed":
          setShown({
            phase: "stopped",
            again: true,
            words: `The batch job failed on the server${job.message ? `: ${job.message}` : "."} No view was saved.`,
          });
          return;
        case "not_found":
          setShown({
            phase: "stopped",
            again: false,
            words: "The batch job can no longer be found. It may have been cancelled, or the case closed or no longer shared with you.",
          });
          return;
        case "unreachable":
          setShown((current) => ({
            phase: "watching",
            job: current.phase === "watching" ? current.job : { state: "queued" },
            trouble: `${job.message} Still trying.`,
          }));
          break;
        default:
          setShown({ phase: "watching", job, trouble: null });
      }
      timer = setTimeout(() => void watch(jobId), pollMs);
    }

    async function start(): Promise<void> {
      setShown({ phase: "starting" });
      const started = await startBatchExpansion(apiBaseUrl, bearerToken, investigationId, request);
      if (!live) return;
      if (started.ok) {
        setShown({ phase: "watching", job: { state: "queued" }, trouble: null });
        await watch(started.jobId);
        return;
      }
      if (started.kind === "forbidden") {
        setShown({
          phase: "stopped",
          again: false,
          words: "You cannot run a batch job in this case: its result is saved as a view of the case, and you do not have the right to edit it. No job was started.",
        });
      } else if (started.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: "This case could not be opened. It may have been closed, or not shared with you. No job was started.",
        });
      } else if (started.kind === "limit_exceeded") {
        setShown({
          phase: "stopped",
          again: false,
          words: `Too large even for a batch job: ${COUNT.format(started.wouldBe.would_be)} ${what(started.wouldBe)} against the batch job's limit of ${COUNT.format(started.wouldBe.cap)}. No job was started. Expand by one relationship instead.`,
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

  const job = shown.phase === "watching" ? shown.job : null;
  const showBar = job?.state === "running" && job.done !== null && job.total !== null && job.total > 0;

  return (
    <section className="batch-expansion" role="region" aria-labelledby="batch-expansion-title">
      <h2 id="batch-expansion-title" className="batch-expansion__title" tabIndex={-1} ref={headingRef}>
        Batch job: the whole expansion
      </h2>
      <p className="batch-expansion__figure">
        The canvas refused {COUNT.format(request.refused.would_be)} {what(request.refused)} against its limit of{" "}
        {COUNT.format(request.refused.cap)}; the server runs it instead and saves the result as a view of this case.
      </p>
      <div role="status" aria-live="polite" className="batch-expansion__status">
        {shown.phase === "starting" && "Starting the batch job."}
        {shown.phase === "watching" && progressWords(shown.job)}
        {shown.phase === "opening" && "The batch job has finished. Opening its result as a view."}
        {shown.phase === "opened" && `The batch job has finished. Its result is open as the view “${shown.name}”.`}
      </div>
      {showBar && job?.state === "running" && (
        <progress
          className="batch-expansion__progress"
          aria-label="Batch job progress"
          max={job.total ?? undefined}
          value={job.done ?? undefined}
        />
      )}
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
