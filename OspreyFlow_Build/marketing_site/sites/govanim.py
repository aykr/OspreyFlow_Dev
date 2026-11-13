"""The GOV.UK theme in four steps, on ospreyflow.org's UK public sector page alone (the owner, 13 November 2026). It is
the website's own drawing, not a screen from the product: this site is not a gov.uk service, so the drawing has no
crown, no GOV.UK logotype and no GDS Transport (set in Arial), and the line under it says so (ADR-132's rule for a
service off gov.uk, Amendment 8). Each step is checked against main and the guides in
`process/lanes/docs/sites2-facts.md`."""
import math, random, html
from overview import text, rect, line, shape, chip, chips, st, esc, tw, DUR

#: Tokens of `.gv` in `source/site.css`: the drawing stays light in the dark theme, as the GOV.UK look has no dark mode.
G = {k: f'var(--g-{k})' for k in ('blue', 'ink', 'sec', 'border', 'light', 'yellow', 'green', 'white', 'tagbg', 'tagink', 'term', 'termink', 'termdim')}
CH = dict(person='#5367cb', company='#3682b2', account='#2f8364', address='#a8430f', phone='#a8324e', doc='#6a3a9a')
SH = dict(person='circle', company='square', account='rounded', address='ring', phone='triangle', doc='diamond')
DK = dict(app='#101314', panel='#161a1b', raised='#202425', b='#4d5051', t1='#e8eced', t2='#c1c5c6', brass='#c08a34',
          person='#8496e6', company='#61b1e6', account='#72b99a', address='#d2693a', phone='#d0707f', doc='#a78bc7', edge='#66696a')

def svg(label, inner):
    return f'<svg viewBox="0 0 1200 500" role="img" aria-label="{html.escape(label)}" style="display: block; width: 100%; height: auto">{inner}</svg>'

def grp(inner, d=None, cls='a-fade'):
    return (f'<g class="{cls}" {st(d)}>' if d is not None else '<g>') + inner + '</g>'

def mini_graph(x, y, w, h, pal, edge, hi, seed=5, ring=None):
    r = random.Random(seed); o = []
    hubs = [(x + w * .22, y + h * .38, 'person'), (x + w * .5, y + h * .24, 'company'), (x + w * .78, y + h * .42, 'account'), (x + w * .6, y + h * .78, 'person')]
    for hx, hy, ht in hubs:
        for i in range(5):
            a = i / 5 * math.tau + r.random(); dd = (22 + r.random() * 22) * w / 520
            px, py = hx + math.cos(a) * dd * 1.2, hy + math.sin(a) * dd * .9
            t = r.choice(list(SH)); o.append(line(hx, hy, px, py, edge, 1)); o.append(shape(SH[t], px, py, 4.5 * w / 520 + 1.5, pal[t], pal.get('bg', '#fff'), 1))
    for i in range(3): o.append(line(hubs[i][0], hubs[i][1], hubs[i + 1][0], hubs[i + 1][1], hi, 2.5))
    for hx, hy, ht in hubs: o.append(shape(SH[ht], hx, hy, 8 * w / 520 + 2, pal[ht], pal.get('bg', '#fff'), 1.5))
    if ring: o.append(f'<circle cx="{hubs[1][0]:.1f}" cy="{hubs[1][1]:.1f}" r="{14 * w / 520 + 4:.1f}" {st(None, fill="none", stroke=ring, stroke_width=3)}></circle>')
    return ''.join(o), hubs

def gov_frame(x, y, w, h, service='Analyse crime intelligence', places=True, banner=True):
    o = [rect(x, y, w, h, G['white'], G['border'], rx=0), rect(x, y, w, 46, G['blue'], rx=0), text(x + 20, y + 30, service, 17, G['white'], 700)]
    if places:
        px = x + w - 20
        for i, p in enumerate(reversed(('The Glass', 'Ingest Studio', 'Rules and Monitoring', 'Admin'))):
            tx = tw(p, 13); px -= tx; first = (i == 3)
            o.append(text(px, y + 29, p, 13, G['white'], 700 if first else 400))
            if first: o.append(rect(px, y + 40, round(tx), 4, G['white'], rx=0))
            px -= 22
    top = y + 46
    if banner:
        o += [rect(x + 20, top + 9, 46, 20, G['tagbg'], rx=0), text(x + 43, top + 24, 'Beta', 12, G['tagink'], 700, 'middle'), text(x + 78, top + 24, 'This is a new service.', 13, G['ink']),
              line(x + 20, top + 38, x + w - 20, top + 38, G['border'])]
        top += 38
    return ''.join(o), top

