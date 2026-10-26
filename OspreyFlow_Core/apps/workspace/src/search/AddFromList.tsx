import { useId, useRef, useState } from "react";

import { Button } from "../design/primitives/Button";
import type { WorkingSetDelta } from "../workingset/models";
import {
  AddFromListError,
  addIdentifiers,
  countIdentifiers,
  countSentence,
  listFromFile,
  type IdentifierCounts,
} from "./addFromListApi";

export interface AddFromListProps {
  apiBaseUrl: string;
  bearerToken: string;
  investigationId: string;
  /** Draws what was added: the same call a starter question's delta goes to. */
  onApplyDelta: (delta: WorkingSetDelta) => void;
  /** Called when the analyst cancels (the button, or Escape). */
  onClose?: () => void;
}

/**
 * Add many from a list (ADR-128 decision 1, B2): a paste box or a `.txt`/`.csv` file (first
 * column), a count, then a confirm. The count says how many identifiers were read, how many were
 * found, how many matched nothing the analyst can see (an identifier that does not exist and one
 * they may not see are one figure) and how many repeated; nothing is on the canvas until they
 * choose. By default the nodes are added without their links ("Show links among all" then draws
 * them); "Add with all links" brings the links among them and what is drawn. Past the canvas's
 * limit nothing is added and the refusal says so (rule 2). The box is given counts and a delta and
 * never an identifier back (rule 7).
 */
export function AddFromList({ apiBaseUrl, bearerToken, investigationId, onApplyDelta, onClose }: AddFromListProps) {
  const boxId = useId();
  const fileId = useId();
  const [text, setText] = useState("");
  const [counts, setCounts] = useState<IdentifierCounts | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function change(next: string): void {
    // A count is of the text it was asked of: the text changed, so what was counted is not what
    // would be added, and the analyst counts again.
    setText(next);
    setCounts(null);
    setSaid(null);
    setProblem(null);
  }

  function cancel(): void {
    setText("");
    setCounts(null);
    setSaid(null);
    setProblem(null);
    if (fileInput.current) fileInput.current.value = "";
    onClose?.();
  }

  function chooseFile(file: File | undefined): void {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      change(listFromFile(file.name, String(reader.result ?? "")));
      setSaid(`Read ${file.name}. Count it to see what it holds.`);
    };
    reader.onerror = () => setProblem(`${file.name} could not be read.`);
    reader.readAsText(file);
  }

  async function count(): Promise<void> {
    setBusy(true);
    setSaid(null);
    setProblem(null);
    try {
      setCounts(await countIdentifiers(apiBaseUrl, bearerToken, investigationId, text));
    } catch (err: unknown) {
      setCounts(null);
      setProblem(err instanceof AddFromListError ? err.message : "The list could not be read.");
    } finally {
      setBusy(false);
    }
  }

  async function add(withLinks: boolean): Promise<void> {
    setBusy(true);
    setProblem(null);
    try {
      const added = await addIdentifiers(apiBaseUrl, bearerToken, investigationId, text, withLinks);
      onApplyDelta(added.delta);
      const nodes = added.delta.op === "add" ? added.delta.nodes.length : 0;
      setCounts(null);
      setText("");
      if (fileInput.current) fileInput.current.value = "";
      setSaid(`${new Intl.NumberFormat("en-GB").format(nodes)} added.`);
    } catch (err: unknown) {
      setProblem(err instanceof AddFromListError ? err.message : "The list could not be added.");
    } finally {
      setBusy(false);
    }
  }

  const caption = { color: "var(--text-secondary)", fontSize: "var(--fs-12)", margin: 0 };
  return (
    <div
      role="group"
      aria-label="Add many from a list"
      style={{ display: "grid", gap: "var(--sp-8)" }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          cancel();
        }
      }}
    >
      <label htmlFor={boxId} style={caption}>
        Identifiers: prison numbers, National Insurance numbers, phone numbers or account references,
        one a line or separated by commas or spaces
      </label>
      <textarea
        id={boxId}
        className="input"
        rows={6}
        spellCheck={false}
        value={text}
        disabled={busy}
        onChange={(e) => change(e.target.value)}
        style={{ width: "100%", boxSizing: "border-box", fontFamily: "var(--font-mono)", resize: "vertical" }}
      />
      <label htmlFor={fileId} style={caption}>
        Or choose a .txt or .csv file (first column)
      </label>
      <input
        id={fileId}
        ref={fileInput}
        type="file"
        accept=".txt,.csv,text/plain,text/csv"
        disabled={busy}
        onChange={(e) => chooseFile(e.target.files?.[0])}
      />
      <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
        <Button type="button" variant="primary" disabled={busy || text.trim() === ""} onClick={() => void count()}>
          Count
        </Button>
        <Button type="button" onClick={cancel}>
          Cancel
        </Button>
      </div>
      {counts && (
        <div style={{ display: "grid", gap: "var(--sp-8)" }}>
          <p role="status" style={{ margin: 0 }}>
            {countSentence(counts)}
          </p>
          <p style={caption}>
            Nothing is on the canvas yet. Add puts the nodes there without their links; Show links among
            all then draws them.
          </p>
          <div style={{ display: "flex", gap: "var(--sp-8)", flexWrap: "wrap" }}>
            <Button type="button" variant="primary" disabled={busy || counts.found === 0} onClick={() => void add(false)}>
              Add
            </Button>
            <Button type="button" disabled={busy || counts.found === 0} onClick={() => void add(true)}>
              Add with all links
            </Button>
          </div>
        </div>
      )}
      {said && !counts && (
        <p role="status" style={{ margin: 0 }}>
          {said}
        </p>
      )}
      {problem && (
        <p role="alert" style={{ margin: 0 }}>
          {problem}
        </p>
      )}
    </div>
  );
}
