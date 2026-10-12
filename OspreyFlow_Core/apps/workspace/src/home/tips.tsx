// Home's "Ways of working" (ADR-115 E3): four habits of the Glass, each with its own small picture,
// in the handoff's words.
const DIM_BARS = [14, 22, 11, 26, 18, 9, 21, 15, 24, 32, 36, 29, 38, 33, 30, 27, 17, 12, 20, 16, 10, 23, 13, 19];

export const TIPS = [
  { kind: "dim", title: "Dim, do not remove", app: "Glass",
    says: "Brushing the timeline fades everything outside the window. The network stays where you left it, so you can see what changed without losing your place." },
  { kind: "stroke", title: "Read a link's stroke", app: "Glass",
    says: "A solid link comes from a source record. A dashed one was inferred by the model and carries a confidence score. A dotted one has a single unverified source." },
  { kind: "count", title: "Counted before drawn", app: "Glass",
    says: "Expanding a node shows how many links of each kind it has before anything is added to the canvas. An expansion over the working-set limit is refused with options." },
  { kind: "branch", title: "Branch, then cut down", app: "Glass",
    says: "Select a group and branch it into a new workspace to work on it on its own. The original case is unchanged, and both stay linked in the history." },
] as const; // prettier-ignore

export function TipPicture({ kind }: { kind: (typeof TIPS)[number]["kind"] }) {
  if (kind === "dim") {
    return (
      <div className="home-tip-pic" aria-hidden="true">
        <div className="home-tip-pic__bars">
          {DIM_BARS.map((h, i) => (
            <span key={i} style={{ height: h }} className={i >= 9 && i <= 15 ? "home-tip-pic__bar--in" : "home-tip-pic__bar"} />
          ))}
          <span className="home-tip-pic__brush" />
        </div>
        <div className="home-tip-pic__labels value"><span>dimmed</span><span>in window</span><span>dimmed</span></div>
      </div>
    );
  }
  if (kind === "stroke") {
    return (
      <div className="home-tip-pic home-tip-pic__list" aria-hidden="true">
        {[["From a record", ""], ["Inferred, with confidence", "4 3"], ["Single source", "1 3"]].map(([name, dash]) => (
          <span key={name} className="home-tip-pic__key">
            <svg width="40" height="8"><line x1="1" y1="4" x2="39" y2="4" strokeDasharray={dash || undefined} className="home-tip-pic__stroke" /></svg>
            {name}
          </span>
        ))}
      </div>
    );
  }
  if (kind === "count") {
    return (
      <div className="home-tip-pic home-tip-pic__list" aria-hidden="true">
        {[["Present at", "22"], ["Associate of", "9"], ["Mentioned in", "4"]].map(([name, n]) => (
          <span key={name} className="home-tip-pic__count"><span>{name}</span><span className="value">{n}</span></span>
        ))}
      </div>
    );
  }
  return (
    <svg className="home-tip-pic" viewBox="0 0 240 80" width="100%" height="80" aria-hidden="true">
      <rect x="8" y="14" width="96" height="52" className="home-tip-pic__frame" />
      <rect x="136" y="14" width="96" height="52" className="home-tip-pic__frame" />
      <path d="M104 40h32" className="home-tip-pic__link" />
      <circle cx="40" cy="40" r="6" style={{ fill: "var(--ch-indigo)" }} /><circle cx="72" cy="30" r="5" style={{ fill: "var(--ch-azure)" }} />
      <circle cx="168" cy="40" r="6" style={{ fill: "var(--ch-indigo)" }} /><circle cx="200" cy="30" r="5" style={{ fill: "var(--ch-azure)" }} />
    </svg>
  );
}
