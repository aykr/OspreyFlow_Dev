// A drawing board (ADR-143 decisions 4 to 7; C7; Amendment 2 decisions 3 and 8; spec 02 §2.0b):
// declare an item, link two by the link handle, by Alt-drag, by right-click *Draw a link from here*
// or by the *Draw a link…* form opened from the selected item; move an item by dragging it or by the
// arrow keys; inspect, edit, withdraw; give a drawn item a picture; and decide *Looks like a loaded
// item* pairs. Drawn items are dashed amber; loaded items are live references, solid and grey, linked
// to but never edited here. Every refusal (the case's ceiling, a type outside the case's model) is
// shown in the Conduit's own words. Under the GOV.UK brand the forms are GOV.UK fields with an error
// summary, statuses GOV.UK tags and the type choice radios (decision 13).
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { currentBrand } from "../brand/brand";
import {
  GRADES,
  clamp,
  isDrawn,
  itemLabel,
  linkLabel,
  moved,
  nextPlace,
  placed,
  type BoardNode,
  type Position,
} from "./boardModel";
import {
  boardPictures,
  decideMatch,
  declareItem,
  drawLink,
  editItem,
  matchSuggestions,
  moveItems,
  openBoard,
  pictureUrl,
  shareBoard,
  uploadPicture,
  withdrawItem,
  type BoardOpened,
  type Grading,
  type MatchSuggestions,
} from "./boardsApi";
import "./boards.css";

export interface EntityTypeShape {
  name: string;
  properties?: { name: string; type?: string; required?: boolean }[];
}

export interface BoardEditorProps {
  apiBaseUrl: string;
  bearerToken: string;
  caseId: string;
  boardId: string;
  /** The deployment's entity types, for a type's required properties. */
  entityTypes: readonly EntityTypeShape[];
  onBack: () => void;
}

type Panel =
  | { kind: "declare"; type: string }
  | { kind: "edit"; id: string }
  | { kind: "link"; from: string; to: string | null }
  | { kind: "withdraw"; id: string }
  | null;

interface Menu {
  id: string;
  x: number;
  y: number;
}

const EMPTY_GRADE = (scheme: string): Grading => {
  const parts = GRADES[scheme] ?? GRADES["5x5x5"]!;
  return { scheme: scheme as Grading["scheme"], source: parts.source[1] ?? "B", intelligence: parts.intelligence[1] ?? "2", handling: parts.handling[0] ?? "1" };
};