def osprey_frame(x, y, w, h):
    o = [rect(x, y, w, h, DK['app'], DK['b'], rx=8), rect(x, y, w, 46, DK['panel'], DK['b'], rx=8), rect(x + 1, y + 30, w - 2, 16, DK['panel'], rx=0),
         f'<path d="M{x+18} {y+14}L{x+34} {y+18}L{x+48} {y+28}L{x+34} {y+31}L{x+22} {y+38}Z" {st(None, fill=DK["brass"])}></path>', text(x + 58, y + 30, 'Osprey', 17, DK['t1'], 700)]
    px = x + w - 20
    for i, p in enumerate(reversed(('The Glass', 'Ingest Studio', 'Rules and Monitoring', 'Admin'))):
        px -= tw(p, 13); o.append(text(px, y + 29, p, 13, DK['t1'] if i == 3 else DK['t2'], 700 if i == 3 else 400)); px -= 22
    return ''.join(o), y + 46

def g0():
    o = [grp(rect(40, 30, 500, 300, G['term'], rx=6) + rect(40, 30, 500, 30, '#2b2f30', rx=6) + text(58, 50, 'Terminal', 12, G['termdim'], 600), .2)]
    for i, l in enumerate(('$ ospreyflow install --mode lite \\', '\u00a0\u00a0\u00a0\u00a0--starter govuk-crime \\', '\u00a0\u00a0\u00a0\u00a0--service-name "Analyse crime intelligence" \\', '\u00a0\u00a0\u00a0\u00a0--organisation "Your organisation"')):
        o.append(text(60, 100 + i * 34, l, 15, G['termink'], mono=True, d=round(.6 + i * .5, 2)))
    o.append(text(60, 270, 'One setting gives every page the GOV.UK look.', 13, G['termdim'], d=2.8))
    o.append(grp(rect(40, 350, 500, 120, G['light'], G['border'], rx=0) + text(60, 380, 'osprey.yaml', 12, G['sec'], 700) + text(60, 412, 'appearance:', 16, G['ink'], mono=True)
                 + text(60, 440, '\u00a0\u00a0brand: govuk', 16, G['ink'], 700, mono=True), 3.0, 'a-rise'))
    of, top = osprey_frame(590, 30, 570, 440); og, _ = mini_graph(610, top + 10, 530, 360, dict(DK, bg=DK['app']), DK['edge'], DK['t1'], ring=DK['brass'])
    o.append(grp(of + og, .3))
    gf, gtop = gov_frame(590, 30, 570, 440, places=False); gg, _ = mini_graph(610, gtop + 6, 530, 330, CH, G['border'], G['ink'], ring=G['blue'])
    o.append(grp(gf + gg, 4.0))
    return ('One setting, chosen at install', 'The GOV.UK theme is a deployment setting, not a separate edition or a fork. Everything underneath is the same product.',
            svg('A terminal installing with a GOV.UK starter, and the same screen changing from the OspreyFlow look to the GOV.UK look', ''.join(o)))

def callout(x, y, label, tx, ty, d):
    w = tw(label, 14) + 24
    return grp(line(x + w / 2, y + 15, tx, ty, G['ink'], 2) + f'<circle cx="{tx}" cy="{ty}" r="5" {st(None, fill=G["ink"])}></circle>'
               + rect(x, y, round(w), 30, G['yellow'], G['ink'], rx=0, sw=2) + text(x + 12, y + 20, label, 14, G['ink'], 700), d, 'a-pop')

def g1():
    gf, top = gov_frame(60, 20, 1080, 460)
    o = [grp(gf + text(80, 262, 'Cases', 28, G['ink'], 700)
             + ''.join(line(80, 286 + i * 44, 760, 286 + i * 44, G['border']) + text(80, 314 + i * 44, n, 16, G['blue'], 400) + text(560, 314 + i * 44, m, 14, G['sec'])
                       for i, (n, m) in enumerate((('Operation Ledger (synthetic demo)', '47 entities · 50 links'), ('HMP fixture (synthetic demo)', '212 entities · 603 links'))))
             + rect(61, 424, 1078, 55, G['light'], rx=0) + line(60, 424, 1140, 424, G['border']) + text(80, 457, 'Your organisation', 14, G['ink'], 700)
             + text(1120, 457, 'Built with OspreyFlow, open source.', 13, G['sec'], anchor='end'), .2)]
    o.append(callout(90, 130, "Your service's name, not ours", 150, 58, 1.4))
    o.append(callout(420, 180, 'The phase banner', 230, 92, 2.4))
    o.append(callout(790, 130, 'The four places, in the header', 900, 58, 3.4))
    o.append(callout(330, 380, 'Your organisation, in the footer', 200, 448, 4.4))
    return ("Your service's name, not ours", "The install asks for the service's name, the organisation and the phase. The switch between the four places sits inside the header.",
            svg('A page in the GOV.UK look with its service name, phase banner, place navigation and footer pointed out', ''.join(o)))

