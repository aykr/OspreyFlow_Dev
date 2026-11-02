// A rule written as a sentence (`06_DECISIONS.md` ADR-133 decision 1, stage (b)): what each blank may
// be, read from the deployment's ontology, and the draft the builder keeps, turned into the server's
// `RuleSentence` and back. Every blank is a closed choice (rule 8): a type, a property, a link type,
// an operator from a fixed list, a number, a date or a drawn area — never text to be parsed. The
// server checks the sentence against the ontology again; this only offers what it would accept.
import type {
  EdgeTypeDef,
  EntityTypeDef,
  OntologySchema,
  PropertyDef,
  RuleSentence,
} from "../../../../packages/schemas/generated";

export type Op = "equals" | "one_of" | "above" | "below" | "within_area" | "within_time";
export type RelationshipKind = "none" | "linked" | "within_steps" | "at_location" | "on_hotlist" | "on_screening_list";
export type FrequencyKind = "none" | "count" | "amount" | "first_time";
export type Scope = "just_me" | "this_case" | "deployment";

/** A drawn area entered as a box by its corners: west, south, east, north. */
export interface AreaBox {
  name: string;
  west: string;
  south: string;
  east: string;
  north: string;
}

export interface ConditionDraft {
  property: string;
  op: Op;
  value: string;
  values: string[];
  start: string;
  end: string;
  area: AreaBox;
}

export type StrengthKind = "none" | "connection_strength" | "shared_attribute_rarity";

export interface SentenceDraft {
  subject: string;
  conditions: ConditionDraft[];
  relationship: RelationshipKind;
  linkType: string;
  otherType: string;
  steps: string;
  area: AreaBox;
  minScore: string;
  frequency: FrequencyKind;
  frequencyLink: string;
  atLeast: string;
  withinDays: string;
  amountProperty: string;
  over: string;
  /** ADR-139 decision 8: "… and the connection strength (or shared-attribute rarity) between …
   * reaches X". */
  strength: StrengthKind;
  strengthLink: string;
  strengthOther: string;
  reaches: string;
  rarityScope: "dataset" | "case";
  severity: "low" | "medium" | "high";
  team: "case" | "my_team";
  runs: "pre_commit" | "post_commit" | "schedule";
  onHit: "load" | "hold";
  scope: Scope;
  /** ADR-133 stage (d): a scheduled rule's cadence, its hour (Europe/London) and, weekly, its day. */
  every: "daily" | "weekly";
  hour: string;
  weekday: string;
}

/** Monday first, as the server numbers them (1 to 7). */
export const WEEKDAY_WORDS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

/** "every day at 06:00", "every Monday at 06:00" — the schedule as the rules list says it. */
export function scheduleWords(schedule: { every?: string; hour?: number; weekday?: number | null } | null | undefined): string {
  if (!schedule) return "on a schedule";
  const at = `at ${String(schedule.hour ?? 6).padStart(2, "0")}:00`;
  if (schedule.every === "weekly") return `every ${WEEKDAY_WORDS[(schedule.weekday ?? 1) - 1] ?? "Monday"} ${at}`;
  return `every day ${at}`;
}

export const MAX_CONDITIONS = 5;

export const OP_WORDS: Record<Op, string> = {
  equals: "is",
  one_of: "is one of",
  above: "is above",
  below: "is below",
  within_area: "is within a drawn area",
  within_time: "is within a time window",
};

export const POLE_WORDS: Record<string, string> = {
  person: "People",
  object: "Objects",
  location: "Locations",
  event: "Events",
  organisation: "Organisations",
};

const EMPTY_AREA: AreaBox = { name: "the drawn area", west: "", south: "", east: "", north: "" };

export function emptyDraft(subject = "Person"): SentenceDraft {
  return {
    subject,
    conditions: [],
    relationship: "none",
    linkType: "",
    otherType: "",
    steps: "2",
    area: { ...EMPTY_AREA },
    minScore: "0.9",
    frequency: "none",
    frequencyLink: "",
    atLeast: "3",
    withinDays: "7",
    amountProperty: "",
    over: "10000",
    strength: "none",
    strengthLink: "",
    strengthOther: "",
    reaches: "0.8",
    rarityScope: "dataset",
    severity: "medium",
    team: "case",
    runs: "post_commit",
    onHit: "load",
    scope: "this_case",
    every: "daily",
    hour: "6",
    weekday: "1",
  };
}