export function BoardEditor({ apiBaseUrl, bearerToken, caseId, boardId, entityTypes, onBack }: BoardEditorProps) {
  const govuk = currentBrand() === "govuk";
  const [opened, setOpened] = useState<BoardOpened | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [positions, setPositions] = useState<Record<string, Position>>({});
  const [chosenType, setChosenType] = useState<string>("");
  const [matches, setMatches] = useState<MatchSuggestions | null>(null);
  const [pictures, setPictures] = useState<Record<string, string>>({});
  const [rubber, setRubber] = useState<{ from: string; x: number; y: number } | null>(null);
  const surface = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  const reload = useCallback(async () => {
    const answer = await openBoard(apiBaseUrl, bearerToken, caseId, boardId);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    setOpened(answer.value);
    setPositions(placed(answer.value));
    setChosenType((type) => type || answer.value.node_types?.[0] || "");
    const found = await matchSuggestions(apiBaseUrl, bearerToken, caseId, boardId);
    setMatches(found.ok ? found.value : null);
    const shown = await boardPictures(apiBaseUrl, bearerToken, caseId, boardId);
    setPictures(shown.ok ? shown.value : {});
  }, [apiBaseUrl, bearerToken, caseId, boardId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const byId = useMemo(() => new Map((opened?.nodes ?? []).map((n) => [n.id, n])), [opened]);
  const drawnIds = useMemo(() => new Set(opened?.drawn ?? []), [opened]);
  const mayDraw = opened?.may_draw ?? false;
  const scheme = opened?.grading_scheme ?? "5x5x5";

  // After a reload the item's button may be drawn a frame or two later: try for a few frames.
  const focusItem = (id: string, tries = 10) =>
    requestAnimationFrame(() => {
      const button = itemRefs.current.get(id);
      if (button) button.focus();
      else if (tries > 0) focusItem(id, tries - 1);
    });

  const keepPlaces = async (changed: Record<string, Position>) => {
    const answer = await moveItems(apiBaseUrl, bearerToken, caseId, boardId, changed);
    if (!answer.ok) setProblem(answer.message);
  };

  // --- moving: drag, or the arrow keys -----------------------------------------------------

  const drag = useRef<{ id: string; startX: number; startY: number; at: Position; moved: boolean; linking: boolean } | null>(null);

  const fraction = (clientX: number, clientY: number): Position => {
    const box = surface.current?.getBoundingClientRect();
    if (!box || box.width === 0 || box.height === 0) return { x: 0.5, y: 0.5 };
    return { x: clamp((clientX - box.left) / box.width), y: clamp((clientY - box.top) / box.height) };
  };

  const itemAt = (clientX: number, clientY: number): string | null => {
    const hit = document.elementFromPoint(clientX, clientY)?.closest<HTMLElement>("[data-board-item]");
    return hit?.dataset.boardItem ?? null;
  };

  function beginDrag(event: PointerEvent, id: string, linking: boolean): void {
    if (event.button !== 0 || !mayDraw) return;
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    drag.current = { id, startX: event.clientX, startY: event.clientY, at: positions[id] ?? { x: 0.5, y: 0.5 }, moved: false, linking: linking || event.altKey };
  }

  function dragging(event: PointerEvent): void {
    const held = drag.current;
    if (!held) return;
    if (Math.abs(event.clientX - held.startX) + Math.abs(event.clientY - held.startY) > 4) held.moved = true;
    if (!held.moved) return;
    const at = fraction(event.clientX, event.clientY);
    if (held.linking) setRubber({ from: held.id, x: at.x, y: at.y });
    else setPositions((p) => ({ ...p, [held.id]: at }));
  }

  function endDrag(event: PointerEvent): void {
    const held = drag.current;
    drag.current = null;
    setRubber(null);
    if (!held || !held.moved) return;
    if (held.linking) {
      const target = itemAt(event.clientX, event.clientY);
      if (target && target !== held.id) openLink(held.id, target);
      return;
    }
    const at = fraction(event.clientX, event.clientY);
    void keepPlaces({ [held.id]: at });
    setSaid(`${labelOf(held.id)} moved.`);
  }

  function itemKeys(event: KeyboardEvent, id: string): void {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault();
      const box = itemRefs.current.get(id)?.getBoundingClientRect();
      setMenu({ id, x: box ? box.left : 0, y: box ? box.bottom : 0 });
      return;
    }
    if (!mayDraw) return;
    const next = moved(positions[id] ?? { x: 0.5, y: 0.5 }, event.key, event.shiftKey);
    if (!next) return;
    event.preventDefault();
    setPositions((p) => ({ ...p, [id]: next }));
    void keepPlaces({ [id]: next });
    setSaid(`${labelOf(id)} moved to ${Math.round(next.x * 100)}% across, ${Math.round(next.y * 100)}% down.`);
  }

  const labelOf = (id: string) => {
    const node = byId.get(id);
    return node ? itemLabel(node) : "The item";
  };

  // --- linking ------------------------------------------------------------------------------

  function openLink(from: string, to: string | null): void {
    setMenu(null);
    setSelected(from);
    setPanel({ kind: "link", from, to });
  }

  // --- withdrawing --------------------------------------------------------------------------

  async function withdraw(id: string): Promise<void> {
    const itemId = opened?.items?.[id];
    if (!itemId) return;
    const answer = await withdrawItem(apiBaseUrl, bearerToken, caseId, itemId);
    if (!answer.ok) {
      setProblem(answer.message);
      return;
    }
    const links = answer.value.links?.length ?? 0;
    setSaid(`${labelOf(id)} withdrawn${links ? `, with ${links} link${links === 1 ? "" : "s"} drawn to it` : ""}. It is kept in the audit.`);
    setPanel(null);
    setSelected(null);
    await reload();
  }

  if (!opened) {
    return (
      <section className="board" aria-label="Drawing board">
        {problem ? (
          <p role="alert" className={govuk ? "govuk-error-message" : "board__problem"}>
            {problem}
          </p>
        ) : (
          <p className="caption">Opening the board…</p>
        )}
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary" : "btn"} onClick={onBack}>
          Back to the boards
        </button>
      </section>
    );
  }

  const selectedNode = selected ? byId.get(selected) ?? null : null;
  const selectedMine = selectedNode ? drawnIds.has(selectedNode.id) && mayDraw && Boolean(opened.items?.[selectedNode.id]) : false;

  return (
    <section className={govuk ? "board board--govuk" : "board"} aria-labelledby="board-title">
      <div className="board__head">
        <h2 id="board-title" className={govuk ? "govuk-heading-m" : "board__title"}>
          {opened.board.name}
        </h2>
        <span className={govuk ? "govuk-tag govuk-tag--grey" : "board-tag"}>{opened.board.shared ? "Shared with the case" : "Only you"}</span>
        {!mayDraw && <span className={govuk ? "govuk-tag govuk-tag--yellow" : "board-tag"}>Read only: drawn by {opened.board.created_by}</span>}
        <span className="board__spacer" />
        {mayDraw && !opened.board.shared && (
          <button
            type="button"
            className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"}
            onClick={() =>
              void shareBoard(apiBaseUrl, bearerToken, caseId, boardId).then((a) => {
                if (a.ok) void reload();
                else setProblem(a.message);
              })
            }
          >
            Share with the case
          </button>
        )}
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={onBack}>
          Back to the boards
        </button>
      </div>
      <p className="caption board__note">
        What you draw is kept in this case&apos;s analyst layer{opened.ceiling ? `, marked no higher than ${opened.ceiling}` : ""}. Drag an item to
        move it, or use the arrow keys. Drag its ⟶ handle onto another item to draw a link, or hold Alt while dragging, or right-click:
        Draw a link from here.
      </p>
      {(opened.missing ?? 0) > 0 && (
        <p className="caption" role="status">
          {opened.missing} item{opened.missing === 1 ? "" : "s"} on this board could not be shown.
        </p>
      )}
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert" tabIndex={-1}>
          {govuk && <h2 className="govuk-error-summary__title">There is a problem</h2>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
          <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => setProblem(null)}>
            Dismiss
          </button>
        </div>
      )}
      <div className="board__body">
        {mayDraw && (
          <div className="board__palette">
            <fieldset className={govuk ? "govuk-fieldset" : "board__fieldset"}>
              <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "label"}>Type of item to declare</legend>
              <div className={govuk ? "govuk-radios govuk-radios--small" : "board__radios"}>
                {(opened.node_types ?? []).map((type) => (
                  <div key={type} className={govuk ? "govuk-radios__item" : "board__radio"}>
                    <input
                      id={`board-type-${type}`}
                      className={govuk ? "govuk-radios__input" : undefined}
                      type="radio"
                      name="board-type"
                      value={type}
                      checked={chosenType === type}
                      onChange={() => setChosenType(type)}
                    />
                    <label htmlFor={`board-type-${type}`} className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                      {type}
                    </label>
                  </div>
                ))}
              </div>
            </fieldset>
            <button
              type="button"
              className={govuk ? "govuk-button board__button" : "btn btn--primary board__button"}
              disabled={!chosenType}
              onClick={() => setPanel({ kind: "declare", type: chosenType })}
            >
              Declare {chosenType ? `a ${chosenType}` : "an item"}
            </button>
            <p className="caption">Need another type? Ask a data engineer.</p>
            <button
              type="button"
              className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"}
              disabled={!selected}
              onClick={() => selected && openLink(selected, null)}
            >
              Draw a link…
            </button>
          </div>
        )}
        <div
          ref={surface}
          className="board__surface"
          role="group"
          aria-label="Board surface"
          onPointerMove={dragging}
          onPointerUp={endDrag}
          onPointerCancel={() => {
            drag.current = null;
            setRubber(null);
          }}
        >
          <svg className="board__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {opened.edges.map((edge) => {
              const a = positions[edge.source];
              const b = positions[edge.target];
              if (!a || !b) return null;
              return (
                <line
                  key={edge.id}
                  x1={a.x * 100}
                  y1={a.y * 100}
                  x2={b.x * 100}
                  y2={b.y * 100}
                  className={isDrawn(edge) ? "board__line board__line--drawn" : "board__line"}
                  vectorEffect="non-scaling-stroke"
                />
              );
            })}
            {rubber && positions[rubber.from] && (
              <line
                x1={positions[rubber.from]!.x * 100}
                y1={positions[rubber.from]!.y * 100}
                x2={rubber.x * 100}
                y2={rubber.y * 100}
                className="board__line board__line--rubber"
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
          {opened.edges.map((edge) => {
            const a = positions[edge.source];
            const b = positions[edge.target];
            if (!a || !b) return null;
            return (
              <span key={`label-${edge.id}`} className="board__link-label" style={{ left: `${((a.x + b.x) / 2) * 100}%`, top: `${((a.y + b.y) / 2) * 100}%` }}>
                {linkLabel(edge)}
              </span>
            );
          })}
          {opened.nodes.length === 0 && <p className="board__empty caption">A blank board. Choose a type and declare your first item.</p>}
          {opened.nodes.map((node) => (
            <BoardItem
              key={node.id}
              node={node}
              at={positions[node.id] ?? { x: 0.5, y: 0.5 }}
              drawn={drawnIds.has(node.id)}
              selected={selected === node.id}
              mayDraw={mayDraw}
              picture={pictures[node.id] ? pictureUrl(apiBaseUrl, caseId, boardId, node.id) : null}
              bearerToken={bearerToken}
              refFor={(el) => {
                if (el) itemRefs.current.set(node.id, el);
                else itemRefs.current.delete(node.id);
              }}
              onSelect={() => {
                setSelected(node.id);
                setMenu(null);
              }}
              onKeyDown={(event) => itemKeys(event, node.id)}
              onPointerDown={(event) => beginDrag(event, node.id, false)}
              onHandleDown={(event) => beginDrag(event, node.id, true)}
              onMenu={(x, y) => {
                setSelected(node.id);
                setMenu({ id: node.id, x, y });
              }}
            />
          ))}
          {menu && (
            <ItemMenu
              menu={menu}
              surface={surface.current}
              drawnAndMine={drawnIds.has(menu.id) && mayDraw && Boolean(opened.items?.[menu.id])}
              mayDraw={mayDraw}
              onClose={() => {
                const id = menu.id;
                setMenu(null);
                focusItem(id);
              }}
              onLink={() => openLink(menu.id, null)}
              onInspect={() => {
                setSelected(menu.id);
                setMenu(null);
                setPanel(null);
              }}
              onEdit={() => {
                setMenu(null);
                setPanel({ kind: "edit", id: menu.id });
              }}
              onWithdraw={() => {
                setMenu(null);
                setPanel({ kind: "withdraw", id: menu.id });
              }}
            />
          )}
        </div>
        <div className="board__side">
          {panel?.kind === "declare" && (
            <ItemForm
              title={`New ${panel.type}`}
              type={panel.type}
              entityType={entityTypes.find((t) => t.name === panel.type)}
              markings={opened.markings ?? []}
              scheme={scheme}
              govuk={govuk}
              onCancel={() => setPanel(null)}
              onSave={async (form) => {
                const at = nextPlace(positions);
                const answer = await declareItem(apiBaseUrl, bearerToken, caseId, boardId, { ...form, type: panel.type, x: at.x, y: at.y });
                if (!answer.ok) return answer.message;
                setPanel(null);
                setSaid(`${form.label} added to the board, with a watch for it.`);
                await reload();
                setSelected(answer.value.element_id);
                focusItem(answer.value.element_id);
                return null;
              }}
            />
          )}
          {panel?.kind === "edit" && byId.get(panel.id) && (
            <ItemForm
              title={`Edit ${itemLabel(byId.get(panel.id)!)}`}
              type={byId.get(panel.id)!.type}
              entityType={entityTypes.find((t) => t.name === byId.get(panel.id)!.type)}
              markings={opened.markings ?? []}
              scheme={scheme}
              govuk={govuk}
              start={byId.get(panel.id)}
              onCancel={() => setPanel(null)}
              onSave={async (form) => {
                const itemId = opened.items?.[panel.id];
                if (!itemId) return "This item cannot be edited here.";
                const answer = await editItem(apiBaseUrl, bearerToken, caseId, itemId, form);
                if (!answer.ok) return answer.message;
                setPanel(null);
                setSaid(`${form.label} changed.`);
                await reload();
                focusItem(panel.id);
                return null;
              }}
            />
          )}
          {panel?.kind === "link" && (
            <LinkForm
              from={byId.get(panel.from)}
              to={panel.to}
              items={opened.nodes.filter((n) => n.id !== panel.from)}
              linkTypes={opened.link_types ?? []}
              markings={opened.markings ?? []}
              scheme={scheme}
              govuk={govuk}
              onCancel={() => {
                const from = panel.from;
                setPanel(null);
                focusItem(from);
              }}
              onSave={async (form) => {
                const answer = await drawLink(apiBaseUrl, bearerToken, caseId, boardId, { ...form, source: panel.from });
                if (!answer.ok) return answer.message;
                setPanel(null);
                setSaid(`Link drawn: ${form.label}.`);
                await reload();
                focusItem(panel.from);
                return null;
              }}
            />
          )}
          {panel?.kind === "withdraw" && byId.get(panel.id) && (
            <div className={govuk ? "govuk-warning-text board__panel" : "board__panel panel"} role="dialog" aria-labelledby="board-withdraw-title">
              <h3 id="board-withdraw-title" className={govuk ? "govuk-heading-s" : "label"}>
                Withdraw {itemLabel(byId.get(panel.id)!)}?
              </h3>
              <p className="caption">It is taken off every board and canvas, with the links drawn to it, and its watch ends. It is never deleted: it is kept in the audit.</p>
              <div className="board__row">
                <button type="button" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn btn--danger board__button"} onClick={() => void withdraw(panel.id)}>
                  Withdraw the item
                </button>
                <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => setPanel(null)}>
                  Keep it
                </button>
              </div>
            </div>
          )}
          {!panel && selectedNode && (
            <Inspector
              node={selectedNode}
              drawn={drawnIds.has(selectedNode.id)}
              mine={selectedMine}
              markings={opened.markings ?? []}
              govuk={govuk}
              onEdit={() => setPanel({ kind: "edit", id: selectedNode.id })}
              onWithdraw={() => setPanel({ kind: "withdraw", id: selectedNode.id })}
              onLink={() => openLink(selectedNode.id, null)}
              mayDraw={mayDraw}
              onPicture={async (file, marking) => {
                const answer = await uploadPicture(apiBaseUrl, bearerToken, caseId, boardId, selectedNode.id, file, marking);
                if (!answer.ok) return answer.message;
                setSaid(`Picture added to ${itemLabel(selectedNode)}.`);
                await reload();
                return null;
              }}
            />
          )}
          <MatchesPanel
            matches={matches}
            byId={byId}
            mayDraw={mayDraw}
            govuk={govuk}
            onDecide={async (drawn, loaded, same) => {
              const answer = await decideMatch(apiBaseUrl, bearerToken, caseId, boardId, { drawn, loaded, same });
              if (!answer.ok) {
                setProblem(answer.message);
                return;
              }
              setSaid(same ? "Marked as the same: a link is kept in this case, nothing is merged." : "Marked as not the same.");
              await reload();
            }}
          />
        </div>
      </div>
      <p className="visually-hidden" role="status" aria-live="polite">
        {said}
      </p>
    </section>
  );
}

