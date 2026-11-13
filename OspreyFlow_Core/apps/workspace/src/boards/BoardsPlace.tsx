// The Glass's *Boards* (ADR-143 decision 5; Amendment 2 decision 5; ADR-145 decision 1): the case's
// drawing boards this person may see, a new board (blank, from one of the case's views, or from the
// selection on the canvas), and a
// drawing with no case, which makes a drawn dataset, its home case and its board in one step. A board
// always belongs to a case; deleting one never deletes what was drawn on it.
import { useCallback, useEffect, useState } from "react";

import { currentBrand } from "../brand/brand";
import { BoardEditor, type EntityTypeShape } from "./BoardEditor";
import { listBoards, makeBoard, startDrawing, type Board } from "./boardsApi";
import { listViews } from "../views/viewsApi";
import "./boards.css";

export interface BoardsPlaceProps {
  apiBaseUrl: string;
  bearerToken: string;
  /** The open case; `null` with none, when only a drawing with no case can be started. */
  caseId: string | null;
  caseName?: string | null;
  /** What is selected on the case's canvas, offered as a board's start. */
  selection: readonly string[];
  entityTypes: readonly EntityTypeShape[];
  /** The deployment's markings, lowest first, for a drawing's ceiling. */
  markings: readonly string[];
  /** Whether this person may draw (`draw_on_boards`); reading needs only the case. */
  mayDraw: boolean;
  /** A drawing with no case has made its home case: the Glass opens it. */
  onCaseMade?: (caseId: string, boardId: string) => void;
  /** A board to open at once (after a drawing's case is made). */
  initialBoard?: string | null;
}

