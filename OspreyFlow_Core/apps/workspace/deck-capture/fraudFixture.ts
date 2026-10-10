// "Operation Ledger" — the deck's synthetic financial-fraud fixture (rule 9: synthetic, in-repo).
// A structuring ring in the West Midlands: cash deposited just under the reporting threshold into
// a shell company, moved fast to a second shell, and invoiced back to the ringleader's real firm.
// Shaped exactly as the Vault would serve it: the POLE core plus the FIBO pack's Account,
// BENEFICIAL_OWNER_OF, CONTROLS, HOLDS_ACCOUNT and widened TRANSACTED (ADR-108 phase D).
import type { Edge, Node, OntologySchema } from "../../../packages/schemas/generated";

export const FRAUD_SCHEMA: OntologySchema = {
  version: 14,
  entity_types: [
    { name: "Person", pole_class: "person", channel: "indigo", shape: "circle" },
    { name: "Organisation", pole_class: "organisation", channel: "azure", shape: "square" },
    { name: "Account", pole_class: "object", channel: "jade", shape: "hexagon" },
    { name: "Location", pole_class: "location", channel: "ochre", shape: "pin" },
    { name: "Document", pole_class: "object", channel: "violet", shape: "page" },
    { name: "Endpoint", pole_class: "object", channel: "cyan", shape: "hexagon" },
  ],
  edge_types: [
    { name: "ASSOCIATE_OF", from: ["Person"], to: ["Person"], directed: false, basis: "direct" },
    { name: "MEMBER_OF", from: ["Person"], to: ["Organisation"], directed: true, basis: "direct" },
    {
      name: "BENEFICIAL_OWNER_OF",
      from: ["Person", "Organisation"],
      to: ["Organisation", "Account"],
      directed: true,
      basis: "direct",
    },
    {
      name: "CONTROLS",
      from: ["Person", "Organisation"],
      to: ["Organisation", "Account"],
      directed: true,
      basis: "direct",
    },
    { name: "HOLDS_ACCOUNT", from: ["Person", "Organisation"], to: ["Account"], directed: true, basis: "direct" },
    { name: "TRANSACTED", from: ["Account"], to: ["Account"], directed: true, basis: "direct" },
    { name: "REGISTERED_AT", from: ["Organisation"], to: ["Location"], directed: true, basis: "direct" },
    { name: "PRESENT_AT", from: ["Person"], to: ["Location"], directed: true, basis: "direct" },
    { name: "MENTIONED_IN", from: ["*"], to: ["Document"], directed: true, basis: "direct" },
    { name: "USES", from: ["Person"], to: ["Endpoint"], directed: true, basis: "direct" },
  ],
} as unknown as OntologySchema;

const PROV = {
  state: "asserted",
  sources: [{ document_id: "sar:2026-0412", locator: "row 1", excerpt_hash: "a".repeat(64) }],
  first_seen: "2026-09-01T00:00:00Z",
} as const;
const HANDLING = {
  classification: "OFFICIAL",
  handling_code: "P",
  originator: "unit-1",
  owning_unit: "unit-1",
} as const;
const AUDIT = { created_at: "2026-09-01T00:00:00Z", created_by: "fixture" } as const;

export function fraudNode(id: string, type: string, properties: Record<string, unknown>, extra: Partial<Node> = {}): Node {
  return { id, type, properties, provenance: PROV, handling: HANDLING, audit: AUDIT, ...extra } as Node;
}

export function fraudEdge(
  id: string,
  type: string,
  source: string,
  target: string,
  properties: Record<string, unknown> = {},
  extra: Partial<Edge> = {},
): Edge {
  return { id, type, source, target, properties, provenance: PROV, handling: HANDLING, audit: AUDIT, ...extra } as Edge;
}

function person(id: string, family: string, given: string): Node {
  return fraudNode(id, "Person", { family_name: family, given_names: given });
}
function company(id: string, name: string, companyNumber: string): Node {
  return fraudNode(id, "Organisation", { name, company_number: companyNumber });
}
function account(id: string, iban: string, institution: string, name: string): Node {
  return fraudNode(id, "Account", { name, account_number: iban, institution, currency: "GBP" });
}

