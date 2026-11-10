// *Show as BPMN* (`06_DECISIONS.md` ADR-146 decision 3): the rule's stored BPMN 2.0 process drawn
// read-only, from the `.bpmn` the Conduit exports. Rules mounts it in the rule editor (L2.11) with
// the file it fetched; this component fetches nothing.
//
// A button opens the drawing in a dialog: focus moves to *Close*, is held inside, and Escape or
// *Close* shuts it and gives focus back to the button (`keyboard/rule-standards.spec.ts`). The
// three elements are drawn and also listed in words, so the drawing is read without the picture.
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { type BpmnDrawing, drawingWords, readBpmnDrawing } from "./bpmnDrawing";
import "./showAsBpmn.css";

export interface ShowAsBpmnProps {
  /** The rule's `.bpmn`, as `GET …/rules/{id}/export.bpmn` gave it. */
  bpmnXml: string;
}

/** A name broken into lines of at most `width` characters, at spaces, for the task's box. */
function lines(name: string, width: number, most: number): string[] {
  const out: string[] = [];
  for (const word of name.split(/\s+/)) {
    const last = out[out.length - 1];
    if (last !== undefined && `${last} ${word}`.length <= width)
      out[out.length - 1] = `${last} ${word}`;
    else out.push(word);
  }
  if (out.length <= most) return out;
  return [
    ...out.slice(0, most - 1),
    `${out
      .slice(most - 1)
      .join(" ")
      .slice(0, width - 1)}…`,
  ];
}

function Drawing({ drawing }: { drawing: BpmnDrawing }) {
  const task = lines(drawing.task.name, 18, 3);
  return (
    <svg
      className="show-as-bpmn__svg"
      viewBox="0 0 520 170"
      role="img"
      aria-label={drawingWords(drawing)}
    >
      <defs>
        <marker
          id="show-as-bpmn-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="8"
          markerHeight="8"
          orient="auto"
        >
          <path d="M0,0 L10,5 L0,10 z" className="show-as-bpmn__arrowhead" />
        </marker>
      </defs>
      <circle className="show-as-bpmn__start" cx="60" cy="70" r="22" />
      <line
        className="show-as-bpmn__flow"
        x1="82"
        y1="70"
        x2="178"
        y2="70"
        markerEnd="url(#show-as-bpmn-arrow)"
      />
      <rect
        className="show-as-bpmn__task"
        x="180"
        y="20"
        width="160"
        height="100"
        rx="10"
      />
      <g className="show-as-bpmn__table" aria-hidden="true">
        <rect x="190" y="28" width="22" height="16" />
        <line x1="190" y1="34" x2="212" y2="34" />
        <line x1="198" y1="34" x2="198" y2="44" />
      </g>
      <text
        className="show-as-bpmn__label"
        x="260"
        y={78 - (task.length - 1) * 8}
        textAnchor="middle"
      >
        {task.map((line, n) => (
          <tspan key={n} x="260" dy={n === 0 ? 0 : 16}>
            {line}
          </tspan>
        ))}
      </text>
      <line
        className="show-as-bpmn__flow"
        x1="340"
        y1="70"
        x2="436"
        y2="70"
        markerEnd="url(#show-as-bpmn-arrow)"
      />
      <circle className="show-as-bpmn__end" cx="460" cy="70" r="22" />
      <text className="show-as-bpmn__label" x="60" y="118" textAnchor="middle">
        Start
      </text>
      <text className="show-as-bpmn__label" x="460" y="118" textAnchor="middle">
        End
      </text>
    </svg>
  );
}

function BpmnDialog({
  bpmnXml,
  onClose,
}: {
  bpmnXml: string;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const drawing = readBpmnDrawing(bpmnXml);

  useLayoutEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
      }
    };
    const onFocusIn = (e: FocusEvent) => {
      if (
        ref.current &&
        e.target instanceof Node &&
        !ref.current.contains(e.target)
      ) {
        ref.current.querySelector<HTMLElement>("button")?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    ref.current?.querySelector<HTMLElement>("button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
    };
  }, []);

  return (
    <div
      ref={ref}
      className="show-as-bpmn"
      role="dialog"
      aria-modal="true"
      aria-labelledby="show-as-bpmn-title"
      onKeyDown={(e) => {
        // One control: Tab and Shift+Tab stay on it.
        if (e.key === "Tab") {
          e.preventDefault();
          ref.current?.querySelector<HTMLElement>("button")?.focus();
        }
      }}
    >
      <div className="show-as-bpmn__head">
        <h2 id="show-as-bpmn-title" className="show-as-bpmn__title">
          {drawing ? `${drawing.rule} as BPMN 2.0` : "This rule as BPMN 2.0"}
        </h2>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>
      {drawing ? (
        <>
          <p className="show-as-bpmn__why">
            Read-only. This is how the rule is stored: a process of three
            elements, with its conditions in a DMN decision table. Export gives
            both files.
          </p>
          <Drawing drawing={drawing} />
          <ol
            className="show-as-bpmn__elements"
            aria-label="The process's elements, in order"
          >
            <li>
              <strong>Start event:</strong> {drawing.start.name}
            </li>
            <li>
              <strong>Business-rule task:</strong> {drawing.task.name}, which
              calls the rule's decision table
            </li>
            <li>
              <strong>End event:</strong> {drawing.end.name}
            </li>
          </ol>
        </>
      ) : (
        <p className="show-as-bpmn__why" role="status">
          This rule's stored file is not a process OspreyFlow runs, so it is not
          drawn.
        </p>
      )}
    </div>
  );
}

export function ShowAsBpmn({ bpmnXml }: ShowAsBpmnProps) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const closed = useRef(false);
  // Focus goes back to the button once the dialog has gone: while it is open, its own guard would
  // pull focus straight back inside it.
  useEffect(() => {
    if (!open && closed.current) {
      closed.current = false;
      button.current?.focus();
    }
  }, [open]);
  return (
    <>
      <button
        ref={button}
        type="button"
        className="btn"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        Show as BPMN
      </button>
      {open && (
        <BpmnDialog
          bpmnXml={bpmnXml}
          onClose={() => {
            closed.current = true;
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
