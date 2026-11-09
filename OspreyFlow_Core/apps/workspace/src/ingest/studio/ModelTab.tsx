// 1 Model (ADR-140 decision 4), thin until phase 5: the domain model (`TargetModel` in the code and
// spec 01; ADR-140 Amendment 9 decision 1 names it on screen) is, for now, the case's packs
// over the POLE core (ADR-126). Phase 5 makes it the dataset's own, versioned, with its extensions,
// reference lists, and draft and live versions.
import type { DomainPack } from "../../investigation/cases";
import { modelInWords } from "./packs";

export function ModelTab({ datasetName, packs }: { datasetName: string; packs: readonly DomainPack[] | undefined }) {
  return (
    <section aria-label="Domain model" style={{ padding: "var(--sp-16)", display: "grid", gap: "var(--sp-8)", maxWidth: 720 }}>
      <h2 style={{ margin: 0, fontSize: "var(--fs-16)" }}>Domain model for {datasetName}</h2>
      <p style={{ margin: 0 }}>{modelInWords(packs)}</p>
      <p className="label" style={{ margin: 0 }}>
        Every pipeline that loads this dataset maps into this model. The POLE core is always on; the
        packs are chosen for the case. A model of the dataset&apos;s own, with its extensions, reference
        lists and versions, comes with the next stage of the Studio.
      </p>
    </section>
  );
}