export const PEOPLE = {
  hale: person("p-hale", "HALE", "Marcus"),
  nair: person("p-nair", "NAIR", "Priya"),
  petrov: person("p-petrov", "PETROV", "Elena"),
  carter: person("p-carter", "CARTER", "Jamal"),
  ruiz: person("p-ruiz", "RUIZ", "Sofia"),
  zelinsky: person("p-zelinsky", "ZELINSKY", "Tomas"),
};

export const COMPANIES = {
  haleLogistics: company("o-hale-log", "Hale Logistics Ltd", "09418821"),
  brightpath: company("o-brightpath", "Brightpath Consulting Ltd", "14092733"),
  crescent: company("o-crescent", "Crescent Imports Ltd", "13550917"),
};

export const ACCOUNTS = {
  haleBiz: account("a-hale-biz", "GB29 NWBK 6016 1331 9268 19", "NatWest", "Hale Logistics · NatWest …68 19"),
  brightpath: account("a-brightpath", "GB94 BARC 2003 5538 2998 12", "Barclays", "Brightpath · Barclays …98 12"),
  crescent: account("a-crescent", "GB33 HBUK 4012 7612 3456 01", "HSBC", "Crescent · HSBC …56 01"),
  carter: account("a-carter", "GB58 LOYD 3096 1700 7099 43", "Lloyds", "Carter · Lloyds …99 43"),
  ruiz: account("a-ruiz", "GB82 MONZ 0400 0412 8831 22", "Monzo", "Ruiz · Monzo …31 22"),
  zelinsky: account("a-zelinsky", "GB21 SRLG 6083 0199 2204 87", "Starling", "Zelinsky · Starling …04 87"),
};

export const LOCATIONS = {
  brightpathOffice: fraudNode("l-bright-office", "Location", {
    name: "Suite 14, 83 Colmore Row, Birmingham",
    geometry_ref: "pt:colmore-row",
  }),
  haleDepot: fraudNode("l-hale-depot", "Location", {
    name: "Unit 6, Pleck Industrial Estate, Walsall",
    geometry_ref: "pt:pleck",
  }),
  crescentOffice: fraudNode("l-crescent-office", "Location", {
    name: "Level 2, 71 Fenchurch Street, London",
    geometry_ref: "pt:fenchurch",
  }),
  carterAddress: fraudNode("l-carter-home", "Location", {
    name: "Dunstall Road, Wolverhampton",
    geometry_ref: "pt:dunstall",
  }),
};

/** WGS84, synthetic but plausible, for the map's own markers. */
export const COORDINATES: Record<string, { lat: number; lng: number }> = {
  "l-bright-office": { lat: 52.4809, lng: -1.9005 },
  "l-hale-depot": { lat: 52.5743, lng: -1.9994 },
  "l-crescent-office": { lat: 51.5119, lng: -0.0807 },
  "l-carter-home": { lat: 52.5926, lng: -2.1416 },
};

export const SAR_DOCUMENT = fraudNode("doc-sar-0412", "Document", {
  title: "SAR 2026-0412 — Brightpath Consulting Ltd",
  media_kind: "text",
});

/** The SAR narrative the reader opens: what extraction finds its entities in. Entirely synthetic;
 * the phone number is an Ofcom drama-range MSISDN. */
export const SAR_TEXT =
  "Suspicious activity report, 12 September 2026. Over eleven banking days, nine cash deposits " +
  "of between £9,400 and £9,850 were made into the Barclays account of Brightpath Consulting Ltd, " +
  "each below the £10,000 reporting threshold, at branches in Birmingham, Walsall and " +
  "Wolverhampton. The deposits were made by Jamal Carter, Sofia Ruiz and Tomas Zelinsky. Within " +
  "48 hours of the final deposit, £84,000 was transferred to Crescent Imports Ltd, and £82,500 " +
  "returned to Hale Logistics Ltd against invoice CI-2026-118 for logistics services. The sole " +
  "listed director of Brightpath Consulting Ltd is Elena Petrov; branch staff state the account " +
  "was opened in the company of Marcus Hale, who was contactable on 07700 900461 and " +
  "m.hale@halelogistics.example.co.uk. The registered office, Suite 14, 83 Colmore Row, " +
  "Birmingham, is a mail-forwarding address.";

