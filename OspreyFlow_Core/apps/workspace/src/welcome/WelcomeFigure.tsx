// The welcome page's product figure (ADR-115 E2): the graph, its timeline, a map inset and a report
// pack tile, with the legend of shapes and strokes — a picture of the product, drawn from `figure.ts`.
import mapPicture from "./assets/screen-map.jpg";
import { buildFigure, KINDS, shapePath, SPARKLINE, timelineBars } from "./figure";

const FIGURE = buildFigure();
const TIMELINE = timelineBars();
const STROKES = [
  { name: "From a record", dash: "" },
  { name: "Inferred", dash: "4 3" },
  { name: "Unresolved", dash: "1 3" },
];

export function WelcomeFigure() {
  const windowLeft = (TIMELINE.from / TIMELINE.bars.length) * 100;
  const windowWidth = ((TIMELINE.to - TIMELINE.from + 1) / TIMELINE.bars.length) * 100;
  return (
    <figure className="welcome-figure">
      <div className="welcome-figure__head">
        <span className="welcome-figure__case">
          <span className="welcome-figure__name">Operation Ledger</span>
          <span className="value welcome-figure__meta">synthetic</span>
        </span>
        <span className="value welcome-figure__meta welcome-figure__counts">
          <span>{FIGURE.nodes.length} entities</span>
          <span>{FIGURE.edges.length} links</span>
        </span>
      </div>
      <div className="welcome-figure__body">
        <div className="welcome-figure__main">
          <div className="welcome-figure__canvas network-canvas">
            <svg viewBox="0 0 680 400" width="100%" role="img"
                 aria-label="Example network: five groups of people, companies, accounts and addresses, with one path traced between two groups">
              {FIGURE.edges.map((e, i) => (
                <line key={i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2} strokeDasharray={e.dash || undefined} strokeLinecap="round"
                      className={e.path ? "welcome-figure__path" : e.dim ? "welcome-figure__edge--dim" : "welcome-figure__edge"} />
              ))}
              {FIGURE.nodes.map((n, i) => (
                <path key={i} d={n.d} fillRule="evenodd" style={{ fill: n.fill, stroke: n.stroke, strokeWidth: n.strokeWidth }} />
              ))}
              <circle cx={FIGURE.selected.x} cy={FIGURE.selected.y} r="14" className="welcome-figure__selected" />
            </svg>
            {FIGURE.labels.map((l) => (
              <span key={l.text} aria-hidden="true"
                    className={["welcome-figure__label", l.mono ? "value" : "", l.dim ? "welcome-figure__label--dim" : ""].join(" ")}
                    style={{ left: `${l.left}%`, top: `${l.top}%`, transform: `translate(${l.hangLeft ? "-100%" : "0"}, ${l.below ? "0" : "-100%"})` }}>
                {l.text}
              </span>
            ))}
          </div>
          <div className="welcome-figure__timeline">
            <div className="welcome-figure__row">
              <span className="welcome-figure__name">Timeline</span>
              <span className="value welcome-figure__meta">11–19 Mar selected</span>
            </div>
            <div className="welcome-figure__bars" aria-hidden="true">
              {TIMELINE.bars.map((b, i) => (
                <span key={i} style={{ height: b.height }} className={b.inWindow ? "welcome-figure__bar--in" : "welcome-figure__bar"} />
              ))}
              <span className="welcome-figure__brush" style={{ left: `${windowLeft}%`, width: `${windowWidth}%` }} />
            </div>
            <div className="value welcome-figure__meta welcome-figure__ticks">
              <span>1 Mar</span>
              <span>14 Mar</span>
              <span>28 Mar</span>
            </div>
          </div>
        </div>
        <div className="welcome-figure__side">
          <div className="welcome-figure__tile">
            <div className="welcome-figure__row">
              <span className="welcome-figure__name">Map</span>
              <span className="welcome-figure__meta">Basemap</span>
            </div>
            <div className="welcome-figure__map">
              <img src={mapPicture} alt="" />
            </div>
          </div>
          <div className="welcome-figure__tile">
            <div className="welcome-figure__row">
              <span className="welcome-figure__name">Report pack</span>
              <span className="value welcome-figure__meta">v3</span>
            </div>
            <div className="welcome-figure__pack">
              <div>
                <div>Value transacted, weekly</div>
                <div className="welcome-figure__spark" aria-hidden="true">
                  {SPARKLINE.map((v, i) => (
                    <span key={i} style={{ height: v }} />
                  ))}
                </div>
              </div>
              <div>
                Assessment: <b>likely</b> <span className="value welcome-figure__meta">55–75%</span>
              </div>
              <div className="welcome-figure__withheld">1 item withheld from this reader</div>
            </div>
          </div>
        </div>
      </div>
      <figcaption className="welcome-figure__legend">
        {Object.values(KINDS).map((k) => (
          <span key={k.name} className="welcome-figure__key">
            <svg width="12" height="12" viewBox="-7 -7 14 14" aria-hidden="true">
              <path d={shapePath(k.shape, 0, 0, 5)} fillRule="evenodd" style={{ fill: `var(--ch-${k.channel})` }} />
            </svg>
            {k.name}
          </span>
        ))}
        <span className="welcome-figure__spacer" />
        {STROKES.map((s) => (
          <span key={s.name} className="welcome-figure__key">
            <svg width="22" height="8" aria-hidden="true">
              <line x1="1" y1="4" x2="21" y2="4" strokeDasharray={s.dash || undefined} className="welcome-figure__stroke" />
            </svg>
            {s.name}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
