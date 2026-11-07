// Each stage's settings, as the drawer shows them (ADR-108 Amendment 6.1: the drawer beside the
// canvas, the same in guided mode). Moved whole from `PipelineStudio.tsx` with phase 6; unchanged.
import { useEffect, useState } from "react";

import type {
  DomainPackEntry,
  PipelineNode,
  StudioRecipeDraft,
} from "../../../../../packages/schemas/generated";
import { Button } from "../../design/primitives/Button";
import { Input } from "../../design/primitives/Input";
import { Select } from "../../design/primitives/Select";
import { fetchDomainPacks } from "../api";

export function StagePanel({ title, words, children }: { title: string; words: string; children?: React.ReactNode }) {
  return (
    <section aria-label={`${title} settings`} style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>{title}</h3>
      <p className="label" style={{ margin: 0 }}>
        {words}
      </p>
      {children}
    </section>
  );
}

export function DomainPanel({
  apiBaseUrl,
  bearerToken,
  node,
  disabled,
  onApply,
}: {
  apiBaseUrl: string;
  bearerToken: string;
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const [packs, setPacks] = useState<DomainPackEntry[]>([]);
  useEffect(() => {
    let cancelled = false;
    fetchDomainPacks(apiBaseUrl, bearerToken)
      .then((found) => !cancelled && setPacks(found))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, bearerToken]);
  const current = (node.config?.pack as string) ?? "pole";
  return (
    <section aria-label="Domain model settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Domain model</h3>
      <p className="label" style={{ margin: 0 }}>
        What this pipeline's data means. The pack adds its types over the POLE core.
      </p>
      <div role="radiogroup" aria-label="Domain pack" style={{ display: "grid", gap: "var(--sp-4)" }}>
        {packs.map((pack) => (
          <label key={pack.name} style={{ display: "grid", gap: "var(--sp-2)" }}>
            <span style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
              <input
                type="radio"
                name="domain-pack"
                checked={current === pack.name}
                disabled={disabled}
                onChange={() => onApply({ ...node.config, pack: pack.name })}
              />
              {pack.label}
            </span>
            {(pack.entity_types?.length ?? 0) > 0 && (
              <span className="label" style={{ paddingLeft: "var(--sp-24)" }}>
                {`Adds ${pack.entity_types!.join(", ")}`}
              </span>
            )}
          </label>
        ))}
      </div>
    </section>
  );
}

export function SourcePanel({
  draft,
  node,
  disabled,
  onApply,
}: {
  draft: StudioRecipeDraft;
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void | Promise<void>;
}) {
  const [connector, setConnector] = useState<string>(
    (node.config?.connector_profile as string) ?? draft.connector_profile ?? "",
  );
  const [location, setLocation] = useState<string>(
    (node.config?.source_location as string) ?? draft.source_location ?? "",
  );
  return (
    <section aria-label="Source settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Source</h3>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Connector profile</span>
        <Input aria-label="Connector profile" value={connector} onChange={(e) => setConnector(e.target.value)} />
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Source location</span>
        <Input aria-label="Source location" value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      <Button
        disabled={disabled}
        onClick={() =>
          void onApply({ ...node.config, connector_profile: connector || null, source_location: location || null })
        }
      >
        Apply source settings
      </Button>
    </section>
  );
}

/** ADR-108 rulings Q1–Q3: the extract stage's declared settings — recogniser or model, the media
 * kind, where findings go (queue by default), and the handling override (below source needs an
 * Author and a reason; the engine enforces it in phase C, the words are honest now). */
export function ExtractPanel({
  node,
  disabled,
  onApply,
}: {
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const config = node.config ?? {};
  const [library, setLibrary] = useState<string>((config.library as string) ?? "stanza");
  const [media, setMedia] = useState<string>((config.media as string) ?? "text");
  const [output, setOutput] = useState<string>((config.output as string) ?? "review_queue");
  return (
    <section aria-label="Extract settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Extract</h3>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Library</span>
        <Select aria-label="Extraction library" value={library} onChange={(e) => setLibrary(e.target.value)}>
          <option value="stanza">Stanza (fast recogniser)</option>
          <option value="spacy">spaCy (fast recogniser)</option>
          <option value="transformers">Transformers NER (fast recogniser)</option>
          <option value="model">The deployment's language model (deep)</option>
          <option value="whisper">faster-whisper (audio transcription)</option>
          <option value="vision">Qwen2-VL (image and video)</option>
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Media kind</span>
        <Select aria-label="Media kind" value={media} onChange={(e) => setMedia(e.target.value)}>
          <option value="text">Document (text)</option>
          <option value="image">Image</option>
          <option value="audio">Audio</option>
        </Select>
      </label>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Findings go to</span>
        <Select aria-label="Findings go to" value={output} onChange={(e) => setOutput(e.target.value)}>
          <option value="review_queue">The review queue (bulk accept)</option>
          <option value="inferred_graph">The graph, as inferred — never asserted</option>
        </Select>
      </label>
      <p className="label" style={{ margin: 0 }}>
        Findings inherit the source&apos;s marking and legal basis. Marking below the source needs an
        Author and a written reason, and the run report says so.
      </p>
      <Button disabled={disabled} onClick={() => onApply({ ...config, library, media, output })}>
        Apply extract settings
      </Button>
    </section>
  );
}

/** ADR-108 ruling Q5: local gazetteers first; an online provider only from the deployment's
 * allow-list, and a run that used one says so. */
export function EnrichPanel({
  node,
  disabled,
  onApply,
}: {
  node: PipelineNode;
  disabled: boolean;
  onApply: (config: Record<string, unknown>) => void;
}) {
  const config = node.config ?? {};
  const [geocoder, setGeocoder] = useState<string>((config.geocoder as string) ?? "local_gazetteer");
  return (
    <section aria-label="Enrich settings" style={{ display: "grid", gap: "var(--sp-8)" }}>
      <h3 style={{ margin: 0, fontSize: "var(--fs-13)" }}>Enrich</h3>
      <p className="label" style={{ margin: 0 }}>
        Parses unstructured addresses (deepparse) and geocodes them for the map.
      </p>
      <label style={{ display: "grid", gap: "var(--sp-2)" }}>
        <span className="label">Geocode against</span>
        <Select aria-label="Geocode against" value={geocoder} onChange={(e) => setGeocoder(e.target.value)}>
          <option value="local_gazetteer">The loaded gazetteers (on this deployment)</option>
          <option value="online_allowlist">An allowed online provider — disclosed per run</option>
        </Select>
      </label>
      <Button disabled={disabled} onClick={() => onApply({ ...config, geocoder })}>
        Apply enrich settings
      </Button>
    </section>
  );
}