// --- an item on the surface --------------------------------------------------------------------

interface BoardItemProps {
  node: BoardNode;
  at: Position;
  drawn: boolean;
  selected: boolean;
  mayDraw: boolean;
  picture: string | null;
  bearerToken: string;
  refFor: (el: HTMLButtonElement | null) => void;
  onSelect: () => void;
  onKeyDown: (event: KeyboardEvent) => void;
  onPointerDown: (event: PointerEvent) => void;
  onHandleDown: (event: PointerEvent) => void;
  onMenu: (x: number, y: number) => void;
}

function BoardItem({ node, at, drawn, selected, mayDraw, picture, bearerToken, refFor, onSelect, onKeyDown, onPointerDown, onHandleDown, onMenu }: BoardItemProps) {
  const label = itemLabel(node);
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!picture) return;
    let url: string | null = null;
    void fetch(picture, { headers: { Authorization: `Bearer ${bearerToken}` } })
      .then((r) => (r.ok ? r.blob() : null))
      .then((blob) => {
        if (blob) {
          url = URL.createObjectURL(blob);
          setSrc(url);
        }
      })
      .catch(() => undefined);
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [picture, bearerToken]);
  return (
    <div className="board-item" data-board-item={node.id} style={{ left: `${at.x * 100}%`, top: `${at.y * 100}%` }}>
      <button
        ref={refFor}
        type="button"
        className={`board-item__body${drawn ? " board-item__body--drawn" : ""}${selected ? " board-item__body--selected" : ""}`}
        aria-pressed={selected}
        onClick={onSelect}
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onContextMenu={(event) => {
          event.preventDefault();
          onMenu(event.clientX, event.clientY);
        }}
      >
        {src && <img className="board-item__picture" src={src} alt="" />}
        <span className="board-item__kind">{node.type} </span>
        <span className="board-item__label">{label}</span>
        {/* Visible text first, so the name holds it (WCAG 2.5.3): "Person Mercer (loaded)". */}
        <span className="visually-hidden"> ({drawn ? "drawn" : "loaded"})</span>
      </button>
      {mayDraw && (
        <span className="board-item__handle" title="Drag to draw a link" aria-hidden="true" onPointerDown={onHandleDown}>
          ⟶
        </span>
      )}
    </div>
  );
}

