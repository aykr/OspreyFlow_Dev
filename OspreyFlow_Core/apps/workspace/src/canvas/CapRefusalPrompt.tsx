import { Popover } from "../design/primitives/Popover";
import type { LimitExceeded } from "../workingset/models";
import { figure as capFigure } from "../workingset/ViewOverCapDialog";
import type { NarrowingOption } from "./expansionGate";
import type { NamedType } from "./linkLabel";
import { NarrowingChoices } from "./NarrowingChoices";

export interface CapRefusalPromptProps {
  x: number;
  y: number;
  /** The Conduit's typed refusal (rule 2): the cap, the figure it would be, and its options. */
  refused: LimitExceeded;
  /** Relationship types to expand by instead, each with what it would add: the cap's *filter*. */
  options: NarrowingOption[];
  /** The node being expanded, as the canvas names it. */
  subject?: string;
  onChooseType: (edgeType: string) => void;
  /** The cap's *save_as_view*: a smaller view of the case, private, opened as the lens (ADR-144). */
  onSaveSmallerView?: () => void;
  /** The cap's *promote_to_batch* (ADR-151): case-b's, drawn third when given. */
  onRunAsBatch?: () => void;
  onCancel: () => void;
  /** The case's link types: a relationship is named by its label, never its stored id (rule 7). */
  edgeTypes?: readonly NamedType[];
}

/**
 * Shown when the working set's cap refuses an expansion (rule 2; spec/00 §4: the Glass offers the
 * cap's explicit choices, never a cut). Nothing has been added. The choices, in the order spec/00
 * names them: expand by one relationship instead (*filter*), save a smaller view of the case
 * (*save_as_view*), and run it as a batch (*promote_to_batch*, ADR-151, when the canvas is given one).
 */
export function CapRefusalPrompt({
  x,
  y,
  refused,
  options,
  subject,
  onChooseType,
  onSaveSmallerView,
  onRunAsBatch,
  onCancel,
  edgeTypes = [],
}: CapRefusalPromptProps) {
  return (
    <Popover x={x} y={y} onClose={onCancel} role="alertdialog" label="Too large to expand" modal>
      <div className="expansion-prompt">
        {subject && (
          <span>
            Expanding <strong>{subject}</strong> was refused.
          </span>
        )}
        <strong className="value">{capFigure(refused)}</strong>
        <span>Nothing has been added.</span>
        <NarrowingChoices options={options} edgeTypes={edgeTypes} onChooseType={onChooseType} />
        {onSaveSmallerView && (
          <button type="button" className="radial-menu__item" onClick={onSaveSmallerView}>
            Save a smaller view…
          </button>
        )}
        {onRunAsBatch && (
          <>
            <span>Or run the whole expansion on the server as a batch job; its result opens as a saved view when it finishes.</span>
            <button type="button" className="radial-menu__item" onClick={onRunAsBatch}>
              Run as a batch job
            </button>
          </>
        )}
        <button type="button" className="radial-menu__item" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </Popover>
  );
}
