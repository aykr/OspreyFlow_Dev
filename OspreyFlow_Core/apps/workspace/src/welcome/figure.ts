// The welcome page's product figure (ADR-115 E2): a synthetic Operation Ledger network of five groups,
// one path traced between four of them, one hub selected and one group dimmed — drawn as the canvas
// draws (DESIGN.md §3.4 shapes and channels, §3.7 states, §3.8 provenance strokes). Seeded, so the
// picture is the same for every visitor; the layout is the handoff's own (`OspreyFlow Welcome.dc.html`).

export type Channel = "indigo" | "azure" | "jade" | "ochre" | "rose" | "violet";
type Shape = "circle" | "square" | "rounded" | "diamond" | "triangle" | "ring";
type Kind = "person" | "company" | "account" | "address" | "phone" | "doc";

export const KINDS: Record<Kind, { channel: Channel; shape: Shape; name: string }> = {
  person: { channel: "indigo", shape: "circle", name: "Person" },
  company: { channel: "azure", shape: "square", name: "Organisation" },
  account: { channel: "jade", shape: "rounded", name: "Account" },
  address: { channel: "ochre", shape: "ring", name: "Location" },
  phone: { channel: "rose", shape: "triangle", name: "Phone" },
  doc: { channel: "violet", shape: "diamond", name: "Document" },
};

export interface FigureNode {
  d: string;
  fill: string;
  stroke: string;
  strokeWidth: number;
  dim: boolean;
}
export interface FigureEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  dash: "" | "4 3" | "1 3";
  path: boolean;
  dim: boolean;
}
export interface FigureLabel {
  text: string;
  /** Position as a percentage of the 680×400 picture, and which side of it the label hangs. */
  left: number;
  top: number;
  hangLeft: boolean;
  below: boolean;
  mono: boolean;
  dim: boolean;
}
export interface Figure {
  nodes: FigureNode[];
  edges: FigureEdge[];
  labels: FigureLabel[];
  selected: { x: number; y: number };
}

const fmt = (n: number) => n.toFixed(1);

/** A node's outline at (x, y), radius r — the six shapes DESIGN.md §3.4 crosses with the channels. */
export function shapePath(shape: Shape, x: number, y: number, r: number): string {
  if (shape === "circle") return `M${fmt(x - r)} ${fmt(y)}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`;
  if (shape === "square") {
    const q = r * 0.9;
    return `M${fmt(x - q)} ${fmt(y - q)}h${fmt(2 * q)}v${fmt(2 * q)}h${fmt(-2 * q)}Z`;
  }
  if (shape === "rounded") {
    const q = r * 0.92;
    const c = r * 0.4;
    return (
      `M${fmt(x - q + c)} ${fmt(y - q)}H${fmt(x + q - c)}Q${fmt(x + q)} ${fmt(y - q)} ${fmt(x + q)} ${fmt(y - q + c)}` +
      `V${fmt(y + q - c)}Q${fmt(x + q)} ${fmt(y + q)} ${fmt(x + q - c)} ${fmt(y + q)}H${fmt(x - q + c)}` +
      `Q${fmt(x - q)} ${fmt(y + q)} ${fmt(x - q)} ${fmt(y + q - c)}V${fmt(y - q + c)}Q${fmt(x - q)} ${fmt(y - q)} ${fmt(x - q + c)} ${fmt(y - q)}Z`
    );
  }
  if (shape === "diamond") {
    const q = r * 1.2;
    return `M${fmt(x)} ${fmt(y - q)}L${fmt(x + q)} ${fmt(y)}L${fmt(x)} ${fmt(y + q)}L${fmt(x - q)} ${fmt(y)}Z`;
  }
  if (shape === "triangle") {
    const q = r * 1.15;
    return `M${fmt(x)} ${fmt(y - q)}L${fmt(x + q)} ${fmt(y + q * 0.75)}L${fmt(x - q)} ${fmt(y + q * 0.75)}Z`;
  }
  const ri = r * 0.45;
  return (
    `M${fmt(x - r)} ${fmt(y)}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z` +
    `M${fmt(x - ri)} ${fmt(y)}a${ri} ${ri} 0 1 1 ${2 * ri} 0a${ri} ${ri} 0 1 1 ${-2 * ri} 0Z`
  );
}