// --- the right-click menu ------------------------------------------------------------------------

function ItemMenu({
  menu,
  surface,
  drawnAndMine,
  mayDraw,
  onClose,
  onLink,
  onInspect,
  onEdit,
  onWithdraw,
}: {
  menu: Menu;
  surface: HTMLDivElement | null;
  drawnAndMine: boolean;
  mayDraw: boolean;
  onClose: () => void;
  onLink: () => void;
  onInspect: () => void;
  onEdit: () => void;
  onWithdraw: () => void;
}) {
  const box = surface?.getBoundingClientRect();
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => first.current?.focus(), []);
  const keys = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("[role=menuitem]"));
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(at + 1) % items.length]?.focus();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(at - 1 + items.length) % items.length]?.focus();
    }
  };
  return (
    <div
      role="menu"
      aria-label="Item actions"
      className="board-menu"
      style={{ left: box ? menu.x - box.left : 0, top: box ? menu.y - box.top : 0 }}
      onKeyDown={keys}
    >
      {mayDraw && (
        <button ref={first} type="button" role="menuitem" className="board-menu__item" onClick={onLink}>
          Draw a link from here
        </button>
      )}
      <button ref={mayDraw ? undefined : first} type="button" role="menuitem" className="board-menu__item" onClick={onInspect}>
        Inspect
      </button>
      {drawnAndMine && (
        <>
          <button type="button" role="menuitem" className="board-menu__item" onClick={onEdit}>
            Edit
          </button>
          <button type="button" role="menuitem" className="board-menu__item" onClick={onWithdraw}>
            Withdraw
          </button>
        </>
      )}
    </div>
  );
}

