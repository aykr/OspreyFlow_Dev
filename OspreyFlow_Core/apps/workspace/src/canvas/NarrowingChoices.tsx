import type { NarrowingOption } from "./expansionGate";
import { linkTypeName, type NamedType } from "./linkLabel";
import type { PreviewCount } from "./nodeGestures";

/** What a relationship would add, as both expansion prompts say it. */
export function wouldAddFigure(count: PreviewCount): string {
  return count === "unavailable" ? "count unavailable" : count.toLocaleString("en-GB");
}

/**
 * *Expand by one relationship instead:* each type the node could be expanded by, named by its label (rule 7)
 * with what it would add, largest first. Shared by the large expansion's prompt and the cap's refusal, so the
 * two say it the same way. Nothing when there is no type to offer.
 */
export function NarrowingChoices({
  options,
  edgeTypes,
  onChooseType,
}: {
  options: readonly NarrowingOption[];
  edgeTypes: readonly NamedType[];
  onChooseType: (edgeType: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    <>
      <span>Expand by one relationship instead:</span>
      {options.map((option) => (
        <button key={option.edgeType} type="button" className="radial-menu__item" onClick={() => onChooseType(option.edgeType)}>
          {linkTypeName(option.edgeType, edgeTypes)} ({wouldAddFigure(option.wouldAdd)})
        </button>
      ))}
    </>
  );
}
