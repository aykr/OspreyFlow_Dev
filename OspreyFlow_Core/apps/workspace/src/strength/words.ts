// Connection strength in words (ADR-139 decisions 7 and 9): what an influencer does, what a link's
// strength rests on, and the per-node values the Metrics panel's two filters judge by. Pure, so the
// wording is tested without a screen. Never a count from beyond the reader's view: everything here is
// read from the reader's own strengths, rarity scores and working set.
import type {
  ActiveInfluencer,
  AppliedInfluencer,
  LinkStrength,
  StrengthInfluencer,
} from "../../../../packages/schemas/generated";

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 });
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

const AS_IS: LinkName = (t) => t;

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

/** What triggers an influencer: a kind of record and its values, or nothing (direct links). */
export function triggerWords(influencer: StrengthInfluencer): string {
  const trigger = influencer.trigger;
  if (!trigger) return "always (these are direct links)";
  const property = trigger.property.replace(/_/g, " ");
  return `when ${withArticle(trigger.entity_type)}'s ${property} is ${orList(trigger.values as string[])}`;
}

/** One influencer in a sentence, for the legend and the editor. */
export function influencerWords(influencer: StrengthInfluencer, linkName: LinkName = AS_IS): string {
  const links = andList(influencer.link_types.map(linkName));
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
  lines.push(`Worked out under ${ruleWords(link.parameter_set, linkName)}: stored weight ${NUMBER.format(link.base_weight)}.`);
  for (const applied of link.applied ?? []) {
    const because = applied.record_kind
      ? `, because ${withArticle(applied.record_kind)} you can see evidences it`
      : ", a direct link";
    lines.push(
      `${applied.label} (${layerWords({ layer: applied.layer, version: null })})${because}: ${changeWords(applied.change, applied.size)}.`,
    );
  }
  lines.push(`Connection strength ${NUMBER.format(link.strength)}.`);
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