export function emptyCondition(property: string, op: Op): ConditionDraft {
  return { property, op, value: "", values: [], start: "", end: "", area: { ...EMPTY_AREA } };
}

// --- what the ontology offers --------------------------------------------------------------------

/** The subjects a sentence may name, grouped by POLE class, in the ontology's own order. The
 * `Alert` type is what rules raise, not something a rule is about. */
export function subjectsByPole(ontology: OntologySchema): [string, EntityTypeDef[]][] {
  const groups = new Map<string, EntityTypeDef[]>();
  for (const type of ontology.entity_types) {
    if (type.name === "Alert") continue;
    const list = groups.get(type.pole_class) ?? [];
    list.push(type);
    groups.set(type.pole_class, list);
  }
  return [...groups.entries()];
}

const TEXT = new Set(["string", "enum"]);
const NUMBERS = new Set(["integer", "float"]);
const TIMES = new Set(["date", "datetime"]);

/** A property a rule may test: declared on the subject, never `sensitivity: high`. */
export function propertiesFor(ontology: OntologySchema, subject: string): PropertyDef[] {
  const type = ontology.entity_types.find((t) => t.name === subject);
  return (type?.properties ?? []).filter((p) => p.sensitivity !== "high");
}

/** The operators that fit a property's type — the server's own table. */
export function opsFor(property: PropertyDef | undefined): Op[] {
  if (!property) return [];
  const ops: Op[] = [];
  const type = property.type;
  if (TEXT.has(type) || NUMBERS.has(type) || TIMES.has(type) || type === "boolean") ops.push("equals");
  if (TEXT.has(type)) ops.push("one_of");
  if (NUMBERS.has(type)) ops.push("above", "below");
  if (TIMES.has(type)) ops.push("within_time");
  if (property.name === "geometry_ref") ops.push("within_area");
  return ops;
}

function reaches(types: string[], name: string): boolean {
  return types.includes("*") || types.includes(name);
}

function offered(link: EdgeTypeDef): boolean {
  return !link.system && !link.hidden;
}

/** The link types that reach the subject's type, by their names a person reads. */
export function linksFor(ontology: OntologySchema, subject: string): EdgeTypeDef[] {
  return ontology.edge_types.filter((e) => offered(e) && (reaches(e.from, subject) || reaches(e.to, subject)));
}

/** The link types whose dated events a frequency counts: those that reach the subject and are temporal. */
export function eventLinksFor(ontology: OntologySchema, subject: string): EdgeTypeDef[] {
  return linksFor(ontology, subject).filter((e) => e.temporal);
}

/** The other end of a link from the subject: the types it may reach. */
export function otherEndsFor(ontology: OntologySchema, subject: string, linkType: string): string[] {
  const link = ontology.edge_types.find((e) => e.name === linkType);
  if (!link) return [];
  const ends = reaches(link.from, subject) ? link.to : link.from;
  return ends.includes("*") ? ontology.entity_types.map((t) => t.name).filter((n) => n !== "Alert") : ends;
}

/** A link type's numeric properties: what an amount condition may total. */
export function amountsFor(ontology: OntologySchema, linkType: string): PropertyDef[] {
  const link = ontology.edge_types.find((e) => e.name === linkType);
  return (link?.properties ?? []).filter((p) => NUMBERS.has(p.type) && p.sensitivity !== "high");
}

