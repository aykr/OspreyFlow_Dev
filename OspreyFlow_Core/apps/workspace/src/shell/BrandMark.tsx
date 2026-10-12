// The mark and the wordmark's chrome short form (DESIGN.md §1, §2; ADR-097 conflict 5): the solid
// cut, which is the cut at 20px and below, filled (never outlined), in brass, the one accent the
// logo may use; then "Osprey" at 700. Not locked together as one image (DESIGN.md §1, prohibited).
// ADR-115 E2: the mesh cut above 20px (the welcome page's 28px mark) and the solid cut as parts.
const SOLID = "M4 6L25 11L45 26L25.5 30L9 42Z";
const MESH = [
  "M4.9 6.7L6.4 17.2L23.9 11.1Z",
  "M6.8 17.9L24.3 19.9L24.2 11.7Z",
  "M6.6 18.6L8 29.1L24.2 20.7Z",
  "M8.4 30.1L9.4 41L24.4 21.2Z",
  "M9.8 41.2L24.4 30.2L24.7 21.5Z",
  "M25.6 11.9L26.2 29.2L43.9 25.7Z",
];

/** The solid cut: at 20px and below (DESIGN.md §1). */
export function SolidMark({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 48 48" className={className} fill="currentColor">
      <path d={SOLID} />
    </svg>
  );
}

/** The mesh cut: above 20px only (DESIGN.md §1, "the mesh cut below 20px" is prohibited). */
export function MeshMark({ size }: { size: number }) {
  if (size <= 20) throw new Error(`the mesh cut is for marks above 20px, not ${size}px (DESIGN.md §1)`);
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 48 48" fill="currentColor">
      {MESH.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}

export function BrandMark() {
  return (
    <span className="brand-mark">
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 48 48">
        <path d={SOLID} fill="var(--brass)" />
      </svg>
      <span className="brand-mark__name">Osprey</span>
    </span>
  );
}
