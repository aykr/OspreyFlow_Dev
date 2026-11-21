// The domain model in words, from the packs the case carries (ADR-126; ADR-140 decision 4 makes
// them the dataset's in phase 5). The labels are the Studio's catalogue's (`DOMAIN_PACKS`), so the
// Model tab and the case's own pack setting say the same thing.
import { DOMAIN_PACKS, type DomainPack } from "../../investigation/cases";

/** The POLE core, always on, then each pack the case carries, in the catalogue's order. */
export function modelInWords(packs: readonly DomainPack[] | undefined): string {
  const named = DOMAIN_PACKS.filter((p) => (packs ?? []).includes(p.name)).map((p) => p.label);
  return ["POLE core", ...named].join(" + ");
}
