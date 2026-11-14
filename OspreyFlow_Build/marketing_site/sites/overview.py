"""The animated overview on both home pages: three seats (analyst, developer, administrator), eleven chapters. From the
design the owner approved on 13 November 2026 (`process/lanes/docs/BRIEF_sites2.md`), with every chapter checked
against main and the guides; the record is `process/lanes/docs/sites2-facts.md`. Each chapter returns its title line,
its sub line and its drawing, inline SVG with real text. Every name and figure in them is invented."""
import math, random, html

#: Every colour is a token of `.ov` (light) and `.theme-dark .ov` in `source/site.css`, so the drawing follows the
#: page's theme. tests/test_sites_design.py holds every text pairing in both to 4.5:1.
K = {k: f'var(--k-{k})' for k in ('app', 'panel', 'raised', 'hover', 'bSub', 'b', 'bStr', 't3', 't2', 't1', 'brass', 'brassInk', 'warn', 'err', 'ok',
                                   'ochre', 'rose', 'violet', 'indigo', 'azure', 'jade', 'seq')}
TYPES = {'person': ('indigo', 'circle'), 'company': ('azure', 'square'), 'account': ('jade', 'rounded'),
         'address': ('ochre', 'ring'), 'phone': ('rose', 'triangle'), 'doc': ('violet', 'diamond')}
DUR = 7

def esc(s): return html.escape(s, quote=False)
def an(cls, d):  # animation class + delay
    return f'class="{cls}" ' if d is None else f'class="{cls}" '
def st(d=None, **css):
    parts = [f'{k.replace("_", "-")}: {v}' for k, v in css.items()]
    if d is not None: parts.append(f'animation-delay: {d}s')
    return f'style="{"; ".join(parts)}"' if parts else ''

def text(x, y, s, size=15, fill=None, weight=400, anchor='start', mono=False, d=None, cls='a-fade'):
    c = (cls + ' ' if d is not None else '') + ('mono' if mono else '')
    return (f'<text x="{x}" y="{y}" class="{c.strip()}" '
            f'{st(d, fill=fill or K["t1"], font_size=f"{size}px", font_weight=weight, text_anchor=anchor)}>{esc(s)}</text>')

def rect(x, y, w, h, fill='none', stroke=None, rx=6, sw=1, d=None, cls='a-fade', dash=None):
    css = {'fill': fill, 'stroke': stroke or 'none'}
    if stroke: css['stroke_width'] = sw
    if dash: css['stroke_dasharray'] = dash
    c = f'class="{cls}" ' if d is not None else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" {c}{st(d, **css)}></rect>'

def line(x1, y1, x2, y2, stroke=None, sw=1, d=None, draw=False, dash=None, cls=None):
    stroke = stroke or K['bStr']
    css = {'stroke': stroke, 'stroke_width': sw, 'stroke_linecap': 'round'}
    if dash: css['stroke_dasharray'] = dash
    c = cls or ('a-draw' if draw else 'a-fade')
    extra = ' pathLength="1"' if draw else ''
    cc = f'class="{c}" ' if d is not None else ''
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"{extra} {cc}{st(d, **css)}></line>'

def shape(kind, x, y, r, fill, stroke=None, sw=1, d=None, cls='a-pop', dash=None):
    f = lambda n: f'{n:.1f}'
    if kind == 'circle': p = f'M{f(x-r)} {f(y)}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 {-2*r} 0Z'
    elif kind in ('square', 'rounded'):
        q = r * .9; p = f'M{f(x-q)} {f(y-q)}h{f(2*q)}v{f(2*q)}h{f(-2*q)}Z'
    elif kind == 'diamond':
        q = r * 1.2; p = f'M{f(x)} {f(y-q)}L{f(x+q)} {f(y)}L{f(x)} {f(y+q)}L{f(x-q)} {f(y)}Z'
    elif kind == 'triangle':
        q = r * 1.15; p = f'M{f(x)} {f(y-q)}L{f(x+q)} {f(y+q*.75)}L{f(x-q)} {f(y+q*.75)}Z'
    else:
        ri = r * .45
        p = (f'M{f(x-r)} {f(y)}a{r} {r} 0 1 0 {2*r} 0a{r} {r} 0 1 0 {-2*r} 0Z'
             f'M{f(x-ri)} {f(y)}a{f(ri)} {f(ri)} 0 1 1 {f(2*ri)} 0a{f(ri)} {f(ri)} 0 1 1 {f(-2*ri)} 0Z')
    css = {'fill': fill, 'stroke': stroke or K['app'], 'stroke_width': sw, 'fill_rule': 'evenodd'}
    if dash: css['stroke_dasharray'] = dash
    c = f'class="{cls}" ' if d is not None else ''
    return f'<path d="{p}" {c}{st(d, **css)}></path>'

