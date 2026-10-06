// The protective marking of what is on screen (ADR-097 step 1, design review item 16, Amendment 1):
// a strip of its own above everything, neutral, never colour-coded. It says the highest
// classification among the nodes and links in the view, in the deployment's own scheme's order;
// the analyst's clearance stays in the account button.

/** The highest of `classifications` in `order` (lowest first); the scheme's lowest for none. A
 * marking the scheme does not know is shown as itself, ranked above all, rather than hidden. */
export function highestMarking(classifications: readonly string[], order: readonly string[]): string {
  let best: string | null = null;
  let rank = -1;
  for (const marking of classifications) {
    const at = order.indexOf(marking);
    const r = at === -1 ? Number.MAX_SAFE_INTEGER : at;
    if (r > rank) {
      rank = r;
      best = marking;
    }
  }
  return best ?? order[0] ?? "";
}

export function ClassificationStrip({ marking }: { marking: string }) {
  return (
    <div role="note" aria-label="Protective marking" className="classification-strip">
      {marking}
    </div>
  );
}
