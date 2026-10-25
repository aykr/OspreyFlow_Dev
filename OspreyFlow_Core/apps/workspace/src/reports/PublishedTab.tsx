// The Published tab (ADR-113 stage 5): what a Reports Viewer reads. A published pack is shown
// read-only, each item under its own marking, with what is withheld from this reader said in a sentence with no number.
import { useEffect, useState } from "react";

import type { PublishedPack, PublishedPackSummary } from "../../../../packages/schemas/generated";
import { Button } from "../design/primitives";
import type { ReportsApi } from "./api";
import { ExportControl } from "./ExportControl";
import { PackItemView } from "./PackItemView";
import { formatDay, WITHHELD_ITEMS_SENTENCE } from "./packText";
import { getPublished, listPublished } from "./packsApi";

export interface PublishedTabProps {
  api: ReportsApi;
  canExport: boolean;
  print?: (html: string) => void;
}

export function PublishedTab({ api, canExport, print }: PublishedTabProps) {
  const [list, setList] = useState<PublishedPackSummary[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [pack, setPack] = useState<PublishedPack | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listPublished(api).then((l) => live && setList(l)).catch((e: Error) => live && setProblem(e.message));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken, api.investigationId]);

  async function open(packId: string) {
    setChosen(packId);
    setProblem(null);
    try {
      setPack(await getPublished(api, packId));
    } catch (e) {
      setPack(null);
      setProblem((e as Error).message);
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--sp-16)", display: "grid", gridTemplateColumns: "minmax(16rem, 22rem) 1fr", gap: "var(--sp-16)", alignContent: "start", alignItems: "start" }}>
      <section aria-label="Published packs" style={{ display: "grid", gap: "var(--sp-8)" }}>
        <h3 className="value" style={{ margin: 0 }}>Published packs</h3>
        {list === null && !problem && <p className="label" style={{ margin: 0 }}>Reading the published packs…</p>}
        {list?.length === 0 && <p className="label" style={{ margin: 0 }}>No pack has been published in this case yet.</p>}
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
          {(list ?? []).map((p) => (
            <li key={p.pack_id}>
              <Button aria-pressed={chosen === p.pack_id} onClick={() => void open(p.pack_id)}>
                {`${p.title} · Version ${p.version}, ${formatDay(p.published_at)}`}
              </Button>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Published pack" style={{ display: "grid", gap: "var(--sp-12)", alignContent: "start" }}>
        {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
        {!pack && !problem && <p className="label" style={{ margin: 0 }}>Choose a published pack to read it.</p>}
        {pack && (
          <>
            <h3 style={{ margin: 0 }}>{pack.title}</h3>
            <p className="label" style={{ margin: 0 }}>{`Version ${pack.version}, published ${formatDay(pack.published_at)} by ${pack.published_by_name ?? pack.published_by}`}</p>
            {pack.marking && <p className="label" style={{ margin: 0 }}>{`Marked ${pack.marking}`}</p>}
            {pack.withheld && <p style={{ margin: 0 }}>{WITHHELD_ITEMS_SENTENCE}</p>}
            {pack.items.map((item) => (
              <PackItemView key={item.id} item={item} />
            ))}
            {canExport && <ExportControl api={api} packId={pack.pack_id} print={print} />}
          </>
        )}
      </section>
    </div>
  );
}