function seeded(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

interface Group {
  x: number;
  y: number;
  n: number;
  hub: Kind;
  mix: Kind[];
  label: string;
  mono: boolean;
  dim?: boolean;
  dx: number;
  dy: number;
  hangLeft?: boolean;
  below?: boolean;
}

const GROUPS: Group[] = [
  { x: 150, y: 120, n: 11, hub: "person", mix: ["account", "account", "phone", "address", "company"], label: "HALE, Marcus", mono: false, dx: 12, dy: -11 },
  { x: 360, y: 92, n: 9, hub: "company", mix: ["person", "account", "address", "doc"], label: "Hale Logistics Ltd", mono: false, dx: 12, dy: -11 },
  { x: 560, y: 140, n: 12, hub: "account", mix: ["account", "account", "person", "phone"], label: "60-16-13 ••19", mono: true, dx: -12, dy: -11, hangLeft: true },
  { x: 470, y: 300, n: 10, hub: "person", mix: ["phone", "address", "account", "doc"], label: "CARTER, Jamal", mono: false, dx: 12, dy: 12, below: true },
  { x: 220, y: 300, n: 9, hub: "company", mix: ["person", "account", "address"], label: "Brightpath Consulting Ltd", mono: false, dim: true, dx: 12, dy: -11 },
];

const DASH = { solid: "", dashed: "4 3", dotted: "1 3" } as const;

export function buildFigure(): Figure {
  const rnd = seeded(11);
  type Point = { x: number; y: number; kind: Kind; r: number; dim: boolean; group: number };
  type Link = { a: Point; b: Point; style: keyof typeof DASH; dim: boolean; path?: boolean };
  const points: Point[] = [];
  const links: Link[] = [];
  const hubs: Point[] = [];
  const labels: FigureLabel[] = [];
  GROUPS.forEach((g, group) => {
    const hub: Point = { x: g.x, y: g.y, kind: g.hub, r: 8, dim: !!g.dim, group };
    points.push(hub);
    hubs.push(hub);
    const members: Point[] = [];
    for (let i = 0; i < g.n; i++) {
      const angle = (i / g.n) * Math.PI * 2 + rnd() * 0.5;
      const distance = 34 + rnd() * 46;
      const member: Point = {
        x: Math.max(12, Math.min(668, g.x + Math.cos(angle) * distance * 1.15)),
        y: Math.max(12, Math.min(388, g.y + Math.sin(angle) * distance * 0.85)),
        kind: g.mix[Math.floor(rnd() * g.mix.length)]!,
        r: 5,
        dim: !!g.dim,
        group,
      };
      points.push(member);
      members.push(member);
      links.push({ a: hub, b: member, style: rnd() < 0.72 ? "solid" : rnd() < 0.6 ? "dashed" : "dotted", dim: !!g.dim });
    }
    for (let i = 0; i < members.length; i++) {
      if (rnd() < 0.28) {
        const b = members[(i + 1 + Math.floor(rnd() * 3)) % members.length]!;
        links.push({ a: members[i]!, b, style: rnd() < 0.5 ? "solid" : "dashed", dim: !!g.dim });
      }
    }
    labels.push({
      text: g.label,
      left: ((g.x + g.dx) / 680) * 100,
      top: ((g.y + g.dy) / 400) * 100,
      hangLeft: !!g.hangLeft,
      below: !!g.below,
      mono: g.mono,
      dim: !!g.dim,
    });
  });
  for (const [i, j] of [[0, 1], [1, 2], [2, 3]] as const) {
    links.push({ a: hubs[i]!, b: hubs[j]!, style: "solid", path: true, dim: false });
  }
  links.push({ a: hubs[0]!, b: hubs[4]!, style: "dashed", dim: true });
  links.push({ a: hubs[3]!, b: hubs[4]!, style: "dotted", dim: true });
  const onPath = new Set([0, 1, 2, 3]);
  return {
    nodes: points.map((p) => {
      const channel = `var(--ch-${KINDS[p.kind].channel})`;
      const isHub = p.r === 8;
      return {
        d: shapePath(KINDS[p.kind].shape, p.x, p.y, p.r),
        fill: p.dim ? `color-mix(in oklab, ${channel} 32%, var(--surface-panel))` : channel,
        stroke: isHub && onPath.has(p.group) && !p.dim ? "var(--text-primary)" : "var(--surface-app)",
        strokeWidth: isHub ? 1.5 : 1,
        dim: p.dim,
      };
    }),
    edges: links.map((l) => ({
      x1: l.a.x,
      y1: l.a.y,
      x2: l.b.x,
      y2: l.b.y,
      dash: DASH[l.style],
      path: !!l.path,
      dim: l.dim,
    })),
    labels,
    selected: { x: hubs[1]!.x, y: hubs[1]!.y },
  };
}

/** The figure's timeline: 28 days, a window of days 10 to 18 drawn in the darker ramp step. */
export function timelineBars(): { bars: { height: number; inWindow: boolean }[]; from: number; to: number } {
  const rnd = seeded(5);
  const from = 10;
  const to = 18;
  const bars = Array.from({ length: 28 }, (_, i) => {
    const base = 6 + rnd() * 12 + (i >= 12 && i <= 16 ? 14 : 0) + (i % 7 === 6 ? -5 : 0);
    return { height: Math.max(3, Math.round(base)), inWindow: i >= from && i <= to };
  });
  return { bars, from, to };
}

/** The report pack tile's weekly sparkline. */
export const SPARKLINE = [5, 7, 6, 9, 8, 12, 10, 15, 13, 18] as const;
