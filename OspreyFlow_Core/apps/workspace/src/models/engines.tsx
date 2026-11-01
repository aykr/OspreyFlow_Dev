// The model engine an analyst may choose for Ask the case and Ask to search (ADR-135 decision 5):
// the engines `GET /v1/models/engines` offers for the role, the role's default chosen. The choice is
// a request, not a ruling — the Conduit decides where each request runs (decision 4), and every
// answer says which engine and model produced it, so the Glass names the engine from the answer,
// never from the choice.
import { useEffect, useState } from "react";

import type { OfferedEngine } from "../../../../packages/schemas/generated";
import { Select } from "../design/primitives/Select";

export type EngineRole = OfferedEngine["roles"][number];

/** The local engine's name, and the label the Conduit gives it (`model_routing.LOCAL_LABEL`). */
export const LOCAL_ENGINE = "local";
const LOCAL_LABEL = "This deployment's own model";

/** `GET /v1/models/engines`: what the deployment offers. Anything but a list of engines is none. */
export async function fetchOfferedEngines(apiBaseUrl: string, bearerToken: string): Promise<OfferedEngine[]> {
  const response = await fetch(`${apiBaseUrl}/v1/models/engines`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) throw new Error(`The model engines could not be read (${response.status}).`);
  const body = (await response.json()) as { engines?: unknown };
  return Array.isArray(body.engines) ? (body.engines as OfferedEngine[]) : [];
}

export interface EngineChoice {
  /** Every engine offered, for naming the engine an answer came from. */
  engines: OfferedEngine[];
  /** The engines offered for the role, in the order the Conduit gives them (the local one first). */
  offered: OfferedEngine[];
  /** The engine chosen; `null` while there is no choice to make (one engine or none offered). */
  chosen: string | null;
  choose: (name: string) => void;
}

/** The engines offered for `role` and the one chosen. With fewer than two there is nothing to
 * choose, and the request names no engine: the role's default is the Conduit's to apply. A failure
 * to read the engines is the same as none offered — Ask still works, on the role's default. */
export function useEngineChoice(apiBaseUrl: string, bearerToken: string, role: EngineRole): EngineChoice {
  const [engines, setEngines] = useState<OfferedEngine[]>([]);
  const [picked, setPicked] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchOfferedEngines(apiBaseUrl, bearerToken)
      .then((found) => {
        if (!cancelled) setEngines(found);
      })
      .catch(() => {
        if (!cancelled) setEngines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);

  const offered = engines.filter((engine) => engine.roles.includes(role));
  const fallback = offered.find((engine) => engine.default_for.includes(role)) ?? offered[0];
  const chosen =
    offered.length < 2 ? null : (offered.find((engine) => engine.name === picked) ?? fallback)!.name;
  return { engines, offered, chosen, choose: setPicked };
}

/** The choice itself, with its visible label: hidden unless there are two or more engines to
 * choose between. `id` ties the label to the select, so it must be unique on the page. */
export function EnginePicker({ choice, id, disabled }: { choice: EngineChoice; id: string; disabled?: boolean }) {
  if (choice.chosen === null) return null;
  return (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <label htmlFor={id} style={{ fontSize: "var(--fs-12)" }}>
        Model engine
      </label>
      <Select id={id} value={choice.chosen} disabled={disabled} onChange={(event) => choice.choose(event.target.value)}>
        {choice.offered.map((engine) => (
          <option key={engine.name} value={engine.name}>
            {engine.label}
          </option>
        ))}
      </Select>
    </div>
  );
}

/** "Answered by <label> (<model>)", from what the answer says produced it; nothing for an answer
 * kept before engines were named. An engine no longer offered is named as the answer gives it. */
export function answeredBy(
  engine: string | null | undefined,
  model: string | null | undefined,
  engines: readonly OfferedEngine[],
): string | null {
  if (!engine) return null;
  const label =
    engines.find((offered) => offered.name === engine)?.label ?? (engine === LOCAL_ENGINE ? LOCAL_LABEL : engine);
  return model ? `Answered by ${label} (${model})` : `Answered by ${label}`;
}

/** The answer's engine line, small and quiet under the answer. */
export function AnsweredBy({
  engine,
  model,
  engines,
}: {
  engine: string | null | undefined;
  model: string | null | undefined;
  engines: readonly OfferedEngine[];
}) {
  const words = answeredBy(engine, model, engines);
  if (words === null) return null;
  return <p style={{ color: "var(--text-tertiary)", fontSize: "var(--fs-12)", margin: 0 }}>{words}</p>;
}
