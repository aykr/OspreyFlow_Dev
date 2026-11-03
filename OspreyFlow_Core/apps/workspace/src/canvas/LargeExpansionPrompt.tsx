import { Popover } from "../design/primitives/Popover";
import { linkTypeName, type NamedType } from "./linkLabel";
import type { NarrowingOption } from "./expansionGate";
import { EXPANSION_CONFIRM_ABOVE } from "./expansionGate";
import type { PreviewCount } from "./nodeGestures";

export interface LargeExpansionPromptProps {
  x: number;
  y: number;
  wouldAdd: PreviewCount;
  options: NarrowingOption[];
  /** The node being expanded, as the canvas names it. */
  subject?: string;
  /** The one relationship being expanded by, or `null` for every one. */
  relationship?: string | null;
  onChooseType: (edgeType: string) => void;
  onChooseAll: () => void;
  onCancel: () => void;
  /** The case's link types: a relationship is named by its label, never its stored id (rule 7). */
  edgeTypes?: readonly NamedType[];
}

function figure(count: PreviewCount): string {
  return count === "unavailable"
    ? "count unavailable"
    : count.toLocaleString("en-GB");
}

/**
 * Shown instead of a very large expansion. Nothing is added until the analyst chooses: a
 * relationship type to expand by, everything, or nothing.
 */
export function LargeExpansionPrompt({
  x,
  y,
  wouldAdd,
  options,
  subject,
  relationship = null,
  onChooseType,
  onChooseAll,
  onCancel,
  edgeTypes = [],
}: LargeExpansionPromptProps) {
  const named = (type: string) => linkTypeName(type, edgeTypes);
  const inSentence = (type: string) => {
    const name = named(type);
    return name.charAt(0).toLowerCase() + name.slice(1);
  };
  return (
    <Popover x={x} y={y} onClose={onCancel}>
      <div
        role="alertdialog"
        aria-label="Large expansion"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--sp-6)",
          minWidth: 280,
        }}
      >
        {subject && (
          <span>
            Expanding <strong>{subject}</strong> by{" "}
            {relationship ? inSentence(relationship) : "every relationship"}.
          </span>
        )}
        <strong className="value">
          {wouldAdd === "unavailable"
            ? "The size of this expansion could not be counted."
            : `This would add ${figure(wouldAdd)} nodes, more than ${EXPANSION_CONFIRM_ABOVE.toLocaleString("en-GB")}.`}
        </strong>
        {wouldAdd === "unavailable" && <span>Nothing has been added.</span>}
        {options.length > 0 && <span>Expand by one relationship instead:</span>}
        {options.map((option) => (
          <button
            key={option.edgeType}
            type="button"
            className="radial-menu__item"
            onClick={() => onChooseType(option.edgeType)}
          >
            {named(option.edgeType)} ({figure(option.wouldAdd)})
          </button>
        ))}
        <button
          type="button"
          className="radial-menu__item"
          onClick={onChooseAll}
        >
          Add all {wouldAdd === "unavailable" ? "of them" : figure(wouldAdd)}
        </button>
        <button type="button" className="radial-menu__item" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </Popover>
  );
}