def node(t, x, y, r=7, d=None, drawn=False, dim=False):
    ch, sh = TYPES[t]
    if drawn: return shape(sh, x, y, r, K['app'], K['warn'], 2, d, dash='4 3')
    return shape(sh, x, y, r, K['bSub'] if dim else K[ch], K['app'], 1.5, d)

def tw(s, size, mono=False): return len(s) * size * (.61 if mono else .56)

def chip(x, y, s, d=None, fill=None, stroke=None, color=None, size=13, mono=False, weight=600, h=26, cls='a-pop'):
    w = tw(s, size, mono) + 20
    g = f'<g class="{cls}" {st(d)}>' if d is not None else '<g>'
    return (g + rect(x, y, round(w), h, fill or K['raised'], stroke or K['b'], rx=h // 2)
            + text(x + 10, y + h / 2 + size * .36, s, size, color or K['t1'], weight, mono=mono) + '</g>'), round(w)

def chips(x, y, items, d0=None, step=.15, gap=8, **kw):
    out = []; cx = x
    for i, s in enumerate(items):
        c, w = chip(cx, y, s, None if d0 is None else round(d0 + i * step, 2), **kw); out.append(c); cx += w + gap
    return ''.join(out)

def panel(x, y, w, h, label, d=0.1):
    return (f'<g class="a-fade" {st(d)}>' + rect(x, y, w, h, K['panel'], K['bSub'], rx=8)
            + rect(x, y, w, 34, K['raised'], K['bSub'], rx=8) + rect(x + 1, y + 20, w - 2, 15, K['raised'], rx=0)
            + line(x, y + 34.5, x + w, y + 34.5, K['bSub'])
            + text(x + 16, y + 22, label, 13, K['t2'], 600) + '</g>')

def svg(label, inner):
    return f'<svg viewBox="0 0 1200 500" role="img" aria-label="{html.escape(label)}" style="display: block; width: 100%; height: auto">{inner}</svg>'

# ---------------------------------------------------------------- analyst
def a0():
    r = random.Random(11); o = [panel(20, 20, 800, 460, 'The Glass · Case · Operation Ledger (synthetic)')]
    hubs = [(170, 180, 'person', 'HALE, Marcus', False), (390, 130, 'company', 'Hale Logistics Ltd', False), (630, 190, 'account', '60-16-13 ••19', False),
            (520, 370, 'person', 'CARTER, Jamal', False), (250, 360, 'company', 'Brightpath Consulting Ltd', True)]
    mix = ['account', 'phone', 'address', 'doc', 'person', 'company']; nodes = []; edges = []
    for hi, (hx, hy, ht, hl, dim) in enumerate(hubs):
        for i in range(7):
            a = i / 7 * math.tau + r.random() * .5; dd = 42 + r.random() * 40
            x = max(40, min(800, hx + math.cos(a) * dd * 1.15)); y = max(74, min(462, hy + math.sin(a) * dd * .85))
            delay = round(.5 + r.random() * 1.3, 2)
            edges.append(line(hx, hy, x, y, K['bSub'] if dim else K['bStr'], 1, round(delay + .5, 2), dash=None if r.random() < .7 else '4 3'))
            nodes.append(node(r.choice(mix), x, y, 5, delay, dim=dim))
    for i, j in ((0, 4), (3, 4)): edges.append(line(hubs[i][0], hubs[i][1], hubs[j][0], hubs[j][1], K['bSub'], 1, 1.9, dash='4 3'))
    path = [line(hubs[i][0], hubs[i][1], hubs[i + 1][0], hubs[i + 1][1], K['t1'], 2.5, round(3.2 + i * .5, 2), draw=True) for i in range(3)]
    hub = [node(t, x, y, 9, round(.3 + i * .1, 2), dim=dim) for i, (x, y, t, l, dim) in enumerate(hubs)]
    lab = []
    for i, (x, y, t, l, dim) in enumerate(hubs):
        w = tw(l, 12, i == 2) + 8
        lab.append(f'<g class="a-fade" {st(2.3)}>' + rect(x + 12, y - 24, round(w), 17, K['app'], rx=2) + text(x + 16, y - 11, l, 12, K['t3'] if dim else K['t1'], 600, mono=(i == 2)) + '</g>')
    ring = f'<circle cx="{hubs[1][0]}" cy="{hubs[1][1]}" r="16" class="a-pop" {st(4.7, fill="none", stroke=K["brass"], stroke_width=2)}></circle>'
    o += edges + path + nodes + hub + lab + [ring]
    o.append(panel(840, 20, 340, 460, 'Ranked by betweenness', .3))
    rows = [('Hale Logistics Ltd', .42), ('60-16-13 ••19', .31), ('HALE, Marcus', .18), ('CARTER, Jamal', .07)]
    for i, (n, v) in enumerate(rows):
        y = 92 + i * 86; d = round(2.6 + i * .25, 2)
        o.append(text(860, y, n, 15, K['t1'], 600, d=d, mono=(i == 1))); o.append(text(1160, y, f'{v:.2f}', 14, K['t2'], anchor='end', mono=True, d=d))
        o.append(rect(860, y + 14, 300, 8, K['raised'], rx=4, d=d)); o.append(rect(860, y + 14, round(300 * v / .42), 8, K['brass'] if i == 0 else K['seq'], rx=4, d=round(d + .2, 2), cls='a-growx'))
    o.append(text(860, 446, 'A path traced: Hale to Carter in three steps', 13, K['t3'], d=4.9))
    return ('Explore the network', 'Expand from one person, find the communities, and trace the path between two people.',
            svg('A network of people, companies and accounts, with a path traced across it and a ranking beside it', ''.join(o)))

def a1():
    o = [panel(20, 20, 820, 460, 'The Glass · Drawing board · Board 3 · Operation Ledger (synthetic)')]
    L = [(250, 210, 'person', 'HALE, Marcus'), (450, 140, 'account', '60-16-13 ••19'), (400, 330, 'phone', '+44 7700 900304')]
    for (x1, y1, *_), (x2, y2, *_) in ((L[0], L[1]), (L[0], L[2])): o.append(line(x1, y1, x2, y2, K['bStr'], 1.5, .7))
    for i, (x, y, t, l) in enumerate(L):
        o.append(node(t, x, y, 11, round(.4 + i * .15, 2))); o.append(text(x + 18, y + 5, l, 13, K['t1'], 600, d=.9, mono=(i > 0)))
    o.append(line(680, 250, 400, 330, K['warn'], 2, 2.6, dash='6 5')); o.append(text(470, 262, 'MET_WITH · drawn', 12, K['warn'], 600, d=2.9, mono=True))
    o.append(node('person', 680, 250, 12, 1.8, drawn=True)); o.append(text(700, 255, "Unknown male, 'Kez'", 13, K['warn'], 600, d=2.0))
    o.append(line(680, 250, 620, 400, K['warn'], 2, 3.3, dash='6 5')); o.append(node('address', 620, 400, 12, 3.1, drawn=True)); o.append(text(640, 405, 'Lock-up, Dock Road', 13, K['warn'], 600, d=3.3))
    o.append(text(40, 462, 'Solid: loaded from a source.   Dashed amber: drawn by an analyst.', 13, K['t3'], d=1.2))
    o.append(panel(860, 20, 320, 300, 'Drawn item', 3.6))
    for i, (k, v) in enumerate((('Drawn by', 'R. Okafor'), ('Grading, 5x5x5', 'B · 2 · 1'), ('Source note', 'IR-2291'), ('Marking', 'OFFICIAL'), ('Kept in', "this case's analyst layer"))):
        y = 92 + i * 46; d = round(3.9 + i * .18, 2)
        o.append(text(880, y, k, 12, K['t3'], d=d)); o.append(text(880, y + 20, v, 15, K['t1'], 600, d=d, mono=(i in (1, 2))))
    c, w = chip(860, 350, 'Promote into the dataset', 5.2, K['brass'], K['brass'], K['brassInk'], 14, h=34); o.append(c)
    o.append(text(860, 412, 'Promotion is a load of its own, reviewed', 13, K['t2'], d=5.5)); o.append(text(860, 432, "by a second person where the dataset asks.", 13, K['t2'], d=5.5))
    return ('Draw what you know', 'A drawing board holds what an analyst knows that the data does not yet say: attributed, marked, graded and sourced.',
            svg('A drawing board with loaded items in solid colour and drawn items in dashed amber', ''.join(o)))

def a2():
    o = [panel(20, 20, 1160, 460, 'Rules and Monitoring · Alerts · one queue')]
    for x, h in ((44, 'Severity'), (160, 'Why it was raised'), (760, 'Who may see it'), (920, 'Age')): o.append(text(x, 82, h, 12, K['t3'], 600, d=.4))
    o.append(line(36, 94, 1164, 94, K['bSub'], d=.4))
    rows = [('High', K['err'], 'Account 60-16-13 ••19 received 3 payments under £10,000 in 7 days', 'The case team', '2 hours old'),
            ('High', K['err'], 'Hotlist: +44 7700 900304 seen in new call records', 'Shared with team', '5 hours old'),
            ('Medium', K['warn'], 'A customer matches an entry that changed on a screening list', 'The case team', '1 day old'),
            ('Low', K['ok'], 'A dormant account was used again', 'The case team', '3 days old')]
    for i, (sev, col, why, who, age) in enumerate(rows):
        y = 104 + i * 56; d = round(.8 + i * .35, 2)
        g = [rect(36, y, 1128, 46, K['raised'], K['bSub'], rx=6)]
        c, w = chip(46, y + 10, sev, None, K['app'], col, col, 12, h=26); g.append(c)
        g += [text(160, y + 28, why, 15, K['t1']), text(760, y + 28, who, 14, K['t2']), text(920, y + 28, age, 14, K['t2'])]
        o.append(f'<g class="a-rise" {st(d)}>' + ''.join(g) + '</g>')
    o.append(rect(36, 104, 1128, 46, 'none', K['brass'], rx=6, sw=2, d=3.0, cls='a-fade'))
    c, w = chip(1070, 114, 'Claimed', 3.2, K['brass'], K['brass'], K['brassInk'], 12, h=26); o.append(c)
    o.append(f'<g class="a-rise" {st(4.1)}>' + rect(560, 340, 604, 124, K['raised'], K['b'], rx=8) + text(580, 370, 'Close this alert', 13, K['t3'], 600)
             + text(580, 398, 'True match', 19, K['t1'], 700) + text(580, 424, 'Reason: three structured deposits, confirmed against statements.', 14, K['t2'])
             + text(580, 448, 'Propose the close: a second person approves a high-severity one.', 13, K['warn'], 600) + '</g>')
    o.append(text(44, 372, 'A person decides every alert.', 15, K['t2'], d=4.4)); o.append(text(44, 396, 'Nothing you may not see is shown or counted.', 15, K['t2'], d=4.7))
    return ('Work the alerts', 'One queue for every alert you may see. A person decides each one, with a reason, and a second person approves closing a high-severity one that others may see.',
            svg('An alert queue with four alerts, one claimed and being closed with a reason', ''.join(o)))

def a3():
    o = [panel(20, 20, 1160, 460, 'Dashboards · Alert monitoring (synthetic figures)')]
    for i, (k, v) in enumerate((('Alerts raised this week', '42'), ('Closed with an outcome', '31'), ('Hotlist matches', '4'))):
        x = 44 + i * 376; d = round(.5 + i * .2, 2)
        o.append(f'<g class="a-rise" {st(d)}>' + rect(x, 70, 360, 96, K['raised'], K['bSub'], rx=8) + text(x + 18, 100, k, 13, K['t3'], 600) + text(x + 18, 146, v, 38, K['t1'], 700, mono=True) + '</g>')
    o.append(text(44, 204, 'Alerts by rule', 14, K['t2'], 600, d=1.3)); o.append(line(44, 440, 560, 440, K['b'], d=1.3))
    for i, hgt in enumerate((150, 110, 190, 70, 130, 50)):
        x = 64 + i * 82
        o.append(rect(x, 440 - hgt, 54, hgt, K['brass'] if i == 2 else K['seq'], rx=3, d=round(1.6 + i * .15, 2), cls='a-growy'))
    o.append(text(620, 204, 'Alerts closed each week', 14, K['t2'], 600, d=1.3)); o.append(line(620, 440, 1156, 440, K['b'], d=1.3))
    pts = [(620, 400), (700, 372), (780, 384), (860, 330), (940, 300), (1020, 318), (1100, 262), (1156, 240)]
    dpath = 'M' + ' L'.join(f'{x} {y}' for x, y in pts)
    o.append(f'<path d="{dpath}" pathLength="1" class="a-draw" {st(2.8, fill="none", stroke=K["azure"], stroke_width=3, stroke_linecap="round", animation_duration="1.8s")}></path>')
    for i, (x, y) in enumerate(pts[1:-1]): o.append(f'<circle cx="{x}" cy="{y}" r="4" class="a-pop" {st(round(3.2 + i * .2, 2), fill=K["azure"])}></circle>')
    return ('Brief the people you report to', 'Trends and report packs for analysts, and dashboards for the people who read the figures, drawn from the same data the analysts work with.',
            svg('A dashboard with three figures, a bar chart of alerts by rule and a rising weekly trend line', ''.join(o)))

# ---------------------------------------------------------------- developer
def d0():
    o = [panel(20, 20, 1160, 460, 'Ingest Studio · 1 Model · crime · draft')]
    B = {'person': (130, 200, 'Person'), 'phone': (490, 90, 'Phone'), 'account': (850, 200, 'Account'), 'address': (270, 370, 'Address'), 'company': (710, 370, 'Company')}
    links = [('person', 'phone', 'USES'), ('person', 'account', 'HOLDS'), ('person', 'address', 'LIVES_AT'), ('person', 'company', 'DIRECTOR_OF'), ('company', 'address', 'REGISTERED_AT'), ('company', 'account', 'HOLDS')]
    cen = lambda k: (B[k][0] + 110, B[k][1] + 35)
    for i, (a, b, l) in enumerate(links):
        (x1, y1), (x2, y2) = cen(a), cen(b); d = round(1.6 + i * .35, 2)
        o.append(line(x1, y1, x2, y2, K['bStr'], 1.5, d, draw=True))
    for i, (a, b, l) in enumerate(links):
        (x1, y1), (x2, y2) = cen(a), cen(b); d = round(1.9 + i * .35, 2); mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        w = tw(l, 11, True) + 12
        o.append(f'<g class="a-fade" {st(d)}>' + rect(round(mx - w / 2), round(my - 10), round(w), 20, K['panel'], K['bSub'], rx=4) + text(mx, my + 4, l, 11, K['t2'], 600, 'middle', mono=True) + '</g>')
    for i, (k, (x, y, n)) in enumerate(B.items()):
        d = round(.4 + i * .2, 2); ch, sh = TYPES[k]
        o.append(f'<g class="a-rise" {st(d)}>' + rect(x, y, 220, 70, K['raised'], K['b'], rx=8) + shape(sh, x + 36, y + 35, 12, K[ch], K['raised'], 1.5)
                 + text(x + 64, y + 32, n, 18, K['t1'], 700) + text(x + 64, y + 52, 'entity type', 12, K['t3']) + '</g>')
    c, w = chip(900, 70, 'Model v14 · live', 4.6, K['brass'], K['brass'], K['brassInk'], 13, h=30); o.append(c)
    c, w = chip(900 + w + 10, 70, 'v15 · draft', 4.8, K['app'], K['b'], K['t1'], 13, h=30); o.append(c)
    o.append(text(44, 462, 'Each type is drawn with a colour and a shape, so hue never carries meaning alone.', 13, K['t3'], d=4.2))
    return ('Model the data', 'A domain model for each dataset: its entity types and the links between them, kept as numbered versions, one live and one draft.',
            svg('Five entity types joined by named link types in a domain model', ''.join(o)))

def d1():
    o = [panel(20, 20, 1160, 460, 'Ingest Studio · 3 Pipelines · Carrier call records')]
    cx = 44
    for i, s in enumerate(('1 Model', '2 Sources', '3 Pipelines', '4 Runs')):
        on = i == 2; c, w = chip(cx, 70, s, round(.3 + i * .1, 2), K['brass'] if on else K['raised'], K['brass'] if on else K['b'], K['brassInk'] if on else K['t2'], 13, h=30); o.append(c); cx += w + 10
    cards = [('Source', [('calls_2026-10.csv', True, K['t1']), ('OFFICIAL', False, K['t2']), ('legal basis recorded', False, K['t2'])]),
             ('Map', [('caller  →  Phone', True, K['t1']), ('callee  →  Phone', True, K['t1']), ('started_at  →  CALLED', True, K['t1'])]),
             ('Verify', [('Would create', False, K['t3']), ('20 numbers · 141 links', False, K['t1']), ('2 rows rejected', False, K['warn'])]),
             ('Run', [('Loaded 09:30', False, K['t1']), ('recorded in Runs', False, K['t2']), ('can be reverted', False, K['ok'])])]
    for i, (h, ls) in enumerate(cards):
        x = 44 + i * 284; d = round(1.0 + i * 1.0, 2)
        g = [rect(x, 150, 254, 190, K['raised'], K['b'], rx=8), text(x + 18, 184, h, 13, K['brass'], 700)]
        for j, (t, mono, col) in enumerate(ls): g.append(text(x + 18, 226 + j * 34, t, 14 if mono else 15, col, 600 if j == 1 or mono else 400, mono=mono))
        o.append(f'<g class="a-rise" {st(d)}>' + ''.join(g) + '</g>')
        if i < 3:
            ax = x + 254; o.append(line(ax + 4, 245, ax + 26, 245, K['t2'], 2, round(d + .6, 2), draw=True))
            o.append(f'<path d="M{ax+20} 239 L{ax+27} 245 L{ax+20} 251" class="a-fade" {st(round(d + .9, 2), fill="none", stroke=K["t2"], stroke_width=2, stroke_linecap="round")}></path>')
    o.append(text(44, 392, 'Loaded data reaches a dataset only through a pipeline someone published.', 15, K['t2'], d=4.8))
    o.append(text(44, 418, 'Verify shows what a file would create, and what it would reject, before anything loads.', 15, K['t2'], d=5.1))
    return ('Build a pipeline in the Ingest Studio', 'A source, its mapping and its runs. Verify shows the result before anything loads, and a load can be taken back.',
            svg('A pipeline in four cards: source, map, verify and run', ''.join(o)))

def d2():
    o = [panel(20, 20, 1160, 460, 'Rules and Monitoring · What raises alerts · rule editor')]
    def sentence(y, parts, d0):
        x = 60; out = []; d = d0
        for s, blank in parts:
            if blank:
                c, w = chip(x, y - 26, s, round(d, 2), K['raised'], K['brass'], K['t1'], 20, h=40, weight=600); out.append(c); x += w + 12; d += .55
            else:
                out.append(text(x, y, s, 22, K['t2'], d=round(max(.3, d - .3), 2))); x += tw(s, 22) + 12
        return ''.join(out), d
    s1, d = sentence(120, [('When a', 0), ('Phone', 1), ('is', 0), ('on one of my hotlists', 1)], .8)
    s2, d = sentence(180, [('3 times within 7 days', 1), (', raise a', 0), ('High', 1), ('alert.', 0)], d)
    o += [s1, s2]
    o.append(f'<g class="a-rise" {st(4.2)}>' + rect(44, 230, 700, 226, K['raised'], K['bSub'], rx=8) + text(64, 262, 'Preview on the last 90 days', 13, K['t3'], 600) + line(64, 410, 724, 410, K['b']) + '</g>')
    for i in range(13):
        hit = i in (2, 6, 7, 11); x = 70 + i * 50
        o.append(rect(x, 410 - (90 if hit else 6), 32, 90 if hit else 6, K['brass'] if hit else K['b'], rx=2, d=round(4.5 + i * .06, 2), cls='a-growy'))
    o.append(text(64, 440, 'It would have raised 4 alerts. A preview raises nothing and writes nothing.', 14, K['t2'], d=5.2))
    c, w = chip(790, 250, 'Test', 5.0, K['raised'], K['b'], K['t1'], 15, h=38); o.append(c)
    c, w = chip(870, 250, 'Make live', 5.4, K['brass'], K['brass'], K['brassInk'], 15, h=38); o.append(c)
    for i, t in enumerate(('Every blank is a choice from your own', 'types and links. No formula to write.', '', 'Make live waits for a second Author', 'where the dataset asks.')):
        if t: o.append(text(790, 330 + i * 24, t, 14, K['t2'] if i < 2 else K['warn'], 600 if i > 2 else 400, d=5.6))
    return ('Write a rule as a sentence', 'Rules are built from your own types and links, previewed on the last 90 days, tested on the last 30, and only then made live.',
            svg('A rule written as a sentence with filled blanks, and a preview chart of the alerts it would have raised', ''.join(o)))

# ---------------------------------------------------------------- administrator
def m0():
    o = []
    tiers = [(30, 'The Glass', "The analyst's workspace", ['React · TypeScript', 'Sigma.js', 'MapLibre GL', 'Apache ECharts', 'GOV.UK Frontend'], K['indigo']),
             (180, 'The Conduit', 'Stateless API and access control', ['Python · FastAPI', 'Access control', 'Entity resolution', 'Extraction'], K['brass']),
             (368, 'The Vault', 'Stores and engines', ['ArcadeDB', 'DuckDB or ClickHouse', 'OpenSearch, PostgreSQL', 'Valkey', 'Object storage', 'LiteLLM'], K['jade'])]
    for i, (y, n, role, cs, col) in enumerate(tiers):
        d = round(.4 + i * .9, 2)
        g = [rect(40, y, 1120, 104, K['panel'], K['bSub'], rx=10), rect(40, y, 8, 104, col, rx=4), text(72, y + 44, n, 26, K['t1'], 700), text(72, y + 72, role, 14, K['t3'])]
        o.append(f'<g class="a-rise" {st(d)}>' + ''.join(g) + chips(400, y + 39, cs, None, size=13, h=28) + '</g>')
    for x in (300, 600, 900): o.append(line(x, 134, x, 180, K['bStr'], 2, 1.2, draw=True))
    for i, p in enumerate(('GraphPort', 'AnalyticsPort', 'ComputePort', 'ModelPort')):
        x = 150 + i * 260; d = round(2.9 + i * .25, 2)
        o.append(line(x + 70, 284, x + 70, 368, K['brass'], 2, d, draw=True))
        c, w = chip(x, 312, p, round(d + .2, 2), K['app'], K['brass'], K['brass'], 14, h=30); o.append(c)
    o.append(text(600, 490, 'An engine behind a port can be swapped without touching what sits above it.', 14, K['t2'], anchor='middle', d=4.6))
    return ('Three tiers, four ports', 'The Glass, the Conduit and the Vault, separated by four typed ports, all inside your own cloud or data centre.',
            svg('Three stacked tiers, the Glass, the Conduit and the Vault, with four ports between the Conduit and the Vault', ''.join(o)))

def m1():
    o = [panel(20, 20, 640, 460, 'Admin · People and roles')]
    for x, h in ((44, 'Person'), (220, 'Roles'), (470, 'Clearance')): o.append(text(x, 82, h, 12, K['t3'], 600, d=.4))
    o.append(line(36, 94, 644, 94, K['bSub'], d=.4))
    people = [('R. Okafor', ['Analyst'], 'OFFICIAL-SENSITIVE'), ('S. Lindqvist', ['Data Engineer', 'Rule author'], 'OFFICIAL'), ('T. Marsh', ['Reports Viewer'], 'OFFICIAL')]
    for i, (n, roles, cl) in enumerate(people):
        y = 106 + i * 62; d = round(.8 + i * .35, 2)
        o.append(f'<g class="a-rise" {st(d)}>' + rect(36, y, 608, 50, K['raised'], K['bSub'], rx=6) + text(52, y + 31, n, 15, K['t1'], 600)
                 + chips(220, y + 12, roles, None, size=12, h=26) + text(470, y + 31, cl, 13, K['warn'] if 'SENS' in cl else K['t2'], 600, mono=True) + '</g>')
    o.append(text(44, 330, 'Roles you can define. Nobody can give more than they hold, clearance included.', 14, K['t2'], d=2.2))
    o.append(text(44, 356, 'On a server of your own: sign-in through Entra ID, ADFS or OpenID Connect.', 14, K['t2'], d=2.5))
    o.append(text(44, 382, 'Disabling a person first asks who takes each thing they answer for.', 14, K['t2'], d=2.8))
    def mini(x, title, show, count, d):
        g = [panel(x, 20, 240, 460, title, d)]
        P = [(x + 70, 140, 'person', 0), (x + 170, 120, 'account', 0), (x + 120, 220, 'company', 0), (x + 60, 300, 'phone', 0), (x + 180, 290, 'person', 1), (x + 130, 370, 'doc', 1)]
        E = [(0, 2), (1, 2), (2, 3), (2, 4), (4, 5), (3, 5)]
        for a, b in E:
            if show or not (P[a][3] or P[b][3]): g.append(line(P[a][0], P[a][1], P[b][0], P[b][1], K['bStr'], 1.5, round(d + .5, 2)))
        for (px, py, t, sens) in P:
            if show or not sens: g.append(node(t, px, py, 10, round(d + .3, 2)))
            if show and sens: g.append(f'<circle cx="{px}" cy="{py}" r="17" class="a-fade" {st(round(d + .8, 2), fill="none", stroke=K["warn"], stroke_width=1.5, stroke_dasharray="3 3")}></circle>')
        g.append(text(x + 120, 440, count, 15, K['t1'], 700, 'middle', d=round(d + 1.0, 2)))
        return ''.join(g)
    o.append(mini(680, 'Cleared higher', True, '6 items', 3.2)); o.append(mini(940, 'Cleared lower', False, '4 items, and the count says 4', 4.2))
    return ('Decide who sees what', 'Roles, teams, markings and clearance. Access is enforced in the store, so a record someone may not see leaves no trace in a count or a path.',
            svg('A table of people with their roles and clearance, and the same network seen by two people with different clearance', ''.join(o)))

DATASETS_SUB = ("Every load is recorded with the pipeline version that made it, and can be reverted. The dataset's model is "
                "versioned: one live, one draft, and every earlier version can be restored.")


def m2():
    """The orchestrator's answer of 13 November 2026: a dataset has no version of its own. Its domain model has one live
    version, one draft and every earlier one restorable; each pipeline has a version; every load is recorded with the
    pipeline version that made it, and can be reverted. The sub line is the owner's, as accepted that day."""
    o = [panel(20, 20, 1160, 460, 'Admin · Datasets · Carrier call records (synthetic)')]
    o.append(line(90, 200, 1110, 200, K['b'], 3, .5, draw=True))
    ev = [(150, 'Load 12', 'pipeline v3', '20 numbers · 141 links', K['seq'], None),
          (420, 'Load 13', 'pipeline v3', 'reverted, and kept on record', K['err'], 'Reverted'),
          (700, 'Load 14', 'promotion', '6 drawn items, as a load', K['warn'], 'Reviewed where the dataset asks'),
          (980, 'Load 15', 'pipeline v3', 'a scheduled run', K['seq'], None)]
    for i, (x, n, made, sub, col, tag) in enumerate(ev):
        d = round(1.0 + i * .8, 2)
        o.append(f'<circle cx="{x}" cy="200" r="11" class="a-pop" {st(d, fill=col, stroke=K["panel"], stroke_width=3)}></circle>')
        o.append(text(x, 140, n, 18, K['t1'], 700, 'middle', d=d))
        if tag == 'Reverted':
            o.append(line(x - 40, 134, x + 40, 134, K['err'], 2, round(d + .6, 2), draw=True))
        c, _ = chip(round(x - (tw(made, 12, True) + 20) / 2), 152, made, round(d + .1, 2), K['raised'], K['b'], K['t2'], 12, mono=True, h=24); o.append(c)
        o.append(text(x, 240, sub, 13, K['t2'], anchor='middle', d=round(d + .2, 2)))
        if tag:
            w = tw(tag, 12) + 20; c, _ = chip(round(x - w / 2), 258, tag, round(d + .5, 2), K['app'], col, col, 12, h=26); o.append(c)
    o.append(f'<g class="a-rise" {st(4.4)}>' + rect(44, 320, 330, 104, K['raised'], K['b'], rx=8)
             + text(64, 350, 'Domain model', 13, K['t3'], 600) + text(64, 382, 'Model v14 · live', 18, K['t1'], 700, mono=True)
             + text(64, 408, 'v15 · draft', 15, K['t2'], 600, mono=True) + '</g>')
    o.append(chips(400, 336, ['Highest marking it may hold: OFFICIAL-SENSITIVE', 'Egress: none'], 4.8, .2, size=13, h=30))
    o.append(text(400, 400, 'Earlier versions of the model can be restored, as a new draft.', 14, K['t2'], d=5.3))
    o.append(text(44, 456, 'An update backs everything up first, and rolls back if it fails.', 14, K['t2'], d=5.8))
    return ('Datasets you can stand behind', DATASETS_SUB,
            svg('A timeline of loads into a dataset, each with the pipeline version that made it, one reverted, and the '
                'domain model with its live version and its draft', ''.join(o)))


def m3():
    o = [panel(20, 20, 1160, 460, 'Admin · Operations and Audit · Audit')]
    o.append(chips(44, 68, ['Cases, people, datasets and loads', 'Loads and promotions', 'People and roles', 'Datasets'], .4, .12, size=12, h=26))
    for x, h in ((44, 'When'), (150, 'Who'), (330, 'What')): o.append(text(x, 128, h, 12, K['t3'], 600, d=.6))
    o.append(line(36, 138, 1164, 138, K['bSub'], d=.6))
    rows = [('09:30', 'S. Lindqvist', 'Ran the pipeline Carrier call records: load 15'),
            ('09:42', 'R. Okafor', 'Promoted 6 drawn items into the dataset: load 14'),
            ('10:05', 'Administrator', "Changed a dataset's egress from none to contracted"),
            ('10:20', 'T. Marsh', 'Refused: a read above their clearance'),
            ('10:31', 'Administrator', 'Disabled an account and transferred 3 items')]
    for i, (t, who, what) in enumerate(rows):
        y = 150 + i * 52; d = round(1.0 + i * .5, 2)
        o.append(f'<g class="a-rise" {st(d)}>' + rect(36, y, 1128, 42, K['raised'], K['bSub'], rx=6) + text(52, y + 27, t, 14, K['t2'], mono=True) + text(150, y + 27, who, 14, K['t1'], 600) + text(330, y + 27, what, 15, K['t1']) + '</g>')
    o.append(text(44, 446, "Where your own read of a record would not show its words, the entry says so. The log is append-only.", 14, K['t2'], d=4.2))
    return ('Everything is on the record', 'Who did what and when: loads and promotions, people and roles, datasets, and every read that was refused.',
            svg('An audit log with five entries, each with a time, a person and an action', ''.join(o)))


SEATS = [('Analyst', 'a', [a0, a1, a2, a3], ['Network', 'Drawing board', 'Alerts', 'Dashboards']),
         ('Developer', 'd', [d0, d1, d2], ['Data model', 'Ingest Studio', 'Rule editor']),
         ('Administrator', 'm', [m0, m1, m2, m3], ['Architecture', 'Access', 'Datasets', 'Audit'])]
