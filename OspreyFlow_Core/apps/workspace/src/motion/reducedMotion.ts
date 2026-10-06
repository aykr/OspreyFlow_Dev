// Whether the person has asked their system for reduced motion (`02_GLASS_FRONTEND.md` §3.4, DESIGN.md
// §7). Read each time it is needed, so a change in the system setting takes effect at the next move.
export function prefersReducedMotion(): boolean {
  if (typeof globalThis.matchMedia !== "function") return false;
  return globalThis.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
