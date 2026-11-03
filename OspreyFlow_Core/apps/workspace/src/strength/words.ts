// Connection strength in words (ADR-139 decisions 7 and 9): what an influencer does, what a link's
// strength rests on, and the per-node values the Metrics panel's two filters judge by. Pure, so the
// wording is tested without a screen. Never a count from beyond the reader's view: everything here is
// read from the reader's own strengths, rarity scores and working set.
import type {
  ActiveInfluencer,
  AppliedInfluencer,
  LinkStrength,
  StrengthInfluencer,
  StrengthLegend,
} from "../../../../packages/schemas/generated";
import { linkTypeName } from "../canvas/linkLabel";

/** The link-type name an influencer uses for a pair linked through a shared value (ADR-139
 * Amendment 2; `schemas/strength.py`'s `SHARED_VALUE`): the client's `dup_*` rows. */
export const SHARED_VALUE = "SHARED_VALUE";
export const SHARED_VALUE_LABEL = "A pair linked through a shared value";

export type Composition = "standard" | "client_parity";
export type RarityMeasure = "share" | "idf";

export const COMPOSITION_LABEL: Record<Composition, string> = {
  standard: "Standard",
  client_parity: "Client parity",
};

export const MEASURE_LABEL: Record<RarityMeasure, string> = {
  share: "share of pair links (the client's)",
  idf: "inverse frequency (IDF)",
};

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
/** The client's own scale, to four places, so their thresholds can be compared. */
const EXACT = new Intl.NumberFormat("en-GB", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

/** "an Incident", "a Document". */
export function withArticle(noun: string): string {
  return `${/^[AEIOUaeiou]/.test(noun) ? "an" : "a"} ${noun}`;
}

/** "a, b or c" */
export function orList(values: readonly string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

/** "a, b and c" */
export function andList(values: readonly string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} and ${values[values.length - 1]}`;
}

export type LinkName = (linkType: string) => string;

/** With no list of declared types to hand, a type is still named in words, never by its id. */
const AS_IS: LinkName = (t) => linkTypeName(t, []);

/** What the kind of change does, with its size. */
export function changeWords(change: AppliedInfluencer["change"], size: number): string {
  switch (change) {
    case "add":
      return `adds ${NUMBER.format(size)} to the score before the curve`;
    case "multiply":
      return `multiplies the score before the curve by ${NUMBER.format(size)}`;
    case "floor":
      return `draws it at least ${NUMBER.format(size)} strong`;
    default:
      return "draws it no stronger than its stored weight";
  }
}

/** What triggers an influencer: a kind of record and its values, a dataset, or nothing (direct
 * links). */
export function triggerWords(influencer: StrengthInfluencer): string {
  const trigger = influencer.trigger as
    | { kind?: "record"; entity_type: string; property: string; values: string[] }
    | { kind: "dataset"; datasets: string[] }
    | null
    | undefined;
  if (!trigger) {
    return influencer.link_types.every((t) => t === SHARED_VALUE) ? "always" : "always (these are direct links)";
  }
  if (trigger.kind === "dataset") return `when the link is evidenced in ${orList(trigger.datasets)}`;
  const property = trigger.property.replace(/_/g, " ");
  return `when ${withArticle(trigger.entity_type)}'s ${property} is ${orList(trigger.values)}`;
}

/** A link type's name, with the shared-value pseudo-type said in words. */
export function withSharedValue(linkName: LinkName): LinkName {
  return (type) => (type === SHARED_VALUE ? SHARED_VALUE_LABEL.toLowerCase() : linkName(type));
}

/** The legend's composition indicator (ADR-139 Amendment 2): which composition is in force, where it
 * came from, and the rarity measure. */
export function compositionWords(legend: Pick<StrengthLegend, "composition" | "composition_layer" | "rarity_measure">): string {
  const composition = (legend.composition ?? "standard") as Composition;
  const from =
    legend.composition_layer === "case"
      ? "this case's own"
      : legend.composition_layer === "installation"
        ? "installation-wide"
        : "shipped with OspreyFlow";
  const measure = MEASURE_LABEL[(legend.rarity_measure ?? "share") as RarityMeasure];
  if (composition === "client_parity") {
    return `Composition: client parity (${from}): strength is rarity plus the adds, with no count or recency, drawn on 0 to 1; rarity by ${measure}.`;
  }
  return `Composition: standard (${from}): strength is the stored weight with the influencers; rarity by ${measure}.`;
}

/** One influencer in a sentence, for the legend and the editor. */
export function influencerWords(influencer: StrengthInfluencer, linkName: LinkName = AS_IS): string {
  const links = andList(influencer.link_types.map(withSharedValue(linkName)));
  return `${links}: ${changeWords(influencer.change ?? "add", influencer.size ?? 0)}, ${triggerWords(influencer)}`;
}

export function layerWords(active: Pick<ActiveInfluencer, "layer" | "version">): string {
  if (active.layer === "case") return `this case's own${active.version ? ` (version ${active.version})` : ""}`;
  if (active.layer === "installation") return `installation-wide${active.version ? `, version ${active.version}` : ""}`;
  return "shipped with OspreyFlow";
}

/** "weights version 3, rule “Shared a cell with”" or "…, default rule". */
export function ruleWords(parameterSet: string | null | undefined, linkName: LinkName = AS_IS): string {
  if (!parameterSet) return "a weight stored before the rules were versioned";
  const [version, rule] = parameterSet.split("/", 2);
  const named = rule === "default" ? "the default rule" : `the rule for “${linkName(rule ?? "")}”`;
  return `weights version ${version}, ${named}`;
}

/** What a link's strength rests on (decision 9), as lines: its count against what is heavy for its
 * type (or its fixed strength), its recency, the rule and version, and each influencer applied. */
export function strengthExplanation(link: LinkStrength, linkName: LinkName = AS_IS): string[] {
  const lines: string[] = [];
  if (link.fixed !== null && link.fixed !== undefined) {
    lines.push(`A fixed strength of ${NUMBER.format(link.fixed)} for “${linkName(link.edge_type)}”, whatever its count or age.`);
  } else {
    const n = link.occurrences ?? 0;
    const heavy = link.heavy ?? 0;
    lines.push(
      `Seen ${NUMBER.format(n)} ${n === 1 ? "time" : "times"}; ${NUMBER.format(heavy)} is heavy for “${linkName(link.edge_type)}”.`,
    );
    lines.push(link.last_seen ? `Last seen on ${DAY.format(new Date(link.last_seen))}.` : "No end date: as recent as it gets.");
  }
  const parity = link.composition === "client_parity";
  if (parity) {
    lines.length = 0;
    lines.push("Client parity: worked out as the client does, from rarity and the adds alone; its count and age are not used.");
    lines.push(
      `Its rarity term ${EXACT.format(link.rarity_term ?? 0)}${link.dataset ? `, in ${link.dataset}` : ""}: one less its share of the links of its type you can see there.`,
    );
  } else {
    lines.push(`Worked out under ${ruleWords(link.parameter_set, linkName)}: stored weight ${NUMBER.format(link.base_weight)}.`);
  }
  for (const applied of link.applied ?? []) {
    const because = applied.record_kind
      ? `, because ${withArticle(applied.record_kind)} you can see evidences it`
      : applied.dataset
        ? `, because it is in ${applied.dataset}`
        : ", a direct link";
    const what = parity ? `adds ${NUMBER.format(applied.size)}` : changeWords(applied.change, applied.size);
    lines.push(`${applied.label} (${layerWords({ layer: applied.layer, version: null })})${because}: ${what}.`);
  }
  if (parity) {
    lines.push(`Raw sum ${EXACT.format(link.raw_sum ?? 0)} on the client's scale; drawn at ${NUMBER.format(link.strength)} on 0 to 1.`);
  } else {
    lines.push(`Connection strength ${NUMBER.format(link.strength)}.`);
  }
  return lines;
}

/** Each node's strongest link, and each link's strength, for the Metrics panel's filter and ranking.
 * `ends` gives a link's two ends from the working set. */
export function strengthValues(
  links: readonly LinkStrength[],
  ends: (edgeId: string) => [string, string] | null,
): { nodes: Record<string, number>; edges: Record<string, number> } {
  const nodes: Record<string, number> = {};
  const edges: Record<string, number> = {};
  for (const link of links) {
    edges[link.edge_id] = link.strength;
    const both = ends(link.edge_id);
    if (!both) continue;
    for (const id of both) nodes[id] = Math.max(nodes[id] ?? 0, link.strength);
  }
  return { nodes, edges };
}
