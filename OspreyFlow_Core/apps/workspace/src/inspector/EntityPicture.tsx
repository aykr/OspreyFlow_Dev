// The Inspector's *Picture* (ADR-105): one entity's own picture, drawn in its node before the
// picture chosen for its type (ADR-079). Setting one adds the file to the case as evidence, so like
// any file it needs a handling marking and a legal basis (spec 09 §2); the old picture is kept, not
// deleted. Removing it puts the node back to its type's picture.
import { useEffect, useState, useSyncExternalStore } from "react";

import {
  entityPictureFor,
  onEntityPicturesChange,
  removeEntityPicture,
  setEntityPicture,
  type PictureApi,
} from "../canvas/entityPictures";
import { PICTURE_ACCEPT, checkPictureFile } from "../canvas/iconImage";
import { fetchHandlingScheme } from "../ingest/api";

export interface EntityPictureProps extends PictureApi {
  /** The entity types a picture may depict (`DEPICTS`'s `to`); others have no *Picture*. */
  types: ReadonlySet<string>;
  /** Each delta the server returned, for the working set. */
  onDelta: (delta: unknown) => void;
}

export function EntityPicture({ nodeId, ...props }: EntityPictureProps & { nodeId: string }) {
  const { apiBaseUrl, bearerToken, onDelta } = props;
  const own = useSyncExternalStore(onEntityPicturesChange, () => entityPictureFor(nodeId));
  const [file, setFile] = useState<File | null>(null);
  const [classifications, setClassifications] = useState<string[]>(["OFFICIAL"]);
  const [classification, setClassification] = useState("OFFICIAL");
  const [legalBasis, setLegalBasis] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    fetchHandlingScheme(apiBaseUrl, bearerToken)
      .then((scheme) => {
        const order = scheme.classification ?? [];
        if (order.length > 0) setClassifications(order);
      })
      .catch(() => undefined);
  }, [apiBaseUrl, bearerToken]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setProblem(null);
    try {
      await action();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  const set = () =>
    run(async () => {
      if (!file) return;
      const deltas = await setEntityPicture(props, nodeId, file, classification, legalBasis.trim());
      deltas.forEach(onDelta);
      setFile(null);
    });
  const remove = () => run(async () => onDelta(await removeEntityPicture(props, nodeId)));

  return (
    <div style={{ display: "grid", gap: "var(--sp-8)" }}>
      {own ? (
        <img src={own} alt="This entity's own picture" width={64} height={64} style={{ borderRadius: "var(--r-chip)" }} />
      ) : (
        <p style={{ margin: 0, color: "var(--text-secondary)" }}>No picture of its own: it is drawn with its type's.</p>
      )}
      <label>
        Picture
        <input
          type="file"
          aria-label="Picture file"
          accept={PICTURE_ACCEPT}
          onChange={(event) => {
            const chosen = event.target.files?.[0] ?? null;
            setProblem(chosen ? checkPictureFile(chosen) : null);
            setFile(chosen && checkPictureFile(chosen) === null ? chosen : null);
          }}
        />
      </label>
      <label>
        Marking
        <select aria-label="Picture marking" value={classification} onChange={(e) => setClassification(e.target.value)}>
          {classifications.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <label>
        Legal basis
        <input
          type="text"
          aria-label="Picture legal basis"
          value={legalBasis}
          onChange={(e) => setLegalBasis(e.target.value)}
        />
      </label>
      <div style={{ display: "flex", gap: "var(--sp-8)" }}>
        <button type="button" disabled={busy || !file || !legalBasis.trim()} onClick={set}>
          Set picture
        </button>
        {own && (
          <button type="button" disabled={busy} onClick={remove}>
            Remove picture
          </button>
        )}
      </div>
      {problem && (
        <p role="alert" style={{ margin: 0, color: "var(--error)" }}>
          {problem}
        </p>
      )}
    </div>
  );
}
