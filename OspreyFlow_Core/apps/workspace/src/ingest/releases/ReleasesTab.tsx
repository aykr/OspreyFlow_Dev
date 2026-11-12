// Studio › 5 Releases (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4): *Export* writes the
// dataset's release as a YAML bundle (its manifest, the domain model, each published pipeline and
// each reference list's definition); *Import* reads a bundle's folder, checks it with a dry run
// first, and only then writes it, as drafts. Nothing here makes a model live: *Make live* stays a
// person's audited step. `ospreyflow release export|import` do the same through the same routes.
import { useState } from "react";

import type {
  ReleaseExport,
  ReleaseImportPlan,
} from "../../../../../packages/schemas/generated";
import { Button, Input } from "../../design/primitives";
import {
  bundleFromFolder,
  exportRelease,
  importRelease,
  releaseName,
} from "./releasesApi";

export interface ReleasesTabProps {
  apiBaseUrl: string;
  bearerToken: string;
  datasetId: string | null;
  datasetName: string;
  rights: ReadonlySet<string> | null;
}

export const RELEASE_WORDS = {
  intro:
    "A release carries this dataset's domain model, its published pipelines and its reference lists' definitions to another environment, as YAML. It never carries a credential, loaded data, case membership, an owner, or a licensed screening list's rows.",
  noExport: "Exporting needs Edit domain model and Publish pipelines.",
  noImport: "Importing needs Edit domain model and Edit pipelines.",
  drafts:
    "Everything imported is a draft. Make the model live in 1 Model when it is ready.",
  checkFirst:
    "Check the folder first: the import is offered once the check finds nothing wrong.",
  replaceOwn: "Replace my draft of the domain model",
  replaceOwnHint:
    "You have a draft of this dataset's domain model open. Importing replaces it, and what you have not made live in 1 Model is lost.",
} as const;

