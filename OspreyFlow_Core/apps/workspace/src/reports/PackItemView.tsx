// One pack item as the Glass shows it (ADR-113 stage 5): a banner with the item's OWN marking at
// its top, then its content. The Packs tab adds its buttons through `children`; the Published tab
// adds none, which is what makes it read-only.
import type { ReactNode } from "react";

import type { PackItem } from "../../../../packages/schemas/generated";
import { KIND_LABEL, formatDay, itemShortTitle } from "./packText";
import { TrendChart } from "./TrendChart";

function Content({ item }: { item: PackItem }) {
  if (item.kind === "trend" && item.trend) {
    return (
      <>
        <h4 style={{ margin: 0 }}>{item.trend.definition.title}</h4>
        <p className="label" style={{ margin: 0 }}>{`As at ${formatDay(item.trend.as_of)}`}</p>
        <TrendChart figures={item.trend} />
      </>
    );
  }
  if (item.kind === "assessment" && item.assessment) {
    return (
      <>
        <p style={{ margin: 0 }}>{item.assessment.statement}</p>
        <p className="label" style={{ margin: 0 }}>{`Probability band: ${item.assessment.probability_band}`}</p>
      </>
    );
  }
  if (item.kind === "entity" && item.entity) {
    return (
      <>
        <p className="value" style={{ margin: 0 }}>{item.entity.name}</p>
        <p className="label" style={{ margin: 0 }}>{item.entity.entity_type}</p>
        <p style={{ margin: 0 }}>{item.entity.caption}</p>
      </>
    );
  }
  return <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{item.note ?? ""}</p>;
}

export function PackItemView({ item, children, replacedNote }: { item: PackItem; children?: ReactNode; replacedNote?: boolean }) {
  return (
    <article
      aria-label={`${KIND_LABEL[item.kind]}: ${itemShortTitle(item)}`}
      style={{ border: "1px solid var(--border-subtle)", display: "grid", gap: "var(--sp-8)", alignContent: "start" }}
    >
      <div className="label" style={{ padding: "var(--sp-4) var(--sp-12)", borderBottom: "1px solid var(--border-subtle)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {`Marked ${item.marking}`}
      </div>
      <div style={{ padding: "0 var(--sp-12) var(--sp-12)", display: "grid", gap: "var(--sp-8)" }}>
        <Content item={item} />
        {replacedNote && item.replaced_at && <p className="label" style={{ margin: 0 }}>{`Replaced ${formatDay(item.replaced_at)}`}</p>}
        {children && <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>{children}</div>}
      </div>
    </article>
  );
}
