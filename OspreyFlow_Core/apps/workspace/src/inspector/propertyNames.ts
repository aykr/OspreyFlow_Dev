// How the Inspector names an entity's properties (build order step 30; CLAUDE.md rule 7): by what a
// person reads, never by the key the store holds, and without the references that mean something only
// to a store or to the system a record came from.

/** The stores' own keys on a node, which identify a record to a store and nothing to a person: an
 * event's id in the analytics store, an email's message header, a rule's id (an alert is read by its
 * words). The ontology's `*_ref` names are the same kind (below). */
const STORE_KEYS = new Set(["event_id", "message_id", "rule_id"]);

/** Whether a property is a reference no analyst reads: every `*_ref` (the ontology's category of
 * deployment-internal references, `default.yaml` v8: `site_ref` "pid:est1:wing:F", `org_ref`,
 * `incident_ref`; and `geometry_ref`/`object_ref`, which point into the analytics and object stores),
 * and the stores' own keys. The value is still on the node for the Glass's own use (the map resolves
 * `geometry_ref`); it is only not shown. */
export function isInternalReference(key: string): boolean {
  return key.endsWith("_ref") || STORE_KEYS.has(key);
}

/** A property's key as a person reads it, the same rule ADR-091 decision 2 gives a link type:
 * `prison_number` reads "Prison number". */
export function propertyLabel(key: string): string {
  const words = key.split("_").filter(Boolean).join(" ");
  if (!words) return key;
  return words.charAt(0).toUpperCase() + words.slice(1);
}
