// Admin › Demo packs (ADR-114 Amendment 5; ADR-145 decision 5). Behind `administer_system`.
import { useEffect, useState } from "react";

import type { DemoPackStatus } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives";
import { listDemoPacks, type AdminApi } from "../api";

/** The demo packs (ADR-114 Amendment 5, "Show and explain"): what each shows, its licence and
 * credit, whether it is loaded, and the command that adds it on the host. The Glass runs nothing. */
export function DemoPacks({ api }: { api: AdminApi }) {
  const [packs, setPacks] = useState<DemoPackStatus[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState<{ id: string; said: string } | null>(null);
  useEffect(() => {
    listDemoPacks(api).then(setPacks).catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!packs) return <p className="label">Reading the demo packs…</p>;
  const copy = (pack: DemoPackStatus) =>
    void Promise.resolve()
      .then(() => navigator.clipboard.writeText(pack.command))
      .then(() => setCopied({ id: pack.id, said: "Copied. Run it in a terminal on the machine OspreyFlow runs on." }))
      .catch(() => setCopied({ id: pack.id, said: "Your browser would not let the page copy; select the command and copy it." }));
  return (
    <>
      <p className="label" style={{ margin: 0 }}>
        A demo pack is added on the machine OspreyFlow runs on, with the command shown — this page never runs it. Each loads
        into a case of its own, with whoever adds it as its Author.
      </p>
      {packs.map((pack) => (
        <article
          key={pack.id}
          aria-label={pack.title}
          style={{ border: "1px solid var(--border-subtle)", padding: "var(--sp-12)", display: "grid", gap: "var(--sp-6)" }}
        >
          <h3 className="value" style={{ margin: 0 }}>{pack.title}</h3>
          {pack.real_data && (
            <p role="note" style={{ margin: 0 }}>
              <strong>Real personal data.</strong> Real people&apos;s email, not made up. The command shows
              what it is and asks you to accept it before anything is loaded.
            </p>
          )}
          <p style={{ margin: 0 }}>{pack.shows}</p>
          <p className="label" style={{ margin: 0 }}>
            {`Licence: ${pack.licence}`}
            {pack.attribution ? ` · Credit: ${pack.attribution}` : ""}
          </p>
          <p className="label" style={{ margin: 0 }}>
            {pack.loaded_case_id ? `Loaded, in “${pack.case_name}”.` : "Not in any case you can open."}
          </p>
          {pack.source_page && (
            <p className="label" style={{ margin: 0 }}>
              <a href={pack.source_page} target="_blank" rel="noreferrer">{`Download ${pack.title.split(" ")[0]}'s file`}</a>
              {pack.size_bytes ? ` (${Math.round(pack.size_bytes / 1e6)} MB), then give its path in the command.` : ""}
            </p>
          )}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--sp-8)", alignItems: "center" }}>
            <code>{pack.command}</code>
            <Button aria-label={`Copy the command for ${pack.id}`} onClick={() => copy(pack)}>
              Copy
            </Button>
            {copied?.id === pack.id && <span role="status" className="label">{copied.said}</span>}
          </div>
        </article>
      ))}
    </>
  );
}
