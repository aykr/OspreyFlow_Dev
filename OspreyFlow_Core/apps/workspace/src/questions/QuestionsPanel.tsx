// The case's questions to the model (ADR-098 decision 4): the analyst chooses what to read from
// (ADR-098 Amendment 7: *Selected items*, *Everything on the graph*, *Whole case*, which Amendment 9
// reads through the case's search with the question's own words), is told by the Conduit what that
// will read and which engine will answer (never counted here), asks, and the model answers from
// those Documents, graph facts and sources, citing them; what it proposes is listed with
// Accept and Reject — inferred until accepted, and accepted onto this case's canvas. The
// conversation is the case's, and shown to each reader as far as they may see it.
import { useEffect, useId, useRef, useState } from "react";

import { AnsweredBy, EnginePicker, useEngineChoice } from "../models/engines";
import { candidateLabel, candidateSource, type EmailCandidate } from "../inspector/linkEventsApi";
import { sourceAsFact, splitAnswer, type GraphCitation, type SearchCitation } from "./graphFacts";
import {
  acceptProposal,
  askQuestion,
  listQuestions,
  rejectProposal,
  willRead,
  type QuestionAnswer,
  type ReadFrom,
  type ReadSummary,
  type WillRead,
} from "./questionsApi";

export interface QuestionsPanelProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** An accepted proposal's change to the view. */
  onDelta: (delta: unknown) => void;
  onOpenDocument?: (documentId: string) => void;
  /** What is selected on the canvas now (ADR-129): the graph facts asked about are these and one
   * link around them; nothing selected is the whole view. */
  selection?: { nodeIds: string[]; linkIds: string[] };
  /** The timeline window now, if one is set: only links and events inside it are in the facts. */
  getTimelineWindow?: () => { validFrom: string; validTo: string | null } | null;
  /** A `[G-n]` was chosen: the canvas selects what it stands for and brings it into view. */
  onSelectFacts?: (citation: GraphCitation) => void;
  /** ADR-144 decision 4: the questions are asked in this case view (*Ask the model about these*
   * saved it, private to the asker): its conversation is listed, asked and decided through it, and
   * reads only what it holds. Absent: the case's own conversation. */
  view?: { id: string; name: string } | null;
  /** Leave the view's conversation for the case's own. */
  onLeaveView?: () => void;
  /** What to read from when the panel opens, before the analyst chooses; absent, the selection
   * when there is one, else the graph. */
  initialReadFrom?: ReadFrom;
}

/** What *Whole case* does, in one line (ADR-098 Amendment 9), shown under the choice before anything
 * is asked. The server's own words (`WHOLE_CASE_LINE`, held to these by
 * `test_questions_read_from.py`). */
export const WHOLE_CASE_LINE = "Whole case finds things by their names and words, not by what they mean.";

const READ_FROM_CHOICES: { value: ReadFrom; label: string }[] = [
  { value: "selection", label: "Selected items" },
  { value: "graph", label: "Everything on the graph" },
  { value: "case", label: "Whole case" },
];

