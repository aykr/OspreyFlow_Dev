import { useEffect, useRef, useState } from "react";

import {
  type BatchExpansionJob,
  type BatchExpansionRequest,
  readBatchExpansion,
  type Started,
  startBatchExpansion,
} from "./batchExpansionApi";

const COUNT = new Intl.NumberFormat("en-GB");
/** Readings of the job's progress that fail in a row (a server error, no answer) before the panel
 * stops asking and says so: a minute at the route's two seconds. */
const TROUBLES_BEFORE_STOPPING = 30;

export interface BatchExpansionProps {
  /** The expansion the cap refused, as the canvas handed it over. Read once, when the panel starts
   * the job: a new object at a later render (or a renewed token, ADR-050) starts nothing. */
  request: BatchExpansionRequest;
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The reader chose *Open the view*: open the job's result as the read-only lens (ADR-144), as the App
   * opens any view (its `openLens`, so the latest view asked for wins). Null when it is open, or another view
   * was asked for since; otherwise the App's sentence saying why it could not be. Never called unasked: the
   * reader may be working elsewhere when the job finishes. Once it is open the panel closes itself. */
  onOpenView: (viewId: string) => Promise<string | null>;
  onClose: () => void;
  /** How often the job is asked where it is, in milliseconds (ADR-151: every 2 s). */
  pollMs?: number;
  /** Whether a failed job may be tried again from here: not while a view is open, where the App offers no
   * batch job (an expansion there is not the case's). */
  mayStartAgain?: boolean;
}

type Shown =
  | { phase: "starting" }
  | { phase: "watching"; words: string; trouble: string | null }
  | { phase: "done"; words: string; view: { id: string; name: string } }
  | { phase: "opening"; words: string }
  | { phase: "stopped"; words: string; again: boolean };

function what(kind: "nodes" | "edges" | null | undefined): string {
  return kind === "edges" ? "links" : "nodes";
}

/** A refusal's words are the server's, shown as given; these stand in only if it sent none. */
function refusalWords(job: BatchExpansionJob): string {
  if (job.words) return job.words;
  const refusal = job.refusal;
  if (refusal && typeof refusal.cap === "number" && typeof refusal.would_be === "number") {
    return `The batch expansion was refused: ${COUNT.format(refusal.would_be)} ${what(refusal.cap_kind)} against a limit of ${COUNT.format(refusal.cap)}. Nothing was saved. Narrow it by link type, depth or dates and try again.`;
  }
  return "The batch expansion was refused, and nothing was saved. Narrow it by link type, depth or dates and try again.";
}

/**
 * The third of the cap's three choices (spec/00 §4, ADR-151): the refused expansion run whole on the
 * server as a batch job, under the reader's own access, its result saved as a private view of the
 * case, which *Open the view* opens as the lens once it finishes (ADR-151). Nothing joins the working set and nothing is cut to
 * fit. Every state is said in words — the server's own sentence for each stage, refusal and failure,
 * and the Glass's own for what it did with the result. Not modal: the reader may go on working on the
 * canvas while the job runs.
 */
