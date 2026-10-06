// The mark and the wordmark's chrome short form (DESIGN.md §1, §2; ADR-097 conflict 5): the solid
// cut, which is the cut at 20px and below, filled (never outlined), in brass, the one accent the
// logo may use; then "Osprey" at 700. Not locked together as one image (DESIGN.md §1, prohibited).
export function BrandMark() {
  return (
    <span className="brand-mark">
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 48 48">
        <path d="M4 6L25 11L45 26L25.5 30L9 42Z" fill="var(--brass)" />
      </svg>
      <span className="brand-mark__name">Osprey</span>
    </span>
  );
}