export function linkLabel(link: EdgeTypeDef): string {
  if (link.label) return link.label;
  const words = link.name.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// --- the draft as the server's sentence, and back ------------------------------------------------

function boxPoints(box: AreaBox): { lon: number; lat: number }[] {
  const [w = 0, s = 0, e = 0, n = 0] = [box.west, box.south, box.east, box.north].map(Number);
  return [
    { lon: w, lat: s },
    { lon: e, lat: s },
    { lon: e, lat: n },
    { lon: w, lat: n },
  ];
}

function area(box: AreaBox) {
  return { name: box.name.trim() || "the drawn area", points: boxPoints(box) };
}

function boxOf(drawn: { name?: string; points: { lon: number; lat: number }[] }): AreaBox {
  const lons = drawn.points.map((p) => p.lon);
  const lats = drawn.points.map((p) => p.lat);
  return {
    name: drawn.name ?? "the drawn area",
    west: String(Math.min(...lons)),
    south: String(Math.min(...lats)),
    east: String(Math.max(...lons)),
    north: String(Math.max(...lats)),
  };
}

function condition(c: ConditionDraft): Record<string, unknown> {
  switch (c.op) {
    case "equals":
      return { op: c.op, property: c.property, value: c.value };
    case "one_of":
      return { op: c.op, property: c.property, values: c.values };
    case "above":
    case "below":
      return { op: c.op, property: c.property, value: Number(c.value) };
    case "within_area":
      return { op: c.op, property: c.property, area: area(c.area) };
    default:
      return {
        op: c.op,
        property: c.property,
        start: c.start ? `${c.start}T00:00:00Z` : null,
        end: c.end ? `${c.end}T23:59:59Z` : null,
      };
  }
}

export function toSentence(draft: SentenceDraft): RuleSentence {
  let relationship: Record<string, unknown> | null = null;
  switch (draft.relationship) {
    case "linked":
      relationship = { kind: "linked", link_type: draft.linkType, other_type: draft.otherType || null };
      break;
    case "within_steps":
      relationship = { kind: "within_steps", steps: Number(draft.steps), other_type: draft.otherType };
      break;
    case "at_location":
      relationship = { kind: "at_location", link_type: draft.linkType, area: area(draft.area) };
      break;
    case "on_hotlist":
      relationship = { kind: "on_hotlist" };
      break;
    case "on_screening_list":
      relationship = { kind: "on_screening_list", min_score: Number(draft.minScore) };
      break;
  }
  let frequency: Record<string, unknown> | null = null;
  switch (draft.frequency) {
    case "count":
      frequency = { kind: "count", link_type: draft.frequencyLink, at_least: Number(draft.atLeast), within_days: Number(draft.withinDays) };
      break;
    case "amount":
      frequency = {
        kind: "amount",
        link_type: draft.frequencyLink,
        amount_property: draft.amountProperty,
        over: Number(draft.over),
        within_days: Number(draft.withinDays),
      };
      break;
    case "first_time":
      frequency = { kind: "first_time", link_type: draft.frequencyLink };
      break;
  }
  let strength: Record<string, unknown> | null = null;
  if (draft.strength === "connection_strength") {
    strength = {
      kind: "connection_strength",
      link_type: draft.strengthLink || null,
      other_type: draft.strengthOther || null,
      reaches: Number(draft.reaches),
    };
  } else if (draft.strength === "shared_attribute_rarity") {
    strength = { kind: "shared_attribute_rarity", reaches: Number(draft.reaches), scope: draft.rarityScope };
  }
  const holds = draft.runs === "pre_commit" && draft.onHit === "hold";
  // A rule just for its author runs after each load commits, or on a schedule; a whole-deployment
  // rule never runs on a schedule (it is judged within each loading case).
  const runs =
    draft.runs === "schedule" && draft.scope !== "deployment"
      ? "schedule"
      : draft.scope === "just_me"
        ? "post_commit"
        : draft.runs === "schedule"
          ? "post_commit"
          : draft.runs;
  const schedule =
    runs === "schedule"
      ? { every: draft.every, hour: Number(draft.hour), weekday: draft.every === "weekly" ? Number(draft.weekday) : null }
      : null;
  return {
    subject: draft.subject,
    conditions: draft.conditions.map(condition),
    relationship,
    frequency,
    strength,
    severity: draft.severity,
    team: draft.scope === "just_me" ? "case" : draft.team,
    runs,
    on_hit: holds && draft.scope !== "just_me" ? "hold" : "load",
    scope: draft.scope,
    // Sent only for a rule that runs on a schedule: a sentence that runs as data loads names none.
    ...(schedule ? { schedule } : {}),
  } as unknown as RuleSentence;
}

type Loose = Record<string, unknown>;

/** The server's sentence (read back from a drawn pattern) as a draft the builder can show. */
export function fromSentence(sentence: RuleSentence): SentenceDraft {
  const draft = emptyDraft(sentence.subject);
  draft.conditions = (sentence.conditions as unknown as Loose[]).map((c) => {
    const row = emptyCondition(String(c.property), c.op as Op);
    if (c.op === "equals") row.value = String(c.value);
    if (c.op === "above" || c.op === "below") row.value = String(c.value);
    if (c.op === "one_of") row.values = [...(c.values as string[])];
    if (c.op === "within_time") {
      row.start = c.start ? String(c.start).slice(0, 10) : "";
      row.end = c.end ? String(c.end).slice(0, 10) : "";
    }
    if (c.op === "within_area") row.area = boxOf(c.area as { name?: string; points: { lon: number; lat: number }[] });
    return row;
  });
  const r = sentence.relationship as unknown as Loose | null | undefined;
  if (r) {
    draft.relationship = r.kind as RelationshipKind;
    if (r.link_type) draft.linkType = String(r.link_type);
    if (r.other_type) draft.otherType = String(r.other_type);
    if (r.steps) draft.steps = String(r.steps);
    if (r.min_score) draft.minScore = String(r.min_score);
    if (r.area) draft.area = boxOf(r.area as { name?: string; points: { lon: number; lat: number }[] });
  }
  const f = sentence.frequency as unknown as Loose | null | undefined;
  if (f) {
    draft.frequency = f.kind as FrequencyKind;
    draft.frequencyLink = String(f.link_type);
    if (f.at_least) draft.atLeast = String(f.at_least);
    if (f.within_days) draft.withinDays = String(f.within_days);
    if (f.amount_property) draft.amountProperty = String(f.amount_property);
    if (f.over) draft.over = String(f.over);
  }
  const st = (sentence as unknown as { strength?: Loose | null }).strength;
  if (st) {
    draft.strength = st.kind as StrengthKind;
    draft.reaches = String(st.reaches);
    if (st.link_type) draft.strengthLink = String(st.link_type);
    if (st.other_type) draft.strengthOther = String(st.other_type);
    if (st.scope) draft.rarityScope = st.scope === "case" ? "case" : "dataset";
  }
  draft.severity = (sentence.severity ?? "medium") as SentenceDraft["severity"];
  draft.team = (sentence.team ?? "case") as SentenceDraft["team"];
  draft.runs = (sentence.runs ?? "post_commit") as SentenceDraft["runs"];
  draft.onHit = (sentence.on_hit ?? "load") as SentenceDraft["onHit"];
  draft.scope = (sentence.scope ?? "this_case") as Scope;
  const schedule = (sentence as unknown as { schedule?: { every: string; hour: number; weekday?: number | null } | null }).schedule;
  if (schedule) {
    draft.every = schedule.every === "weekly" ? "weekly" : "daily";
    draft.hour = String(schedule.hour);
    draft.weekday = String(schedule.weekday ?? 1);
  }
  return draft;
}

/** Why the draft cannot be sent yet, in words, or `null` when every blank is filled. */
export function unfinished(draft: SentenceDraft): string | null {
  for (const c of draft.conditions) {
    if (!c.property) return "Choose a property for each condition.";
    if ((c.op === "equals" || c.op === "above" || c.op === "below") && c.value.trim() === "") return `Give a value for “${c.property}”.`;
    if (c.op === "one_of" && c.values.length < 2) return `Choose at least two values for “${c.property}”.`;
    if (c.op === "within_time" && !c.start && !c.end) return `Give a start, an end or both for “${c.property}”.`;
    if (c.op === "within_area" && [c.area.west, c.area.south, c.area.east, c.area.north].some((v) => v.trim() === "")) return "Give the area's four corners.";
  }
  if ((draft.relationship === "linked" || draft.relationship === "at_location") && !draft.linkType) return "Choose the link type.";
  if (draft.relationship === "within_steps" && !draft.otherType) return "Choose what the subject is near.";
  if (draft.relationship === "at_location" && [draft.area.west, draft.area.south, draft.area.east, draft.area.north].some((v) => v.trim() === ""))
    return "Give the area's four corners.";
  if (draft.frequency !== "none" && !draft.frequencyLink) return "Choose the link type whose events are counted.";
  if (draft.frequency === "amount" && !draft.amountProperty) return "Choose the amount to total.";
  if (draft.strength !== "none") {
    const figure = Number(draft.reaches);
    if (!Number.isFinite(figure) || figure <= 0) return "Give the figure the strength or rarity must reach, above 0.";
    if (draft.strength === "connection_strength" && figure > 1) return "A connection strength is at most 1.";
    if (draft.runs === "pre_commit") return "Strength is read from the stored graph, so the rule runs after commit or on a schedule.";
  }
  return null;
}

/** A deployed sentence in short words, for the rules list (the server's words are on its alerts). */
export function sentenceSummary(sentence: RuleSentence): string {
  const a = (noun: string) => `${/^[aeiou]/i.test(noun) ? "an" : "a"} ${noun}`;
  const parts = [`When ${a(sentence.subject)}`];
  const conditions = sentence.conditions as unknown as Loose[];
  if (conditions.length) {
    parts[0] += (
      " whose " +
        conditions
          .map((c) => {
            const name = String(c.property).replace(/_/g, " ");
            if (c.op === "one_of") return `${name} is one of ${(c.values as string[]).join(", ")}`;
            if (c.op === "within_area") return `${name} is within ${(c.area as { name?: string }).name ?? "a drawn area"}`;
            if (c.op === "within_time") return `${name} is within a time window`;
            return `${name} ${OP_WORDS[c.op as Op]} ${String(c.value)}`;
          })
          .join(" and ")
    );
  }
  const r = sentence.relationship as unknown as Loose | null | undefined;
  if (r?.kind === "linked") parts.push(`is linked by ${String(r.link_type)}${r.other_type ? ` to ${a(String(r.other_type))}` : ""}`);
  if (r?.kind === "within_steps") parts.push(`is within ${String(r.steps)} step(s) of ${a(String(r.other_type))}`);
  if (r?.kind === "at_location") parts.push(`is at a location within ${String((r.area as { name?: string }).name ?? "a drawn area")}`);
  if (r?.kind === "on_hotlist") parts.push("is on one of its author's hotlists");
  if (r?.kind === "on_screening_list") parts.push("is on a screening list");
  const f = sentence.frequency as unknown as Loose | null | undefined;
  if (f?.kind === "count") parts.push(`${String(f.at_least)} or more times by ${String(f.link_type)} within ${String(f.within_days)} day(s)`);
  if (f?.kind === "amount") parts.push(`a total ${String(f.amount_property)} over ${String(f.over)} by ${String(f.link_type)} within ${String(f.within_days)} day(s)`);
  if (f?.kind === "first_time") parts.push(`for the first time ever by ${String(f.link_type)}`);
  const st = (sentence as unknown as { strength?: Loose | null }).strength;
  if (st?.kind === "connection_strength")
    parts.push(
      `the connection strength with ${st.other_type ? a(String(st.other_type)) : "anything"}${st.link_type ? ` by ${String(st.link_type)}` : ""} reaches ${String(st.reaches)}`,
    );
  if (st?.kind === "shared_attribute_rarity")
    parts.push(`the shared-attribute rarity with another ${sentence.subject} reaches ${String(st.reaches)}`);
  const whom = { just_me: "its author alone", this_case: sentence.team === "my_team" ? "its author's team" : "the case team", deployment: "every case's team" }[
    (sentence.scope ?? "this_case") as Scope
  ];
  const scheduled =
    sentence.runs === "schedule"
      ? `, ${scheduleWords((sentence as unknown as { schedule?: { every: string; hour: number; weekday?: number | null } }).schedule)}`
      : "";
  return `${parts.join(", ")}: a ${sentence.severity ?? "medium"}-severity alert for ${whom}${scheduled}${sentence.on_hit === "hold" ? ", its rows held for review" : ""}.`;
}