function download(path: string, text: string): void {
  const url = URL.createObjectURL(
    new Blob([text], { type: "application/yaml" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = path.replace(/\//g, "__");
  link.click();
  URL.revokeObjectURL(url);
}

const ACTION_WORDS: Record<string, string> = {
  new_draft: "a new draft",
  replaces_draft: "the draft, in place of the one open now",
};

function Plan({ plan }: { plan: ReleaseImportPlan }) {
  const items = plan.items ?? [];
  return (
    <div
      aria-label="What the import writes"
      style={{ display: "grid", gap: "var(--sp-4)" }}
    >
      {(plan.refused ?? []).length > 0 && (
        <div role="alert">
          <p style={{ margin: 0 }}>Nothing was written, because:</p>
          <ul style={{ margin: 0 }}>
            {(plan.refused ?? []).map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {items.length > 0 && (
        <ul style={{ margin: 0 }}>
          {items.map((item) => (
            <li key={`${item.role}:${item.name}`}>
              {`${plan.dry_run ? "Would write" : "Wrote"} ${item.name} as ${ACTION_WORDS[item.action] ?? "a draft"}.`}
            </li>
          ))}
        </ul>
      )}
      {(plan.missing_connections ?? []).map((name) => (
        <p key={name} className="caption" style={{ margin: 0 }}>
          {`This environment has no connection named “${name}”: add one in Admin › Connections before a run.`}
        </p>
      ))}
      {(plan.notes ?? []).map((note) => (
        <p key={note} className="caption" style={{ margin: 0 }}>
          {`Note: ${note}.`}
        </p>
      ))}
    </div>
  );
}

export function ReleasesTab({
  apiBaseUrl,
  bearerToken,
  datasetId,
  datasetName,
  rights,
}: ReleasesTabProps) {
  const has = (right: string) => rights?.has(right) ?? false;
  const mayExport = has("edit_target_model") && has("publish_pipelines");
  const mayImport = has("edit_target_model") && has("edit_pipelines");
  const [name, setName] = useState(releaseName(datasetName));
  const [version, setVersion] = useState("1");
  const [exported, setExported] = useState<ReleaseExport | null>(null);
  const [files, setFiles] = useState<Record<string, string> | null>(null);
  const [checked, setChecked] = useState<ReleaseImportPlan | null>(null);
  const [written, setWritten] = useState<ReleaseImportPlan | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // CARRIES row 90: the importer's own in-progress draft is replaced only once they say so here.
  const [replaceOwn, setReplaceOwn] = useState(false);

  if (!datasetId) {
    return (
      <p className="label" style={{ padding: "var(--sp-16)" }}>
        This case loads into no dataset, so there is nothing to release.
      </p>
    );
  }

  const run = (work: () => Promise<void>) => {
    setProblem(null);
    setBusy(true);
    work()
      .catch((e: Error) => setProblem(e.message))
      .finally(() => setBusy(false));
  };

  const onExport = () =>
    run(async () => {
      setExported(
        await exportRelease(
          apiBaseUrl,
          bearerToken,
          datasetId,
          name.trim(),
          version.trim(),
        ),
      );
    });

  const onChoose = (chosen: FileList | null) =>
    run(async () => {
      setChecked(null);
      setWritten(null);
      setReplaceOwn(false);
      setFiles(
        chosen && chosen.length > 0
          ? await bundleFromFolder(Array.from(chosen))
          : null,
      );
    });

  const check = (confirmed: boolean) =>
    run(async () => {
      if (files)
        setChecked(
          await importRelease(
            apiBaseUrl,
            bearerToken,
            datasetId,
            files,
            true,
            confirmed,
          ),
        );
    });

  const onCheck = () => check(replaceOwn);

  const onReplaceOwn = (confirmed: boolean) => {
    setReplaceOwn(confirmed);
    check(confirmed);
  };

  const onImport = () =>
    run(async () => {
      if (files)
        setWritten(
          await importRelease(
            apiBaseUrl,
            bearerToken,
            datasetId,
            files,
            false,
            replaceOwn,
          ),
        );
    });

  const clean = checked !== null && (checked.refused ?? []).length === 0;

  return (
    <div
      style={{
        display: "grid",
        gap: "var(--sp-16)",
        padding: "var(--sp-16)",
        maxWidth: 820,
      }}
    >
      <p style={{ margin: 0 }}>{RELEASE_WORDS.intro}</p>

      <section
        aria-label="Export a release"
        style={{ display: "grid", gap: "var(--sp-8)" }}
      >
        <h3 style={{ margin: 0 }}>Export</h3>
        {!mayExport && (
          <p className="caption" style={{ margin: 0 }}>
            {RELEASE_WORDS.noExport}
          </p>
        )}
        <div
          style={{
            display: "flex",
            gap: "var(--sp-8)",
            alignItems: "end",
            flexWrap: "wrap",
          }}
        >
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>Release name</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!mayExport}
            />
          </label>
          <label style={{ display: "grid", gap: "var(--sp-4)" }}>
            <span>Release version</span>
            <Input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              disabled={!mayExport}
            />
          </label>
          <Button
            variant="primary"
            onClick={onExport}
            disabled={!mayExport || busy}
          >
            Export
          </Button>
        </div>
        {exported && (
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <p role="status" style={{ margin: 0 }}>
              {`The release has ${Object.keys(exported.files).length} files.`}
              {exported.left_out
                ? ` ${exported.left_out} published pipeline(s) are marked above what you may view, so they are not in it.`
                : ""}
            </p>
            <ul aria-label="The release's files" style={{ margin: 0 }}>
              {Object.entries(exported.files).map(([path, text]) => (
                <li key={path}>
                  <Button
                    onClick={() => download(path, text)}
                    aria-label={`Download ${path}`}
                  >
                    {path}
                  </Button>
                </li>
              ))}
            </ul>
            <p className="caption" style={{ margin: 0 }}>
              {`To keep the files as a folder, run: ospreyflow release export ${datasetId} --name ${name.trim()} --release-version ${version.trim()} --out <folder>`}
            </p>
          </div>
        )}
      </section>

      <section
        aria-label="Import a release"
        style={{ display: "grid", gap: "var(--sp-8)" }}
      >
        <h3 style={{ margin: 0 }}>Import</h3>
        {!mayImport && (
          <p className="caption" style={{ margin: 0 }}>
            {RELEASE_WORDS.noImport}
          </p>
        )}
        <label style={{ display: "grid", gap: "var(--sp-4)" }}>
          <span>The release's folder</span>
          <input
            type="file"
            multiple
            aria-label="Choose the release's folder"
            disabled={!mayImport}
            onChange={(e) => onChoose(e.target.files)}
            {...{ webkitdirectory: "" }}
          />
        </label>
        <p className="caption" style={{ margin: 0 }}>
          {RELEASE_WORDS.checkFirst}
        </p>
        <div style={{ display: "flex", gap: "var(--sp-8)" }}>
          <Button onClick={onCheck} disabled={!mayImport || !files || busy}>
            Check the release
          </Button>
          <Button
            variant="primary"
            onClick={onImport}
            disabled={!mayImport || !clean || busy || written !== null}
          >
            Import as drafts
          </Button>
        </div>
        {checked?.replaces_own_draft && !written && (
          <div style={{ display: "grid", gap: "var(--sp-4)" }}>
            <label
              style={{
                display: "flex",
                gap: "var(--sp-8)",
                alignItems: "center",
              }}
            >
              <input
                type="checkbox"
                checked={replaceOwn}
                disabled={!mayImport || busy}
                onChange={(e) => onReplaceOwn(e.target.checked)}
              />
              <span>{RELEASE_WORDS.replaceOwn}</span>
            </label>
            <p className="caption" style={{ margin: 0 }}>
              {RELEASE_WORDS.replaceOwnHint}
            </p>
          </div>
        )}
        {checked && !written && <Plan plan={checked} />}
        {written && (
          <>
            <Plan plan={written} />
            {(written.refused ?? []).length === 0 && (
              <p role="status" style={{ margin: 0 }}>
                {RELEASE_WORDS.drafts}
              </p>
            )}
          </>
        )}
      </section>
      {problem && <p role="alert">{problem}</p>}
    </div>
  );
}