// --- the item form (declare and edit) -------------------------------------------------------------

interface AssertedForm {
  label: string;
  marking: string;
  grading: Grading;
  sourceNote: string;
  properties: Record<string, string>;
}

function GradingFields({ grading, scheme, govuk, onChange, idPrefix }: { grading: Grading; scheme: string; govuk: boolean; onChange: (g: Grading) => void; idPrefix: string }) {
  const parts = GRADES[scheme] ?? GRADES["5x5x5"]!;
  const field = (key: "source" | "intelligence" | "handling", label: string, values: string[]) => (
    <div className={govuk ? "govuk-form-group board__grade" : "board__grade"}>
      <label htmlFor={`${idPrefix}-grade-${key}`} className={govuk ? "govuk-label" : "label"}>
        {label}
      </label>
      <select
        id={`${idPrefix}-grade-${key}`}
        className={govuk ? "govuk-select" : "input"}
        value={grading[key]}
        onChange={(e) => onChange({ ...grading, [key]: e.target.value })}
      >
        {values.map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    </div>
  );
  return (
    <fieldset className={govuk ? "govuk-fieldset" : "board__fieldset"}>
      <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "label"}>Grading ({scheme})</legend>
      <div className="board__grades">
        {field("source", "Source", parts.source)}
        {field("intelligence", "Intelligence", parts.intelligence)}
        {field("handling", "Handling", parts.handling)}
      </div>
    </fieldset>
  );
}

