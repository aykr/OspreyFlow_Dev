// Admin › Policies › Grading scheme (ADR-145 decision 12; ADR-143 decision 11 and Amendment 6; L2.7):
// the deployment's grading scheme, read-only, over `GET /v1/grading-scheme`, with each part's grades
// and the command that changes it. The change is never made here: it runs on the machine OspreyFlow
// runs on, a dry run first (ruling C13), with the Conduit stopped, so this page only shows the
// command and copies it. Behind `administer_system` as its section (`sections.json`).
import { useEffect, useState } from "react";

import type { GradingSchemeAnswer } from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives";
import type { AdminApi } from "../api";

/** The dry run, always first: the change itself is refused without its token (Amendment 6, 2). */
export const GRADING_COMMAND = "ospreyflow grading change --to <scheme> --mapping <file> --dry-run";

const PARTS: { key: "source" | "intelligence" | "handling"; label: string }[] = [
  { key: "source", label: "Source" },
  { key: "intelligence", label: "Intelligence" },
  { key: "handling", label: "Handling" },
];

export async function readGradingScheme(api: AdminApi): Promise<GradingSchemeAnswer> {
  const response = await fetch(`${api.apiBaseUrl}/v1/grading-scheme`, { headers: { Authorization: `Bearer ${api.bearerToken}` } });
  if (!response.ok) throw new Error(`The grading scheme could not be read (${response.status}).`);
  return (await response.json()) as GradingSchemeAnswer;
}

export function GradingScheme({ api }: { api: AdminApi }) {
  const [scheme, setScheme] = useState<GradingSchemeAnswer | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  useEffect(() => {
    readGradingScheme(api)
      .then(setScheme)
      .catch((e: Error) => setProblem(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api.apiBaseUrl, api.bearerToken]);
  if (problem) return <p role="alert">{problem}</p>;
  if (!scheme) return <p className="label">Reading the grading scheme…</p>;
  const copy = () =>
    void Promise.resolve()
      .then(() => navigator.clipboard.writeText(GRADING_COMMAND))
      .then(() => setCopied("Copied. Run it in a terminal on the machine OspreyFlow runs on, the dry run first."))
      .catch(() => setCopied("Your browser would not let the page copy; select the command and copy it."));
  return (
    <div style={{ display: "grid", gap: "var(--sp-12)", maxWidth: 720 }}>
      <p className="label" style={{ margin: 0 }}>
        {`This deployment grades in ${scheme.scheme}. Every drawn item's grade is one of these, and a board's grade fields offer them. It is read-only here.`}
      </p>
      <table className="table" aria-label={`The grades of ${scheme.scheme}`}>
        <thead>
          <tr>
            <th scope="col">Part</th>
            <th scope="col">Grades, in order</th>
          </tr>
        </thead>
        <tbody>
          {PARTS.map((part) => (
            <tr key={part.key}>
              <th scope="row">{part.label}</th>
              <td>{scheme[part.key].join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <section aria-label="Changing the grading scheme" style={{ display: "grid", gap: "var(--sp-6)" }}>
        <p className="label" style={{ margin: 0 }}>
          The scheme is changed on the machine OspreyFlow runs on, never from this page. Run the dry run first: it reports how many
          items each line of your mapping moves and gives the token the change needs. The change itself is made with the Conduit
          stopped.
        </p>
        <code style={{ overflowWrap: "anywhere" }}>{GRADING_COMMAND}</code>
        <div>
          <Button onClick={copy} aria-label="Copy the grading change command">
            Copy
          </Button>
        </div>
        {copied && <p role="status">{copied}</p>}
      </section>
    </div>
  );
}