export const FRAUD_NODES: Node[] = [
  ...Object.values(PEOPLE),
  ...Object.values(COMPANIES),
  ...Object.values(ACCOUNTS),
  ...Object.values(LOCATIONS),
  SAR_DOCUMENT,
];

function transacted(id: string, from: string, to: string, amount: number, at: string, reference: string): Edge {
  return fraudEdge(id, "TRANSACTED", from, to, { amount, currency: "GBP", at, reference });
}

export const FRAUD_EDGES: Edge[] = [
  // Who runs what. PETROV is the nominee on paper; HALE's control is the engine's inference.
  fraudEdge("e-petrov-bo", "BENEFICIAL_OWNER_OF", "p-petrov", "o-brightpath", { percent: 100, nature: "sole director" }),
  fraudEdge("e-hale-controls", "CONTROLS", "p-hale", "o-brightpath", { capacity: "de facto" }, {
    provenance: { ...PROV, state: "inferred", extracted_by: "model:spacy:en_core_web_sm-3.8.0" },
  }),
  fraudEdge("e-hale-owns", "BENEFICIAL_OWNER_OF", "p-hale", "o-hale-log", { percent: 100 }),
  fraudEdge("e-nair-member", "MEMBER_OF", "p-nair", "o-hale-log", { role: "accountant" }),
  // Accounts.
  fraudEdge("e-acc-1", "HOLDS_ACCOUNT", "o-hale-log", "a-hale-biz"),
  fraudEdge("e-acc-2", "HOLDS_ACCOUNT", "o-brightpath", "a-brightpath"),
  fraudEdge("e-acc-3", "HOLDS_ACCOUNT", "o-crescent", "a-crescent"),
  fraudEdge("e-acc-4", "HOLDS_ACCOUNT", "p-carter", "a-carter"),
  fraudEdge("e-acc-5", "HOLDS_ACCOUNT", "p-ruiz", "a-ruiz"),
  fraudEdge("e-acc-6", "HOLDS_ACCOUNT", "p-zelinsky", "a-zelinsky"),
  // The ring's own ties.
  fraudEdge("e-assoc-1", "ASSOCIATE_OF", "p-hale", "p-nair"),
  fraudEdge("e-assoc-2", "ASSOCIATE_OF", "p-hale", "p-carter"),
  fraudEdge("e-assoc-3", "ASSOCIATE_OF", "p-carter", "p-ruiz"),
  fraudEdge("e-assoc-4", "ASSOCIATE_OF", "p-carter", "p-zelinsky"),
  // Structuring in: nine deposits under the threshold (three shown per mule account).
  transacted("t-01", "a-carter", "a-brightpath", 9400, "2026-09-01T10:12:00Z", "cash deposit, Birmingham New St"),
  transacted("t-02", "a-ruiz", "a-brightpath", 9750, "2026-09-02T11:03:00Z", "cash deposit, Walsall"),
  transacted("t-03", "a-zelinsky", "a-brightpath", 9600, "2026-09-03T09:48:00Z", "cash deposit, Wolverhampton"),
  transacted("t-04", "a-carter", "a-brightpath", 9850, "2026-09-05T10:31:00Z", "cash deposit, Birmingham New St"),
  transacted("t-05", "a-ruiz", "a-brightpath", 9500, "2026-09-08T12:19:00Z", "cash deposit, Walsall"),
  transacted("t-06", "a-zelinsky", "a-brightpath", 9700, "2026-09-09T09:02:00Z", "cash deposit, Wolverhampton"),
  transacted("t-07", "a-carter", "a-brightpath", 9450, "2026-09-10T10:44:00Z", "cash deposit, Birmingham New St"),
  transacted("t-08", "a-ruiz", "a-brightpath", 9800, "2026-09-11T11:37:00Z", "cash deposit, Walsall"),
  transacted("t-09", "a-zelinsky", "a-brightpath", 9550, "2026-09-12T09:55:00Z", "cash deposit, Wolverhampton"),
  // Rapid movement out, and the circle back.
  transacted("t-10", "a-brightpath", "a-crescent", 84000, "2026-09-13T16:20:00Z", "consultancy fees Q3"),
  transacted("t-11", "a-crescent", "a-hale-biz", 82500, "2026-09-14T09:10:00Z", "invoice CI-2026-118, logistics services"),
  // Places and the SAR.
  fraudEdge("e-reg-1", "REGISTERED_AT", "o-brightpath", "l-bright-office"),
  fraudEdge("e-reg-2", "REGISTERED_AT", "o-hale-log", "l-hale-depot"),
  fraudEdge("e-reg-3", "REGISTERED_AT", "o-crescent", "l-crescent-office"),
  fraudEdge("e-home-1", "PRESENT_AT", "p-carter", "l-carter-home"),
  fraudEdge("e-sar-1", "MENTIONED_IN", "o-brightpath", "doc-sar-0412"),
  fraudEdge("e-sar-2", "MENTIONED_IN", "p-hale", "doc-sar-0412"),
];

