import { useState } from "react";

import { errorMessage } from "../api/client";
import type { OspreyConfig } from "../api/types";

// What the schema ships for these: paths inside the Conduit's container, which mean nothing on a
// person's computer, so a folder under their own home is suggested in their place. The backups one
// is also the placeholder `ospreyflow backup` reads as no folder named (ADR-114 Amendment 37).
const SHIPPED = {
  ingest: "/var/lib/osprey/ingest",
  tiles: "/var/lib/osprey/tiles",
  backups: "/var/lib/osprey/backups",
};

export function FoldersScreen({
  config,
  onSave,
  home,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
  /** The person's home folder, from the install page; folders are suggested beneath it. */
  home?: string;
}) {
  const current = config.components?.storage;
  const suggest = (value: string | undefined, shipped: string, name: string) =>
    !value || value === shipped ? (home ? `${home}/OspreyFlow/${name}` : shipped) : value;
  const [ingest, setIngest] = useState(suggest(current?.ingest, SHIPPED.ingest, "ingest"));
  const [tiles, setTiles] = useState(suggest(current?.tiles, SHIPPED.tiles, "basemap"));
  const [backups, setBackups] = useState(suggest(current?.backups, SHIPPED.backups, "backups"));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        components: { ...config.components, storage: { ...config.components?.storage, ingest, tiles, backups } },
      });
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="folders-heading">
      <h2 id="folders-heading">Folders</h2>
      <label htmlFor="folder-ingest">Ingest folder</label>
      <input
        id="folder-ingest"
        className="input"
        value={ingest}
        onChange={(event) => setIngest(event.target.value)}
        aria-describedby="folder-ingest-help"
      />
      <p id="folder-ingest-help" className="help">
        On this computer. Source files placed here are listed by the Ingest Studio for analysts to
        pick. OspreyFlow never writes to it. Give the full path, from /.
      </p>
      <label htmlFor="folder-tiles">Basemap folder</label>
      <input
        id="folder-tiles"
        className="input"
        value={tiles}
        onChange={(event) => setTiles(event.target.value)}
        aria-describedby="folder-tiles-help"
      />
      <p id="folder-tiles-help" className="help">
        On this computer. Where a built basemap lives. Give the full path, from /.
      </p>
      <label htmlFor="folder-backups">Backups folder</label>
      <input
        id="folder-backups"
        className="input"
        value={backups}
        onChange={(event) => setBackups(event.target.value)}
        aria-describedby="folder-backups-help"
      />
      <p id="folder-backups-help" className="help">
        On this computer, outside the OspreyFlow folder. Where ospreyflow backup writes, each
        deployment&rsquo;s backups in a subfolder of its own. A backup holds all of the
        deployment&rsquo;s data, so choose a folder that is not synced to a cloud drive. Give the
        full path, from /.
      </p>
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save folders
      </button>
    </section>
  );
}
