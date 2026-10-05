// Files added straight to a case (ADR-094 step 3, spec 09 §7): images, videos and text files, each
// a Document on the canvas, standing alone or held by the node they were added from (`HOLDS`). Each
// needs a handling marking and a legal basis, like every source (spec 09 §2); the marking offered is
// the deployment's own scheme. A refused file is said by name and the rest still go.
import { useEffect, useState } from "react";

import { fetchHandlingScheme } from "../ingest/api";

export interface AddFilesProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** The node the files are held by; left out, they stand alone. */
  holder?: { id: string; label: string };
  /** Each file's delta, for the working set. */
  onDelta: (delta: unknown) => void;
  onClose: () => void;
}

const ACCEPT = ".png,.jpg,.jpeg,.gif,.webp,.tif,.tiff,.heic,.mp4,.mov,.webm,.txt";

async function uploadOne(
  props: AddFilesProps,
  file: File,
  classification: string,
  legalBasis: string,
): Promise<unknown> {
  const query = new URLSearchParams({ name: file.name, classification, legal_basis: legalBasis });
  if (props.holder) query.set("holder", props.holder.id);
  const url =
    `${props.apiBaseUrl}/v1/investigations/${encodeURIComponent(props.investigationId)}/documents?` +
    query.toString();
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${props.bearerToken}`, "Content-Type": "application/octet-stream" },
      body: file,
    });
  } catch {
    throw new Error(`${file.name}: the server could not be reached.`);
  }
  if (response.ok) return ((await response.json()) as { delta: unknown }).delta;
  let body: { error?: string; detail?: string } = {};
  try {
    body = (await response.json()) as typeof body;
  } catch {
    // no body
  }
  if (response.status === 413) throw new Error(`${file.name}: larger than the upload limit.`);
  if (response.status === 403) throw new Error(`${file.name}: adding files needs Editor access.`);
  if (body.error === "holder_not_found") throw new Error(`${file.name}: the holder is no longer in the view.`);
  throw new Error(`${file.name}: ${body.detail ?? `refused (${response.status})`}`);
}

export function AddFiles(props: AddFilesProps) {
  const { apiBaseUrl, bearerToken, holder, onDelta, onClose } = props;
  const [files, setFiles] = useState<File[]>([]);
  const [classifications, setClassifications] = useState<string[]>(["OFFICIAL"]);
  const [classification, setClassification] = useState("OFFICIAL");
  const [legalBasis, setLegalBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState<number | null>(null);
  const [problems, setProblems] = useState<string[]>([]);

  useEffect(() => {
    fetchHandlingScheme(apiBaseUrl, bearerToken)
      .then((scheme) => {
        const order = scheme.classification ?? [];
        if (order.length > 0) setClassifications(order);
      })
      .catch(() => undefined);
  }, [apiBaseUrl, bearerToken]);

  async function upload() {
    setBusy(true);
    setProblems([]);
    let count = 0;
    const refused: string[] = [];
    for (const file of files) {
      try {
        onDelta(await uploadOne(props, file, classification, legalBasis.trim()));
        count += 1;
      } catch (err) {
        refused.push(err instanceof Error ? err.message : String(err));
      }
    }
    setAdded(count);
    setProblems(refused);
    setBusy(false);
  }

  const label = files.length === 1 ? "Add 1 file" : `Add ${files.length} files`;
  return (
    <section
      aria-label="Add files"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      style={{ display: "grid", gap: "var(--sp-8)", padding: "var(--sp-16)", background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "var(--sp-4)", minWidth: 320 }}
    >
      <h3 style={{ margin: 0, fontSize: "var(--fs-14)" }}>
        Add files{holder ? ` held by ${holder.label}` : " to the case"}
      </h3>
      <label htmlFor="add-files-input">Files</label>
      <input
        id="add-files-input"
        type="file"
        multiple
        accept={ACCEPT}
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
      />
      <span style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)" }}>
        Images, videos and text files. Each becomes a Document you can read and extract from.
      </span>
      <label htmlFor="add-files-marking">Marking</label>
      <select
        id="add-files-marking"
        className="input"
        value={classification}
        onChange={(e) => setClassification(e.target.value)}
      >
        {classifications.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      <label htmlFor="add-files-basis">Legal basis</label>
      <input
        id="add-files-basis"
        className="input"
        value={legalBasis}
        onChange={(e) => setLegalBasis(e.target.value)}
        placeholder="The power or consent the files are held under"
      />
      <span style={{ display: "flex", gap: "var(--sp-8)" }}>
        <button
          type="button"
          className="btn"
          disabled={busy || files.length === 0 || legalBasis.trim() === ""}
          onClick={() => void upload()}
        >
          {busy ? "Adding…" : label}
        </button>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </span>
      {added !== null && (
        <p role="status" style={{ margin: 0 }}>
          {added === 1 ? "1 file added." : `${added} files added.`}
        </p>
      )}
      {problems.length > 0 && (
        <div role="alert" style={{ color: "var(--text-secondary)" }}>
          {problems.map((p) => (
            <p key={p} style={{ margin: 0 }}>
              {p}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