/** A finding as the review queue serves it, located in `SAR_TEXT` by real character offsets. */
function candidate(id: string, entityType: string, words: string, properties: Record<string, unknown>) {
  const start = SAR_TEXT.indexOf(words);
  if (start < 0) throw new Error(`candidate words not in SAR_TEXT: ${words}`);
  return {
    id,
    document_id: "doc-sar-0412",
    entity_type: entityType,
    properties,
    confidence: 1,
    model: "spacy:en_core_web_sm-3.8.0",
    locator: `char span ${start}-${start + words.length}`,
    excerpt_hash: "b".repeat(64),
    status: "pending",
  };
}

export const SAR_CANDIDATES = [
  candidate("c-hale", "Person", "Marcus Hale", { family_name: "Hale", given_names: "Marcus" }),
  candidate("c-petrov", "Person", "Elena Petrov", { family_name: "Petrov", given_names: "Elena" }),
  candidate("c-carter", "Person", "Jamal Carter", { family_name: "Carter", given_names: "Jamal" }),
  candidate("c-bright", "Organisation", "Brightpath Consulting Ltd", { name: "Brightpath Consulting Ltd" }),
  candidate("c-crescent", "Organisation", "Crescent Imports Ltd", { name: "Crescent Imports Ltd" }),
  candidate("c-birmingham", "Location", "Birmingham", { name: "Birmingham" }),
  candidate("c-walsall", "Location", "Walsall", { name: "Walsall" }),
  candidate("c-phone", "Endpoint", "07700 900461", {
    value_raw: "07700 900461",
    value_normalised: "+447700900461",
    endpoint_kind: "msisdn",
  }),
  candidate("c-email", "Endpoint", "m.hale@halelogistics.example.co.uk", {
    value_raw: "m.hale@halelogistics.example.co.uk",
    value_normalised: "m.hale@halelogistics.example.co.uk",
    endpoint_kind: "email",
  }),
];

/** The Questions drawer's worked answer (ADR-098 decision 4), with its citations and the pending
 * follow-ups a model proposes — everything `inferred` until a person accepts it (rule 5). */
export const FRAUD_QUESTION = {
  id: "q-1",
  author: "analyst-1",
  author_name: "Avery Whitfield",
  question: "Who controls Brightpath Consulting, and where does its money go?",
  answer:
    "On paper, Brightpath Consulting Ltd is controlled by its sole director Elena Petrov. The SAR " +
    "narrative states the account was opened in the company of Marcus Hale, whose firm Hale " +
    "Logistics Ltd receives the money back: nine structured cash deposits (£9,400–£9,850, below " +
    "the £10,000 threshold) total about £86,600 into Brightpath's Barclays account, £84,000 moves " +
    "to Crescent Imports Ltd within 48 hours, and £82,500 returns to Hale Logistics against " +
    "invoice CI-2026-118.",
  citations: [{ document_id: "doc-sar-0412", title: "SAR 2026-0412 — Brightpath Consulting Ltd" }],
  candidates: [],
  unplaced: 0,
  created_at: "2026-10-10T09:30:00Z",
};