function AssertedFields({
  form,
  setForm,
  markings,
  scheme,
  govuk,
  idPrefix,
  labelText,
}: {
  form: AssertedForm;
  setForm: (f: AssertedForm) => void;
  markings: string[];
  scheme: string;
  govuk: boolean;
  idPrefix: string;
  labelText: string;
}) {
  return (
    <>
      <div className={govuk ? "govuk-form-group" : "board__field"}>
        <label htmlFor={`${idPrefix}-label`} className={govuk ? "govuk-label" : "label"}>
          {labelText}
        </label>
        <input
          id={`${idPrefix}-label`}
          className={govuk ? "govuk-input" : "input"}
          value={form.label}
          maxLength={200}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
        />
      </div>
      <div className={govuk ? "govuk-form-group" : "board__field"}>
        <label htmlFor={`${idPrefix}-marking`} className={govuk ? "govuk-label" : "label"}>
          Handling marking
        </label>
        <select id={`${idPrefix}-marking`} className={govuk ? "govuk-select" : "input"} value={form.marking} onChange={(e) => setForm({ ...form, marking: e.target.value })}>
          {markings.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <GradingFields grading={form.grading} scheme={scheme} govuk={govuk} idPrefix={idPrefix} onChange={(grading) => setForm({ ...form, grading })} />
      <div className={govuk ? "govuk-form-group" : "board__field"}>
        <label htmlFor={`${idPrefix}-note`} className={govuk ? "govuk-label" : "label"}>
          Source note
        </label>
        <div id={`${idPrefix}-note-hint`} className={govuk ? "govuk-hint" : "caption"}>
          Where this comes from, for whoever reads it next.
        </div>
        <textarea
          id={`${idPrefix}-note`}
          className={govuk ? "govuk-textarea" : "input board__textarea"}
          rows={2}
          aria-describedby={`${idPrefix}-note-hint`}
          value={form.sourceNote}
          onChange={(e) => setForm({ ...form, sourceNote: e.target.value })}
        />
      </div>
    </>
  );
}

function FormShell({
  title,
  govuk,
  problem,
  onSubmit,
  onCancel,
  submitLabel,
  children,
}: {
  title: string;
  govuk: boolean;
  problem: string | null;
  onSubmit: () => void;
  onCancel: () => void;
  submitLabel: string;
  children: React.ReactNode;
}) {
  const id = `board-form-${title.replace(/\W+/g, "-").toLowerCase()}`;
  const head = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const first = head.current?.parentElement?.querySelector<HTMLElement>("input, select, textarea");
    first?.focus();
  }, []);
  return (
    <form
      role="dialog"
      aria-labelledby={id}
      className={govuk ? "board__panel board__form--govuk" : "board__panel panel"}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onCancel();
        }
      }}
    >
      <h3 ref={head} id={id} className={govuk ? "govuk-heading-s" : "label"}>
        {title}
      </h3>
      {problem && (
        <div className={govuk ? "govuk-error-summary" : "board__problem-box"} role="alert">
          {govuk && <h4 className="govuk-error-summary__title">There is a problem</h4>}
          <p className={govuk ? "govuk-error-summary__body" : "board__problem"}>{problem}</p>
        </div>
      )}
      {children}
      <div className={govuk ? "govuk-button-group" : "board__row"}>
        <button type="submit" className={govuk ? "govuk-button board__button" : "btn btn--primary board__button"}>
          {submitLabel}
        </button>
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function ItemForm({
  title,
  type,
  entityType,
  markings,
  scheme,
  govuk,
  start,
  onSave,
  onCancel,
}: {
  title: string;
  type: string;
  entityType: EntityTypeShape | undefined;
  markings: string[];
  scheme: string;
  govuk: boolean;
  start?: BoardNode;
  onSave: (form: AssertedForm) => Promise<string | null>;
  onCancel: () => void;
}) {
  const drawn = start?.provenance.drawn;
  const required = (entityType?.properties ?? []).filter((p) => p.required);
  const [form, setForm] = useState<AssertedForm>({
    label: drawn?.label ?? "",
    marking: start?.handling.classification ?? markings[0] ?? "",
    grading: (drawn?.grading as Grading | undefined) ?? EMPTY_GRADE(scheme),
    sourceNote: drawn?.source_note ?? "",
    properties: Object.fromEntries(
      Object.entries((start?.properties ?? {}) as Record<string, unknown>).filter(([, v]) => typeof v === "string") as [string, string][],
    ),
  });
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [problem, setProblem] = useState<string | null>(null);
  // A type's required name is filled from what the analyst calls it, until they change it.
  const withLabel = (next: AssertedForm): AssertedForm => {
    const properties = { ...next.properties };
    for (const p of required) if (!touched.has(p.name) && (p.type ?? "string") === "string") properties[p.name] = next.label;
    return { ...next, properties };
  };
  return (
    <FormShell
      title={title}
      govuk={govuk}
      problem={problem}
      submitLabel={start ? "Save the change" : "Add to board"}
      onCancel={onCancel}
      onSubmit={() => {
        if (!form.label.trim()) return setProblem("Say what you call it.");
        if (!form.sourceNote.trim()) return setProblem("Give a source note: where this comes from.");
        const missing = required.filter((p) => !form.properties[p.name]?.trim());
        if (missing.length) return setProblem(`A ${type} needs its ${missing.map((p) => p.name.replaceAll("_", " ")).join(" and ")}.`);
        void onSave(form).then((refused) => setProblem(refused));
      }}
    >
      <AssertedFields
        form={form}
        setForm={(next) => setForm(start ? next : withLabel(next))}
        markings={markings}
        scheme={scheme}
        govuk={govuk}
        idPrefix="board-item"
        labelText="What do you call it?"
      />
      {required.map((p) => (
        <div key={p.name} className={govuk ? "govuk-form-group" : "board__field"}>
          <label htmlFor={`board-item-prop-${p.name}`} className={govuk ? "govuk-label" : "label"}>
            {p.name.replaceAll("_", " ")} (the {type}&apos;s own)
          </label>
          <input
            id={`board-item-prop-${p.name}`}
            className={govuk ? "govuk-input" : "input"}
            value={form.properties[p.name] ?? ""}
            onChange={(e) => {
              setTouched((t) => new Set(t).add(p.name));
              setForm({ ...form, properties: { ...form.properties, [p.name]: e.target.value } });
            }}
          />
        </div>
      ))}
    </FormShell>
  );
}