export function BoardsPlace({
  apiBaseUrl,
  bearerToken,
  caseId,
  caseName,
  selection,
  entityTypes,
  markings,
  mayDraw,
  onCaseMade,
  initialBoard = null,
}: BoardsPlaceProps) {
  const govuk = currentBrand() === "govuk";
  const [boards, setBoards] = useState<Board[] | null>(null);
  const [open, setOpen] = useState<string | null>(initialBoard);
  const [problem, setProblem] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [start, setStart] = useState<"blank" | "view" | "selection">("blank");
  const [views, setViews] = useState<{ id: string; name: string }[]>([]);
  const [viewId, setViewId] = useState("");
  const [drawingName, setDrawingName] = useState("");
  const [ceiling, setCeiling] = useState<string>(markings[Math.min(1, markings.length - 1)] ?? "");
  const [pack, setPack] = useState<"" | "fibo" | "niem" | "stix">("");

  const reload = useCallback(async () => {
    if (!caseId) return;
    const answer = await listBoards(apiBaseUrl, bearerToken, caseId);
    if (answer.ok) setBoards(answer.value);
    else setProblem(answer.message);
    // The case's views this reader may see, to start a board from (ADR-144); none offers none.
    let found: Awaited<ReturnType<typeof listViews>> = [];
    try {
      found = await listViews(apiBaseUrl, bearerToken, caseId);
    } catch (err) {
      // Said, not hidden as "none yet".
      setProblem(err instanceof Error ? err.message : "The views could not be loaded.");
    }
    setViews(found.map((v) => ({ id: v.id, name: v.name })));
    setViewId((held) => held || found[0]?.id || "");
  }, [apiBaseUrl, bearerToken, caseId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => setOpen(initialBoard), [initialBoard, caseId]);

  if (caseId && open) {
    return (
      <BoardEditor
        apiBaseUrl={apiBaseUrl}
        bearerToken={bearerToken}
        caseId={caseId}
        boardId={open}
        entityTypes={entityTypes}
        onBack={() => {
          setOpen(null);
          void reload();
        }}
      />
    );
  }

  const button = (primary = false) => (govuk ? `govuk-button${primary ? "" : " govuk-button--secondary"} board__button` : `btn${primary ? " btn--primary" : ""} board__button`);

  return (
    <section className={govuk ? "boards boards--govuk" : "boards"} aria-labelledby="boards-title">
      <h2 id="boards-title" className={govuk ? "govuk-heading-m" : "board__title"}>
        {caseId ? `Drawing boards in case ${caseName ?? ""}`.trim() : "Drawing boards"}
      </h2>
      <p className="caption">
        {caseId
          ? // The owner's navigation decision (ADR-145 Amendment 15): the strip's note left; the board says it here.
            "Drawing board: your sketch; it does not change the case's data. Everything drawn is kept in this case's analyst layer. Deleting a board never deletes what was drawn."
          : "Open a case to see its boards, or start a drawing as a case of its own."}
      </p>
      {problem && (
        <p role="alert" className={govuk ? "govuk-error-message" : "board__problem"}>
          {problem}
        </p>
      )}
      <div className="boards__columns">
        {caseId && (
          <div className="boards__list-column">
            {boards === null ? (
              <p className="caption">Reading the boards…</p>
            ) : boards.length === 0 ? (
              <p className="caption">No boards in this case yet.</p>
            ) : (
              <ul className="boards__list" aria-label="Boards in this case">
                {boards.map((b) => (
                  <li key={b.id} className="boards__card">
                    <button type="button" className={button()} onClick={() => setOpen(b.id)}>
                      Open {b.name}
                    </button>
                    <span className="caption">
                      {b.drawn} drawn item{b.drawn === 1 ? "" : "s"} · by {b.created_by}
                    </span>
                    <span className={govuk ? "govuk-tag govuk-tag--grey" : "board-tag"}>{b.shared ? "Shared" : "Only you"}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {mayDraw && (
          <div className="boards__new">
            {caseId && (
              <form
                className={govuk ? "board__panel" : "board__panel panel"}
                aria-labelledby="boards-new-title"
                onSubmit={(e) => {
                  e.preventDefault();
                  const fromView = views.find((v) => v.id === viewId);
                  if (start === "view" && !fromView) return setProblem("Choose the view to start from.");
                  const named =
                    name.trim() ||
                    (start === "selection" ? `Selection of ${selection.length}` : start === "view" ? `From ${fromView!.name}` : "New board");
                  void makeBoard(apiBaseUrl, bearerToken, caseId, {
                    name: named,
                    start,
                    ...(start === "selection" ? { nodeIds: [...selection] } : {}),
                    ...(start === "view" ? { viewId } : {}),
                  }).then((answer) => {
                    if (!answer.ok) return setProblem(answer.message);
                    setName("");
                    setOpen(answer.value.id);
                  });
                }}
              >
                <h3 id="boards-new-title" className={govuk ? "govuk-heading-s" : "label"}>
                  New board
                </h3>
                <div className={govuk ? "govuk-form-group" : "board__field"}>
                  <label htmlFor="boards-new-name" className={govuk ? "govuk-label" : "label"}>
                    Board name
                  </label>
                  <input id="boards-new-name" className={govuk ? "govuk-input" : "input"} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} />
                </div>
                <fieldset className={govuk ? "govuk-fieldset" : "board__fieldset"}>
                  <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "label"}>Start from</legend>
                  <div className={govuk ? "govuk-radios govuk-radios--small" : "board__radios"}>
                    <div className={govuk ? "govuk-radios__item" : "board__radio"}>
                      <input id="boards-start-blank" className={govuk ? "govuk-radios__input" : undefined} type="radio" name="boards-start" checked={start === "blank"} onChange={() => setStart("blank")} />
                      <label htmlFor="boards-start-blank" className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                        Blank
                      </label>
                    </div>
                    <div className={govuk ? "govuk-radios__item" : "board__radio"}>
                      <input
                        id="boards-start-view"
                        className={govuk ? "govuk-radios__input" : undefined}
                        type="radio"
                        name="boards-start"
                        disabled={views.length === 0}
                        checked={start === "view"}
                        onChange={() => setStart("view")}
                      />
                      <label htmlFor="boards-start-view" className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                        From a view of this case{views.length === 0 ? " (none yet)" : ""}
                      </label>
                    </div>
                    <div className={govuk ? "govuk-radios__item" : "board__radio"}>
                      <input
                        id="boards-start-selection"
                        className={govuk ? "govuk-radios__input" : undefined}
                        type="radio"
                        name="boards-start"
                        disabled={selection.length === 0}
                        checked={start === "selection"}
                        onChange={() => setStart("selection")}
                      />
                      <label htmlFor="boards-start-selection" className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                        From the selection ({selection.length} item{selection.length === 1 ? "" : "s"}, as live references)
                      </label>
                    </div>
                  </div>
                </fieldset>
                {start === "view" && views.length > 0 && (
                  <div className={govuk ? "govuk-form-group" : "board__field"}>
                    <label htmlFor="boards-new-view" className={govuk ? "govuk-label" : "label"}>
                      The view (its items come as live references)
                    </label>
                    <select id="boards-new-view" className={govuk ? "govuk-select" : "input"} value={viewId} onChange={(e) => setViewId(e.target.value)}>
                      {views.map((v) => (
                        <option key={v.id} value={v.id}>
                          {v.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <button type="submit" className={button(true)}>
                  Make the board
                </button>
              </form>
            )}
            <form
              className={govuk ? "board__panel" : "board__panel panel"}
              aria-labelledby="boards-drawing-title"
              onSubmit={(e) => {
                e.preventDefault();
                if (!drawingName.trim()) return setProblem("Name the drawing.");
                void startDrawing(apiBaseUrl, bearerToken, { name: drawingName.trim(), highestMarking: ceiling, pack: pack || null }).then((answer) => {
                  if (!answer.ok) return setProblem(answer.message);
                  onCaseMade?.(answer.value.investigation_id, answer.value.board.id);
                });
              }}
            >
              <h3 id="boards-drawing-title" className={govuk ? "govuk-heading-s" : "label"}>
                New drawing as a case of its own
              </h3>
              <p className="caption">Makes a drawn dataset named after it, its case with you as its Author, and its board. What you draw is its data.</p>
              <div className={govuk ? "govuk-form-group" : "board__field"}>
                <label htmlFor="boards-drawing-name" className={govuk ? "govuk-label" : "label"}>
                  Drawing name
                </label>
                <input id="boards-drawing-name" className={govuk ? "govuk-input" : "input"} value={drawingName} maxLength={200} onChange={(e) => setDrawingName(e.target.value)} />
              </div>
              <div className={govuk ? "govuk-form-group" : "board__field"}>
                <label htmlFor="boards-drawing-ceiling" className={govuk ? "govuk-label" : "label"}>
                  Highest marking it may hold
                </label>
                <select id="boards-drawing-ceiling" className={govuk ? "govuk-select" : "input"} value={ceiling} onChange={(e) => setCeiling(e.target.value)}>
                  {markings.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className={govuk ? "govuk-form-group" : "board__field"}>
                <label htmlFor="boards-drawing-pack" className={govuk ? "govuk-label" : "label"}>
                  Starter model
                </label>
                <select id="boards-drawing-pack" className={govuk ? "govuk-select" : "input"} value={pack} onChange={(e) => setPack(e.target.value as typeof pack)}>
                  <option value="">The POLE core alone</option>
                  <option value="fibo">FIBO</option>
                  <option value="niem">NIEM</option>
                  <option value="stix">STIX</option>
                </select>
              </div>
              <button type="submit" className={button()}>
                Start the drawing
              </button>
            </form>
          </div>
        )}
      </div>
    </section>
  );
}