def g2():
    gf, top = gov_frame(40, 20, 1120, 460)
    gg, hubs = mini_graph(60, top + 8, 700, 360, CH, G['border'], G['ink'], seed=9, ring=G['blue'])
    o = [grp(gf, .2), grp(gg, .9), line(780, top + 8, 780, 470, G['border'], d=.9)]
    o.append(text(804, 150, 'A possible match', 22, G['ink'], 700, d=1.8))
    o.append(grp(rect(804, 164, 70, 22, G['tagbg'], rx=0) + text(839, 180, 'Inferred', 12, G['tagink'], 700, 'middle'), 2.2, 'a-pop'))
    for i, (k, v) in enumerate((('This', 'Hale Logistics Ltd'), ('Same as', 'Hale Logistics Limited'), ('Came from', 'Companies register, row 212'))):
        yy = 222 + i * 44; o.append(grp(line(804, yy + 14, 1140, yy + 14, G['border']) + text(804, yy, k, 14, G['ink'], 700) + text(900, yy, v, 14, G['ink']), round(2.6 + i * .3, 2), 'a-rise'))
    o.append(grp(rect(804, 372, 200, 40, '#002d18', rx=0) + rect(804, 370, 200, 40, G['green'], rx=0) + text(904, 396, 'Confirm as the same', 16, G['white'], 700, 'middle'), 3.8, 'a-pop'))
    o.append(text(804, 446, 'A model suggests; a person confirms.', 13, G['sec'], d=4.4))
    o.append(grp(rect(60, 430, 470, 30, G['white'], rx=0) + text(64, 450, "The network's colours and shapes are the same under either look.", 14, G['ink'], 700), 5.0, 'a-rise'))
    return ('The same product underneath', 'The network, the map, the timeline, reports, the Ingest Studio and monitoring, all with the same features and the same tests.',
            svg('The network view in the GOV.UK look, with a possible match beside it, inferred until a person confirms it', ''.join(o)))

def g3():
    gf, top = gov_frame(40, 20, 1120, 460)
    o = [grp(gf + text(60, top + 44, 'Matrix: the network as tables', 24, G['ink'], 700), .2)]
    cols = [(60, 'From'), (330, 'Type'), (520, 'To'), (800, 'Marking')]; ty = top + 78
    o.append(grp(''.join(text(x, ty, h, 14, G['ink'], 700) for x, h in cols) + line(60, ty + 12, 900, ty + 12, G['ink'], 2), .6))
    rows = [('HALE, Marcus', 'DIRECTOR_OF', 'Hale Logistics Ltd', 'OFFICIAL'), ('Hale Logistics Ltd', 'HOLDS', '60-16-13 ••19', 'OFFICIAL'), ('60-16-13 ••19', 'PAID', 'CARTER, Jamal', 'OFFICIAL'), ('CARTER, Jamal', 'USES', '+44 7700 900304', 'OFFICIAL')]
    for i, r_ in enumerate(rows):
        yy = ty + 44 + i * 44
        o.append(grp(''.join(text(cols[j][0], yy, v, 15, G['blue'] if j in (0, 2) else G['ink'], mono=(j == 1)) for j, v in enumerate(r_)) + line(60, yy + 14, 900, yy + 14, G['border']), round(.9 + i * .25, 2), 'a-rise'))
    def focus(x, yy, w, d, stay=False):
        return grp(rect(x - 8, yy - 24, w, 36, 'none', G['yellow'], rx=0, sw=5) + rect(x - 5, yy - 21, w - 6, 30, 'none', G['ink'], rx=0, sw=2), d, 'a-fade' if stay else 'a-blink')
    o += [focus(60, ty + 44, 150, 2.2), focus(60, ty + 88, 190, 3.2), focus(520, ty + 88, 160, 4.2), focus(520, ty + 132, 160, 5.2, True)]
    for i, (k, d) in enumerate((('Tab', 2.2), ('↓', 3.2), ('→', 4.2), ('↓', 5.2))):
        o.append(grp(rect(950 + i * 50, top + 60, 42, 36, G['light'], G['ink'], rx=4, sw=2) + text(971 + i * 50, top + 84, k, 14, G['ink'], 700, 'middle'), d, 'a-pop'))
    for i, t_ in enumerate(('Each table is one Tab stop;', 'arrow keys move between', 'cells, in the Design', "System's yellow focus.")):
        o.append(text(950, top + 136 + i * 22, t_, 14, G['ink'], d=2.4))
    for i, t_ in enumerate(('Automated accessibility scans', 'run on the screens we test.', 'An independent accessibility', 'audit is planned.')):
        o.append(text(950, top + 248 + i * 22, t_, 14, G['sec'] if i < 2 else G['ink'], 700 if i > 1 else 400, d=5.6))
    return ('Built to be used by everyone', 'The whole network is also available as tables, for a keyboard or a screen reader.',
            svg('The Matrix view of the network as a table, with a yellow focus outline moving from cell to cell', ''.join(o)))

SCENES = [g0, g1, g2, g3]; LABELS = ['One setting', 'Your service', 'Same product', 'Accessible']
NOTE = ("This is the website's own drawing of the GOV.UK theme, not a screen from the product. This site is not a gov.uk "
        "service, so the drawing shows no crown and no GOV.UK logotype, and is set in Arial. Every name in it is invented.")
