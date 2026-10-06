// An entity type as the canvas draws it (ADR-097 step 1, design review item 4): its shape in its
// channel's colour, then its name, so the Inspector's header reads as the node does.
import { cachedNodeSvgDataUri, type NodeShape } from "../color/nodeVisual";
import { BORDER_SUBTLE_DARK_HEX, resolveChannelHex } from "../color/tokens";
import type { EntityVisual } from "../ontology/schema";

export function TypeChip({ type, visual }: { type: string; visual?: EntityVisual }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--sp-4)" }}>
      {visual && (
        <img
          alt=""
          width={14}
          height={14}
          src={cachedNodeSvgDataUri({
            shape: visual.shape as NodeShape,
            fillHex: resolveChannelHex(visual.channel),
            strokeHex: BORDER_SUBTLE_DARK_HEX,
            strokeStyle: "solid",
          })}
        />
      )}
      <span>{type}</span>
    </span>
  );
}