export function BatchExpansion({
  request,
  apiBaseUrl,
  bearerToken,
  investigationId,
  onOpenView,
  onClose,
  pollMs = 2000,
  mayStartAgain = true,
}: BatchExpansionProps) {
  const [shown, setShown] = useState<Shown>({ phase: "starting" });
  const [attempt, setAttempt] = useState(0);
  const onOpenViewRef = useRef(onOpenView);
  onOpenViewRef.current = onOpenView;
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  // Read at each request, never a reason to start again: one job per panel and per *Try again*. The
  // token is the newest the page holds, so a renewal mid-job is used by the next poll.
  const asked = useRef({ apiBaseUrl, bearerToken, investigationId, request, pollMs });
  asked.current = { ...asked.current, apiBaseUrl, bearerToken, investigationId, pollMs };
  const [following, setFollowing] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // The start of each try, kept across React's StrictMode remount (`src/main.tsx`), which runs the effect
  // twice on one mount and keeps refs: the second run awaits the first's POST and never sends its own.
  const startedRef = useRef<{ attempt: number; started: Promise<Started> } | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    headingRef.current?.focus();
    return () => {
      mounted.current = false;
    };
  }, []);

  // The button pressed is taken away by what it does (*Open the view*, *Try the batch job again*), so focus
  // goes to the panel's heading first, never to the page's top (rule 13; spec 02 §3.1h).
  function keepFocusInThePanel(): void {
    headingRef.current?.focus();
  }

  async function openResult(view: { id: string; name: string }, words: string): Promise<void> {
    keepFocusInThePanel();
    setShown({ phase: "opening", words });
    const problem = await onOpenViewRef.current(view.id);
    if (!mounted.current) return;
    if (problem === null) {
      onCloseRef.current();
      return;
    }
    setShown({ phase: "stopped", again: false, words: `The batch job saved its result as the view “${view.name}”, but it could not be opened. ${problem}` });
  }

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let troubles = 0;
    const { request: startWith } = asked.current;

    function finish(job: BatchExpansionJob): void {
      if (!job.view) {
        // Done, its view deleted since (ADR-151): the server's sentence says so; there is nothing to open.
        setShown({ phase: "stopped", again: false, words: job.words || "The batch expansion finished, but the view it saved has since been deleted." });
        return;
      }
      setShown({ phase: "done", words: job.words, view: { id: job.view.id, name: job.view.name } });
    }

    async function watch(jobId: string): Promise<void> {
      const { apiBaseUrl, bearerToken, investigationId, pollMs } = asked.current;
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
          setShown({ phase: "stopped", again: true, words: job.words || "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion." });
          return;
        }
        troubles = 0;
        setShown({ phase: "watching", words: job.words || "The batch job is under way.", trouble: null });
      } else if (read.kind === "not_found") {
        setShown({
          phase: "stopped",
          again: false,
          words: "The batch expansion can no longer be found: it is not one of yours in this case, or the case is no longer shared with you.",
        });
        return;
      } else if (read.kind === "refused") {
        setShown({ phase: "stopped", again: false, words: read.message });
        return;
      } else if (read.kind === "unknown") {
        setShown({ phase: "stopped", again: false, words: read.message });
        return;
      } else if ((troubles += 1) >= TROUBLES_BEFORE_STOPPING) {
        setShown({
          phase: "stopped",
          again: false,
          words: `${read.message} The batch expansion is still running on the server; while it runs, asking for a batch expansion in this case again follows it.`,
        });
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
      const { apiBaseUrl, bearerToken, investigationId, pollMs } = asked.current;
      if (startedRef.current?.attempt !== attempt) {
        startedRef.current = { attempt, started: startBatchExpansion(apiBaseUrl, bearerToken, investigationId, startWith) };
      }
      const started = await startedRef.current.started;
      if (!live) return;
      if (started.ok) {
        const [id, words] = "job" in started ? [started.job.id, started.job.words] : [started.running.id, started.running.words];
        setFollowing(!("job" in started));
        setShown({ phase: "watching", words: words || "The batch job is under way.", trouble: null });
        timer = setTimeout(() => void watch(id), pollMs);
        return;
      }
      if (started.kind === "forbidden") {
        setShown({
          phase: "stopped",
          again: false,
          words:
            started.words ??
            "You cannot run a batch job in this case: it needs the Editor level, since its result is saved as a view of the case. No job was started.",
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
  }, [attempt]);

  return (
    <section className="batch-expansion" role="region" aria-labelledby="batch-expansion-title">
      <h2 id="batch-expansion-title" className="batch-expansion__title" tabIndex={-1} ref={headingRef}>
        Batch job: the whole expansion
      </h2>
      {!following && (
      <p className="batch-expansion__figure">
        The canvas refused {COUNT.format(request.refused.would_be)} {what(request.refused.cap_kind)} against its limit of{" "}
        {COUNT.format(request.refused.cap)}. The server runs the whole expansion instead and saves the result as a view of
        this case, private to you; nothing is added to the canvas.
      </p>
      )}
      <div role="status" aria-live="polite" className="batch-expansion__status">
        {shown.phase === "starting" && "Starting the batch job."}
        {shown.phase === "watching" && shown.words}
        {shown.phase === "done" && shown.words}
        {shown.phase === "opening" && `${shown.words} Opening the view.`.trim()}
      </div>
      {shown.phase === "watching" && shown.trouble !== null && (
        <p className="batch-expansion__trouble">{shown.trouble}</p>
      )}
      {shown.phase === "stopped" && (
        <p className="batch-expansion__message" role="alert">
          {shown.words}
        </p>
      )}
      {(shown.phase === "starting" || shown.phase === "watching") && (
        <p className="batch-expansion__figure">
          Closing this does not stop the job. While it runs, asking for a batch expansion in this case again follows it.
        </p>
      )}
      <div className="batch-expansion__actions">
        {shown.phase === "done" && (
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void openResult(shown.view, shown.words)}
          >
            Open the view
          </button>
        )}
        {shown.phase === "stopped" && shown.again && mayStartAgain && (
          <button type="button" className="btn btn--primary" onClick={() => {
            keepFocusInThePanel();
            setAttempt((n) => n + 1);
          }}>
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
