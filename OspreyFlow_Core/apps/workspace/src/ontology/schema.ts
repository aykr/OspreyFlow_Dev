// Fetches and caches `GET /v1/ontology` (`services/api/app.py`) — the
// channel/shape mapping the Glass needs to render at all
// (`spec/02_GLASS_FRONTEND.md` §4). One fetch per session; the ontology
// does not change while a session is open.
import type { EntityTypeDef, OntologySchema } from "../../../../packages/schemas/generated";
import type { NodeShape } from "../color/nodeVisual";
import type { IconByValueRule } from "../canvas/valueIcons";

export interface EntityVisual {
  channel: string;
  shape: NodeShape;
  /** The ontology's default icon for the type (ADR-079): a name from its closed list, or none. */
  icon?: string | null;
  /** ADR-128 Decision 4: the enum property whose value picks the icon, and the drawing for some of its values. */
  iconByValue?: IconByValueRule;
}

/** `EntityTypeDef.channel`/`.shape` are free-form strings in the schema
 * (validated against the ontology's own JSON Schema server-side, not
 * against this union) — narrowed here so a channel/shape the Glass has no
 * token or SVG generator for fails loudly in development rather than
 * silently rendering nothing. */
const KNOWN_SHAPES: ReadonlySet<string> = new Set([
  "circle",
  "square",
  "diamond",
  "hexagon",
  "triangle",
  "page",
  "pin",
]);

function toEntityVisual(entity: EntityTypeDef): EntityVisual {
  if (!KNOWN_SHAPES.has(entity.shape)) {
    throw new Error(
      `entity type ${JSON.stringify(entity.name)}: shape ${JSON.stringify(entity.shape)} has no Glass SVG generator`,
    );
  }
  const rule = entity.icon_by_value;
  return {
    channel: entity.channel,
    shape: entity.shape as NodeShape,
    icon: entity.icon ?? null,
    ...(rule ? { iconByValue: { property: rule.property, icons: { ...rule.icons } } } : {}),
  };
}

export class OntologyRegistry {
  private readonly byType = new Map<string, EntityVisual>();
  private readonly identifiers = new Map<string, readonly string[]>();

  constructor(schema: OntologySchema) {
    for (const entity of schema.entity_types) {
      this.byType.set(entity.name, toEntityVisual(entity));
      this.identifiers.set(entity.name, entity.identifiers ?? []);
    }
  }

  visualFor(entityType: string): EntityVisual | undefined {
    return this.byType.get(entityType);
  }

  /** The type's identifying properties; a label drawn from one is a literal value (ADR-097). */
  identifiersFor(entityType: string): readonly string[] {
    return this.identifiers.get(entityType) ?? [];
  }
}

export async function fetchOntologyRegistry(
  baseUrl: string,
  bearerToken: string,
): Promise<OntologyRegistry> {
  const response = await fetch(`${baseUrl}/v1/ontology`, {
    headers: { Authorization: `Bearer ${bearerToken}` },
  });
  if (!response.ok) {
    throw new Error(`GET /v1/ontology failed: ${response.status}`);
  }
  const schema = (await response.json()) as OntologySchema;
  return new OntologyRegistry(schema);
}
