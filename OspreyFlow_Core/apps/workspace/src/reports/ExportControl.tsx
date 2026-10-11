// "Export PDF" (ADR-113 stage 5, shared by the Packs and Published tabs). The Conduit re-checks the
// pack as the exporter; if some item needs a justification it names them and asks for it. On
// success the manifest becomes a print document and the person saves the PDF from the browser's
// print dialogue.
import { useState } from "react";

import { Button, Input } from "../design/primitives";
import type { BlockedItem } from "../export/api";
import type { ReportsApi } from "./api";
import { packPrintHtml, printInFrame } from "./packExport";
import { exportPack } from "./packsApi";

export interface ExportControlProps {
  api: ReportsApi;
  packId: string;
  /** Receives the print document; the default prints it from a hidden frame. */
  print?: (html: string) => void;
}

export function ExportControl({ api, packId, print }: ExportControlProps) {
  const [blocked, setBlocked] = useState<BlockedItem[] | null>(null);
  const [justification, setJustification] = useState("");
  const [reference, setReference] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(withOverride: boolean) {
    setProblem(null);
    setNotice(null);
    try {
      const outcome = await exportPack(api, packId, withOverride ? { justification: justification.trim(), originator_reference: reference.trim() } : {});
      if (outcome.kind === "override_required") {
        setBlocked(outcome.blocked);
        return;
      }
      setBlocked(null);
      (print ?? printInFrame)(packPrintHtml(outcome.manifest));
      setNotice("The export is ready. Save it as a PDF from the print dialogue.");
    } catch (e) {
      setProblem((e as Error).message);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      <div>
        <Button onClick={() => void run(false)}>Export PDF</Button>
      </div>
      {blocked && (
        <div role="group" aria-label="Export needs a justification" style={{ display: "grid", gap: "var(--sp-8)", border: "1px solid var(--border-subtle)", padding: "var(--sp-12)" }}>
          <p style={{ margin: 0 }}>
            These items need a justification before they can be exported. Say why, and give the originator reference.
          </p>
          <ul style={{ margin: 0, paddingLeft: "var(--sp-16)" }}>
            {blocked.map((b) => (
              <li key={b.id}>{`${b.label}: ${b.reason.replace(/_/g, " ")}`}</li>
            ))}
          </ul>
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Justification
            <Input value={justification} onChange={(e) => setJustification(e.target.value)} />
          </label>
          <label className="label" style={{ display: "grid", gap: "var(--sp-4)" }}>
            Originator reference
            <Input value={reference} onChange={(e) => setReference(e.target.value)} />
          </label>
          <div>
            <Button variant="primary" disabled={justification.trim() === "" || reference.trim() === ""} onClick={() => void run(true)}>
              Export with override
            </Button>
          </div>
        </div>
      )}
      {problem && <p role="alert" style={{ margin: 0 }}>{problem}</p>}
      {notice && <p role="status" style={{ margin: 0 }}>{notice}</p>}
    </div>
  );
}
