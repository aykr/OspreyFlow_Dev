// What the canvas says to assistive technology when keyboard focus moves to a node (GDS remediation
// plan A2; WCAG 4.1.3 Status Messages): its name as the canvas draws it, its type, and how many links
// it has on the canvas — "OKAFOR, Callum, Person, 12 links". Read from a polite live region in
// `GlassCanvas.tsx`, so a screen reader hears where it is without the focus leaving the canvas.
export function focusAnnouncement(label: string, type: string, links: number): string {
  const name = label.trim() || type;
  return `${name}, ${type}, ${links.toLocaleString("en-GB")} link${links === 1 ? "" : "s"}`;
}