function counted(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "About: Tarbuck, Kyle and 1 other", or "About: everything on the graph", from the Conduit's
 * summary (the first selected item's name is the Conduit's, as the asker may see it). */
export function aboutWords(read: ReadSummary): string {
  if (read.read_from === "graph") return "About: everything on the graph";
  if (read.read_from === "case") return "About: the whole case, searched with your question's words";
  if (read.first_selected === null) return `About: ${counted(read.selected, "selected item", "selected items")}`;
  const others = read.selected - 1;
  return others > 0
    ? `About: ${read.first_selected} and ${counted(others, "other", "others")}`
    : `About: ${read.first_selected}`;
}

/** What was or will be read, in words: the documents (and those with no text, which are not), the
 * other items, the links and the events counted on them. */
export function readWords(read: ReadSummary): string {
  if (read.read_from === "case") return caseWords(read);
  const parts = [
    counted(read.documents, "document", "documents"),
    counted(read.items, "item", "items"),
    counted(read.links, "link", "links"),
  ];
  if (read.events > 0) parts.push(counted(read.events, "event", "events"));
  const listed = `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  const unread =
    read.documents_without_text > 0
      ? ` (${counted(read.documents_without_text, "document has", "documents have")} no text to read)`
      : "";
  return `${listed}${unread}`;
}

function listed(parts: string[]): string {
  return parts.length === 1 ? parts[0]! : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/** *Whole case*: what the search found that the question reads, by how each is read. */
function caseWords(read: ReadSummary): string {
  const parts: string[] = [];
  if (read.documents > 0) parts.push(`${counted(read.documents, "document", "documents")} whole`);
  if (read.passages > 0) parts.push(`${counted(read.passages, "document", "documents")} by the passage found`);
  if (read.items > 0) parts.push(counted(read.items, "other record", "other records"));
  const unread =
    read.documents_without_text > 0
      ? ` (${counted(read.documents_without_text, "document has", "documents have")} no text to read)`
      : "";
  return `${counted(read.found, "match", "matches")} found in the case: ${listed(parts.length ? parts : ["nothing to read"])}${unread}`;
}

/** What limits a *Whole case* reading, each said once: the search's own fallback words, counts it
 * could not complete, and a second page never read (rule 2). */
export function caseLimits(read: ReadSummary): string[] {
  if (read.read_from !== "case") return [];
  const said: string[] = [];
  if (read.limited_reason) said.push(read.limited_reason);
  if (!read.counts_exact) said.push("The search's counts may be incomplete.");
  if (read.more) said.push(`Only the first ${read.found} matches are read; there are more.`);
  return said;
}

/** How long the scope must stay still before *will read* is asked (each answer reads the scope's
 * documents and writes an audit row). */
export const WILL_READ_DEBOUNCE_MS = 300;

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
  selection,
  getTimelineWindow,
  onSelectFacts,
  view = null,
  onLeaveView,
  initialReadFrom,
}: QuestionsPanelProps) {
  const viewId = view?.id ?? null;
  const [entries, setEntries] = useState<QuestionAnswer[] | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // ADR-135 decision 5: the engine to ask, among those offered for extraction.
  const engineChoice = useEngineChoice(apiBaseUrl, bearerToken, "extraction", investigationId);
  // ADR-098 Amendment 7: what to read from. The selection is the default when there is one; a
  // choice of Selected items with nothing selected falls back to the graph.
  const nodeIds = selection?.nodeIds ?? [];
  const linkIds = selection?.linkIds ?? [];
  const hasSelection = nodeIds.length + linkIds.length > 0;
  const [picked, setPicked] = useState<ReadFrom | null>(initialReadFrom ?? null);
  const readFrom: ReadFrom =
    picked === "graph" || picked === "case" || (picked === "selection" && hasSelection)
      ? picked
      : hasSelection
        ? "selection"
        : "graph";
  // What will be read and who will answer, from the Conduit (`will-read`), for the scope as it is now.
  const [will, setWill] = useState<WillRead | null>(null);
  const [willProblem, setWillProblem] = useState<string | null>(null);
  const [willAsked, setWillAsked] = useState(0);
  // Keyed on the body *will read* actually sends: under Everything on the graph a click on the
  // canvas changes nothing sent, so asks nothing. The timeline window is read as the panel draws,
  // and again when the question box takes focus (`willAsked`), as the question itself reads it.
  const sentNodeIds = readFrom === "selection" ? nodeIds : [];
  const sentLinkIds = readFrom === "selection" ? linkIds : [];
  const timelineWindow = getTimelineWindow?.() ?? null;
  const askedWindow = useRef<string>("");
  // Under Whole case the question's words are what is searched, so they are part of the scope.
  const searched = readFrom === "case" ? question.trim() : null;
  const scopeKey = JSON.stringify([readFrom, sentNodeIds, sentLinkIds, timelineWindow, engineChoice.chosen, viewId, investigationId, searched]);
  const radioName = useId();

  useEffect(() => {
    let cancelled = false;
    setEntries(null);
    listQuestions(apiBaseUrl, bearerToken, investigationId, viewId)
      .then((found) => !cancelled && setEntries(found))
      .catch((err: unknown) => {
        if (cancelled) return;
        setEntries([]);
        setProblem(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken, investigationId, viewId]);

  useEffect(() => {
    let cancelled = false;
    // The last answer is for another scope: it is not shown, and Ask waits, until this one comes.
    setWill(null);
    setWillProblem(null);
    // Debounced: a run of changes (selecting several items) asks once, after the last.
    const timer = window.setTimeout(() => {
      const sentWindow = getTimelineWindow?.() ?? null;
      askedWindow.current = JSON.stringify(sentWindow);
      willRead(apiBaseUrl, bearerToken, investigationId, {
        nodeIds: sentNodeIds,
        linkIds: sentLinkIds,
        window: sentWindow,
        engine: engineChoice.chosen,
        viewId,
        readFrom,
        question: searched,
      })
        .then((found) => !cancelled && setWill(found))
        .catch((err: unknown) => {
          if (cancelled) return;
          setWill(null);
          setWillProblem(err instanceof Error ? err.message : String(err));
        });
    }, WILL_READ_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // `scopeKey` stands for the scope's own values; `willAsked` asks again after a question.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl, bearerToken, scopeKey, willAsked]);

  async function ask(): Promise<void> {
    const text = question.trim();
    if (!text || asking) return;
    setAsking(true);
    setProblem(null);
    try {
      const answered = await askQuestion(apiBaseUrl, bearerToken, investigationId, text, {
        nodeIds: sentNodeIds,
        linkIds: sentLinkIds,
        window: getTimelineWindow?.() ?? null,
        engine: engineChoice.chosen,
        viewId,
        readFrom,
      });
      setEntries((prev) => [...(prev ?? []), answered]);
      setQuestion("");
      setWillAsked((n) => n + 1);
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
        const result = await acceptProposal(apiBaseUrl, bearerToken, investigationId, candidate.id, viewId);
        onDelta(result.delta);
        settle(candidate.id, "accepted");
      } else {
        await rejectProposal(apiBaseUrl, bearerToken, investigationId, candidate.id, viewId);
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
      {view && (
        <p role="status" style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
          <span>
            Asking in the view <strong>{view.name}</strong>, private to you until you share it.
          </span>
          {onLeaveView && (
            <button type="button" className="btn btn--quiet" onClick={onLeaveView}>
              Ask about the whole case instead
            </button>
          )}
        </p>
      )}
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        The model reads what you choose below, as far as you may see it: the documents whole, the
        items, their links and the events on them. What it proposes is a suggestion until you
        accept it.
      </p>
      {entries === null && <p style={{ margin: 0 }}>Loading the questions…</p>}
      {entries !== null && entries.length === 0 && (
        <p style={{ color: "var(--text-tertiary)", margin: 0 }}>No questions asked in this {view ? "view" : "case"} yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <ol role="list" aria-label="Questions asked" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-16)" }}>
          {entries.map((entry) => (
            <li key={entry.id} style={{ display: "grid", gap: "var(--sp-8)" }}>
              <p style={{ margin: 0, fontWeight: 600 }}>{entry.question}</p>
              <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                {entry.author_name ?? entry.author} · {WHEN.format(new Date(entry.created_at))} UTC
              </p>
              <AnswerText entry={entry} onSelectFacts={onSelectFacts} />
              <AnsweredBy engine={entry.engine} model={entry.model} engines={engineChoice.engines} />
              {entry.read && <ReadLine read={entry.read} />}
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
                    ? "1 item was left out: it is not in the documents, graph facts or sources the model was given."
                    : `${entry.unplaced} items were left out: they are not in the documents, graph facts or sources the model was given.`}
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
        {/* Rows far enough apart that each radio keeps its 24px target (WCAG 2.2, 2.5.8). */}
        <fieldset style={{ border: 0, margin: 0, padding: 0, display: "grid", gap: "var(--sp-8)" }}>
          <legend style={{ fontSize: "var(--fs-12)", padding: 0, marginBottom: "var(--sp-4)" }}>Read from</legend>
          {READ_FROM_CHOICES.map((choice) => {
            const unavailable = choice.value === "selection" && !hasSelection;
            const id = `${radioName}-${choice.value}`;
            return (
              <span key={choice.value} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
                <input
                  type="radio"
                  id={id}
                  name={radioName}
                  value={choice.value}
                  checked={readFrom === choice.value}
                  disabled={asking || unavailable}
                  aria-describedby={choice.value === "case" ? `${radioName}-case-why` : undefined}
                  onChange={() => setPicked(choice.value)}
                />
                <label htmlFor={id}>
                  {choice.label}
                  {choice.value === "selection" && !hasSelection && (
                    <span style={{ color: "var(--text-tertiary)" }}> (nothing is selected)</span>
                  )}
                </label>
              </span>
            );
          })}
          <p id={`${radioName}-case-why`} style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
            {WHOLE_CASE_LINE}
          </p>
        </fieldset>
        <div aria-live="polite" data-testid="will-read" style={{ display: "grid", gap: "var(--sp-2)" }}>
          {will === null && willProblem === null && (
            <p style={{ margin: 0, color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>Working out what will be read…</p>
          )}
          {willProblem !== null && <p style={{ margin: 0 }}>{willProblem}</p>}
          {will !== null && willProblem === null && (
            <>
              <p style={{ margin: 0 }}>{aboutWords(will.read)}</p>
              <p style={{ margin: 0 }}>Will read: {readWords(will.read)}</p>
              {caseLimits(will.read).map((line) => (
                <p key={line} style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--fs-12)" }}>
                  {line}
                </p>
              ))}
              {will.read.documents === 0 && (
                <p style={{ margin: 0, color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                  {will.read.read_from === "case"
                    ? "No document will be read whole: the answer will come from what the search found."
                    : "No documents will be read: the answer will come from the links and events."}
                </p>
              )}
              {will.engine_label !== null ? (
                <p style={{ margin: 0 }}>
                  Will be answered by {will.engine_label}
                  {will.model ? ` (${will.model})` : ""}
                </p>
              ) : (
                <p style={{ margin: 0 }}>{will.refused ?? "No engine may answer this question."}</p>
              )}
            </>
          )}
        </div>
        {engineChoice.failed && (
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "var(--fs-12)" }}>
            The list of model engines could not be loaded, so there is no choice of engine: the
            question goes to the deployment&rsquo;s default.
          </p>
        )}
        <EnginePicker choice={engineChoice} id="questions-engine" disabled={asking} reasons={will?.unusable} />
        {engineChoice.chosen === null && will !== null && will.unusable.length > 0 && (
          <div style={{ display: "grid", gap: "var(--sp-2)" }}>
            {will.unusable.map((engine) => (
              <p key={engine.name} style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
                {`${engine.label}: ${engine.reason}`}
              </p>
            ))}
          </div>
        )}
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
          // The timeline window may have moved without the panel being drawn again: if it has,
          // *will read* is asked again before the question is, as the question will read it.
          onFocus={() => {
            if (JSON.stringify(getTimelineWindow?.() ?? null) !== askedWindow.current) setWillAsked((n) => n + 1);
          }}
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
              The model is reading…
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

/** What an answer read, from its kept summary: with no document, the answer says it came from the
 * links and events (ADR-098 Amendment 7). */
function ReadLine({ read }: { read: ReadSummary }) {
  if (read.read_from === "case") {
    return (
      <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
        {`Read from the whole case: ${readWords(read)}. ${WHOLE_CASE_LINE}`}
        {caseLimits(read).map((line) => ` ${line}`)}
      </p>
    );
  }
  return (
    <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>
      {read.documents === 0
        ? `No documents were read: the answer comes from the links and events (read: ${readWords(read)}).`
        : `Read: ${readWords(read)}.`}
    </p>
  );
}

/** The answer, with each `[G-n]` the Conduit returned as a button that selects what it stands for.
 * A fact the words do not mark follows the answer, so every citation is reachable. */
function AnswerText({
  entry,
  onSelectFacts,
}: {
  entry: QuestionAnswer;
  onSelectFacts?: (citation: GraphCitation) => void;
  /** ADR-144 decision 4: the questions are asked in this case view (*Ask the model about these*
   * saved it, private to the asker): its conversation is listed, asked and decided through it, and
   * reads only what it holds. Absent: the case's own conversation. */
  view?: { id: string; name: string } | null;
  /** Leave the view's conversation for the case's own. */
  onLeaveView?: () => void;
}) {
  const { parts, unmarked, unmarkedSources } = splitAnswer(
    entry.answer,
    entry.graph_citations ?? [],
    entry.search_citations ?? [],
  );
  // An `[S-n]` selects its records as a fact does (`bringFactIntoView`); one not on the canvas
  // leaves the selection as it was.
  const sourceButton = (source: SearchCitation, key: string) => (
    <button
      key={key}
      type="button"
      className="btn btn--quiet"
      disabled={!onSelectFacts}
      aria-label={`Select ${source.label}, ${source.name}, on the canvas`}
      title={`${source.type}: ${source.why}`}
      onClick={() => onSelectFacts?.(sourceAsFact(source))}
    >
      {source.label}
    </button>
  );
  const factButton = (citation: GraphCitation, key: string) => (
    <button
      key={key}
      type="button"
      className="btn btn--quiet"
      disabled={!onSelectFacts}
      aria-label={`Select ${citation.label} on the canvas`}
      onClick={() => onSelectFacts?.(citation)}
    >
      {citation.label}
    </button>
  );
  return (
    <>
      <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
        {entry.answer === "" && "The model gave no answer."}
        {parts.map((part, i) =>
          part.kind === "text" ? (
            <span key={`t${i}`}>{part.text}</span>
          ) : part.kind === "fact" ? (
            factButton(part.citation, `f${i}`)
          ) : (
            sourceButton(part.citation, `s${i}`)
          ),
        )}
      </p>
      {unmarked.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-4)", alignItems: "center" }}>
          <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>Graph facts</span>
          {unmarked.map((citation) => factButton(citation, `u${citation.number}`))}
        </div>
      )}
      {(entry.search_citations ?? []).length > 0 && (
        <ul role="list" aria-label="Sources found in the case" style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {(entry.search_citations ?? []).map((source) => (
            <li key={source.number} style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
              {unmarkedSources.includes(source) ? sourceButton(source, `us${source.number}`) : <span>{source.label}</span>}
              <span className="value">{source.name}</span>
              <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
                {source.type} · {source.why}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