function LinkForm({
  from,
  to,
  items,
  linkTypes,
  markings,
  scheme,
  govuk,
  onSave,
  onCancel,
}: {
  from: BoardNode | undefined;
  to: string | null;
  items: BoardNode[];
  linkTypes: string[];
  markings: string[];
  scheme: string;
  govuk: boolean;
  onSave: (form: AssertedForm & { type: string; target: string }) => Promise<string | null>;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<AssertedForm>({ label: "", marking: markings[0] ?? "", grading: EMPTY_GRADE(scheme), sourceNote: "", properties: {} });
  const [target, setTarget] = useState<string>(to ?? items[0]?.id ?? "");
  const [type, setType] = useState<string>(linkTypes[0] ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <FormShell
      title={`New link from ${from ? itemLabel(from) : "the item"}`}
      govuk={govuk}
      problem={problem}
      submitLabel="Draw the link"
      onCancel={onCancel}
      onSubmit={() => {
        if (!target) return setProblem("Choose the item it links to.");
        if (!type) return setProblem("Choose what links them.");
        if (!form.sourceNote.trim()) return setProblem("Give a source note: where this comes from.");
        const label = form.label.trim() || type.toLowerCase().replaceAll("_", " ");
        void onSave({ ...form, label, type, target }).then((refused) => setProblem(refused));
      }}
    >
      <div className={govuk ? "govuk-form-group" : "board__field"}>
        <label htmlFor="board-link-to" className={govuk ? "govuk-label" : "label"}>
          Links to
        </label>
        <select id="board-link-to" className={govuk ? "govuk-select" : "input"} value={target} onChange={(e) => setTarget(e.target.value)}>
          {items.map((n) => (
            <option key={n.id} value={n.id}>
              {itemLabel(n)} ({n.type})
            </option>
          ))}
        </select>
      </div>
      <fieldset className={govuk ? "govuk-fieldset" : "board__fieldset"}>
        <legend className={govuk ? "govuk-fieldset__legend govuk-fieldset__legend--s" : "label"}>What links them?</legend>
        <div className={govuk ? "govuk-radios govuk-radios--small" : "board__radios"}>
          {linkTypes.map((t) => (
            <div key={t} className={govuk ? "govuk-radios__item" : "board__radio"}>
              <input id={`board-link-type-${t}`} className={govuk ? "govuk-radios__input" : undefined} type="radio" name="board-link-type" checked={type === t} onChange={() => setType(t)} />
              <label htmlFor={`board-link-type-${t}`} className={govuk ? "govuk-label govuk-radios__label" : undefined}>
                {t.toLowerCase().replaceAll("_", " ")}
              </label>
            </div>
          ))}
        </div>
      </fieldset>
      <AssertedFields form={form} setForm={setForm} markings={markings} scheme={scheme} govuk={govuk} idPrefix="board-link" labelText="What does the link say? (optional)" />
    </FormShell>
  );
}

// --- the inspector -------------------------------------------------------------------------------

function Inspector({
  node,
  drawn,
  mine,
  mayDraw,
  markings,
  govuk,
  onEdit,
  onWithdraw,
  onLink,
  onPicture,
}: {
  node: BoardNode;
  drawn: boolean;
  mine: boolean;
  mayDraw: boolean;
  markings: string[];
  govuk: boolean;
  onEdit: () => void;
  onWithdraw: () => void;
  onLink: () => void;
  onPicture: (file: File, marking: string) => Promise<string | null>;
}) {
  const assertion = node.provenance.drawn;
  const [file, setFile] = useState<File | null>(null);
  const [marking, setMarking] = useState(markings[0] ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const rows: [string, string][] = assertion
    ? [
        ["Drawn by", assertion.asserted_by],
        ["Grading", `${assertion.grading.source}${assertion.grading.intelligence}${assertion.grading.handling} (${assertion.grading.scheme ?? "5x5x5"})`],
        ["Marking", node.handling.classification],
        ["Source note", assertion.source_note ?? "A document of the case"],
      ]
    : [
        ["From", "A dataset this case reads: a live reference, not editable here"],
        ["Marking", node.handling.classification],
      ];
  return (
    <section className={govuk ? "board__panel" : "board__panel panel"} aria-labelledby="board-inspector-title">
      <h3 id="board-inspector-title" className={govuk ? "govuk-heading-s" : "label"}>
        {itemLabel(node)}
      </h3>
      <span className={govuk ? `govuk-tag ${drawn ? "govuk-tag--yellow" : "govuk-tag--grey"}` : `board-tag${drawn ? " board-tag--drawn" : ""}`}>
        {drawn ? "Drawn" : "Loaded"}
      </span>
      <dl className={govuk ? "govuk-summary-list govuk-summary-list--no-border" : "board__facts"}>
        {rows.map(([k, v]) => (
          <div key={k} className={govuk ? "govuk-summary-list__row" : "board__fact"}>
            <dt className={govuk ? "govuk-summary-list__key" : "caption"}>{k}</dt>
            <dd className={govuk ? "govuk-summary-list__value" : "board__fact-value"}>{v}</dd>
          </div>
        ))}
      </dl>
      <div className={govuk ? "govuk-button-group" : "board__row"}>
        {mayDraw && (
          <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={onLink}>
            Draw a link from here
          </button>
        )}
        {mine && (
          <>
            <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={onEdit}>
              Edit {itemLabel(node)}
            </button>
            <button type="button" className={govuk ? "govuk-button govuk-button--warning board__button" : "btn board__button board__danger"} onClick={onWithdraw}>
              Withdraw {itemLabel(node)}
            </button>
          </>
        )}
      </div>
      {mine && (
        <form
          className="board__picture"
          onSubmit={(e) => {
            e.preventDefault();
            if (!file) return setProblem("Choose a picture: a png, jpeg, webp or gif.");
            void onPicture(file, marking).then((refused) => {
              setProblem(refused);
              if (!refused) setFile(null);
            });
          }}
        >
          <div className={govuk ? "govuk-form-group" : "board__field"}>
            <label htmlFor="board-picture-file" className={govuk ? "govuk-label" : "label"}>
              Picture of {itemLabel(node)}
            </label>
            <input
              id="board-picture-file"
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.gif"
              className={govuk ? "govuk-file-upload" : "input"}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className={govuk ? "govuk-form-group" : "board__field"}>
            <label htmlFor="board-picture-marking" className={govuk ? "govuk-label" : "label"}>
              The picture&apos;s marking
            </label>
            <select id="board-picture-marking" className={govuk ? "govuk-select" : "input"} value={marking} onChange={(e) => setMarking(e.target.value)}>
              {markings.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          {problem && (
            <p role="alert" className={govuk ? "govuk-error-message" : "board__problem"}>
              {problem}
            </p>
          )}
          <button type="submit" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"}>
            Add the picture
          </button>
        </form>
      )}
    </section>
  );
}

// --- Looks like a loaded item -------------------------------------------------------------------

function MatchesPanel({
  matches,
  byId,
  mayDraw,
  govuk,
  onDecide,
}: {
  matches: MatchSuggestions | null;
  byId: Map<string, BoardNode>;
  mayDraw: boolean;
  govuk: boolean;
  onDecide: (drawn: string, loaded: string, same: boolean) => Promise<void>;
}) {
  const found = matches?.suggestions ?? [];
  return (
    <section className={govuk ? "board__panel" : "board__panel panel"} aria-labelledby="board-matches-title">
      <h3 id="board-matches-title" className={govuk ? "govuk-heading-s" : "label"}>
        Looks like a loaded item
      </h3>
      {found.length === 0 ? (
        <p className="caption">Nothing drawn here looks like a loaded item.</p>
      ) : (
        <ul className="board__matches" aria-label="Looks like a loaded item">
          {found.map((m) => {
            const drawn = byId.get(m.drawn);
            const drawnName = drawn ? itemLabel(drawn) : "A drawn item";
            const loadedName = itemLabel(m.loaded);
            return (
              <li key={`${m.drawn}-${m.loaded.id}`} className="board__match">
                <span>
                  {drawnName} looks like {loadedName} ({m.why}, {Math.round(m.score * 100)}%)
                </span>
                <span className={govuk ? "govuk-tag govuk-tag--grey" : "board-tag"}>Suggested</span>
                {mayDraw && (
                  <span className="board__row">
                    <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => void onDecide(m.drawn, m.loaded.id, true)}>
                      Same: {drawnName} is {loadedName}
                    </button>
                    <button type="button" className={govuk ? "govuk-button govuk-button--secondary board__button" : "btn board__button"} onClick={() => void onDecide(m.drawn, m.loaded.id, false)}>
                      Not the same: {drawnName} and {loadedName}
                    </button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {matches?.more && <p className="caption">More looked alike than are shown here.</p>}
      <p className="caption">A suggestion does nothing by itself. Same keeps a link in this case; nothing is merged.</p>
    </section>
  );
}
