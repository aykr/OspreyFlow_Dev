#!/usr/bin/env python3
"""Builds the two OspreyFlow sites as plain static files: org/ (ospreyflow.org) and net/ (ospreyflow.net), beside
this file, in the design the owner approved on 13 November 2026 (`process/lanes/docs/BRIEF_sites2.md`). No external
request: the site's own fonts, style sheet, images and one script (the theme switch and the animations' player), and
one inline script in <head>, allowed by its hash in each page's content security policy.

    python3 build.py                  # rewrite every page and style sheet in org/ and net/
    python3 build.py --out <folder>   # into another folder (tests/test_sites.py compares the two)
    python3 build.py --images <shots> # also make each shown image from its capture in <shots> (needs Pillow)

The pages and style sheets in org/ and net/ are this script's output and are committed; a test fails when they
differ from it. The images are committed too, and made only with --images, from fresh captures.

The release each page names is read from the product's CHANGELOG at build time, never typed. The build refuses when it
differs from CHECKED_AGAINST: what the pages say is in a release, and what is only on main, was checked against that
release, and a new one means checking it again before the pages may say so."""
import argparse, base64, hashlib, math, os, random, re, shutil, html, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
SOURCE = OUT / 'source'
CHANGELOG = OUT.parents[2] / 'OspreyFlow_Core' / 'CHANGELOG.md'
#: The release every claim on the pages was last checked against (docs lane, 13 November 2026).
CHECKED_AGAINST = 'v0.5.1'
sys.path.insert(0, str(OUT))
import overview as OV, govanim as GV  # noqa: E402


def latest_release(changelog=CHANGELOG):
    m = re.search(r'^## (v\d+\.\d+\.\d+) — \d{4}-\d{2}-\d{2}$', Path(changelog).read_text(encoding='utf-8'), re.MULTILINE)
    if m is None:
        raise SystemExit(f'{changelog}: no released version')
    return m.group(1)


RELEASE = CHECKED_AGAINST  # set from the CHANGELOG by build()
ORG, NET, APP = 'https://ospreyflow.org', 'https://ospreyflow.net', 'https://ospreyflow.app'
REPO = 'https://github.com/aykr/OspreyFlow'
STATEMENT = ('OspreyFlow is an open source intelligence mapping platform for crime analysis, anti-money-laundering, '
             'fraud detection, and event monitoring and alerting, developed by Solirius Reply and released under the '
             'Apache License 2.0.')
#: The owner's decision 2 (12 November 2026): one shared mailbox for enquiries and security reports.
MAILBOX = 'servicecentre@solirius.com'
GDS = ('OspreyFlow is designed to meet the GDS Service Standard. Three independent checks are planned and not yet '
       'done: an independent accessibility audit, a penetration test and a data protection impact assessment '
       '(DPIA). Only a service assessment panel decides whether a service meets the Standard, and it looks at a '
       'service, not at a product alone.')
SYN = 'Demonstration deployment, synthetic data; every name shown is invented.'

SHOTS = {  # output name: (source file, alt text)
 'network-govuk': ('ps-govuk-network.jpg', 'A network laid out around one person and ranked by betweenness, under the GOV.UK theme'),
 'connections': ('cap-a1-j5.jpg', 'Find connections: the routes between two people, listed beside the network'),
 'communities': ('cap-a1-j6.jpg', 'The network clustered into communities, with a ranking beside it'),
 'map-time': ('cap-a2-c4-b.jpg', 'Events on a map of a site, with a heat map of the hours and weekdays they happen'),
 'questions': ('cap-a2-c8-v6.jpg', 'Questions: an answer that cites documents and graph facts, with the engine that produced it'),
 'document': ('cap-a2-c5.jpg', 'A document open in a case, with the names a model found waiting to be accepted or rejected'),
 'studio': ('cap-m1-a.jpg', 'The Ingest Studio: a list of published pipelines, one per source'),
 'verify': ('cap-a2-c3-v3.jpg', 'Verify in the Ingest Studio: what a file would create, and the rows it would reject, before it loads'),
 'matrix': ('cap-s3-a.jpg', 'The Matrix view: the network as accessible tables, with what two people share'),
 'timeline': ('cap-a2-c7-a.jpg', 'A period selected on the timeline, applied to the network above it'),
 'history': ('cap-m6.jpg', 'History: every step taken in a view, each one restorable'),
 'rule': ('mon-rule-sentence.jpg', 'A rule written as a sentence, with its preview on the last 90 days'),
 'lists': ('mon-screening-lists.jpg', 'A screening list with its version, licence and latest refresh'),
 'second-person': ('mon-second-person.jpg', 'An alert whose closing waits for a second person to approve it'),
 'hotlist': ('mon-hotlist-inbox.jpg', 'A hotlist and the alerts it raised, each saying what it matched'),
 'pack': ('mon-alert-in-pack.jpg', 'An alert added to a report pack beside an alert trend'),
 'queue-govuk': ('ps-govuk-queue.jpg', 'The alert queue under the GOV.UK theme'),
 'queue-osprey': ('ps-ospreyflow-queue.jpg', "An alert queue in OspreyFlow's own look"),
 'matrix-govuk': ('ps-govuk-matrix.jpg', 'The Matrix view under the GOV.UK theme, with a link explained in the Inspector'),
}

def esc(s): return html.escape(s, quote=True)

def fig(name, caption=None, cls=''):
    alt = SHOTS[name][1]
    cap = f'<figcaption>{caption or alt + "."} <span class="syn">{SYN}</span></figcaption>'
    return (f'<figure class="shot {cls}"><a href="assets/{name}.jpg"><img src="assets/{name}.jpg" alt="{esc(alt)}" '
            f'width="1280" height="800" loading="lazy"></a>{cap}</figure>')

def network_svg(seed=7, n=34, dark=False):
    """An original radial network motif: one centre, a ring, a few cross links."""
    r = random.Random(seed); cx, cy, R = 300, 300, 235
    ink, amber, teal = 'var(--ink,#191B1C)', 'var(--accent,#8A6318)', 'var(--second,#007177)'
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n - math.pi / 2; rr = R * (1 if i % 5 else .78)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    o = [f'<svg class="motif" viewBox="0 0 600 600" role="img" aria-label="A network drawn around one point">']
    for i, (x, y) in enumerate(pts):
        w = r.choice([.6, .6, .9, 1.4, 2.2]); c = r.choice([ink, ink, ink, teal, amber])
        o.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" style="stroke: {c}" stroke-width="{w}" opacity=".55"/>')
    for _ in range(11):
        a, b = r.sample(range(n), 2)
        o.append(f'<line x1="{pts[a][0]:.1f}" y1="{pts[a][1]:.1f}" x2="{pts[b][0]:.1f}" y2="{pts[b][1]:.1f}" style="stroke: {teal}" stroke-width=".8" opacity=".5" stroke-dasharray="3 4"/>')
    for i, (x, y) in enumerate(pts):
        c = amber if i % 7 == 0 else (teal if i % 4 == 0 else ink)
        if i % 3 == 0: o.append(f'<rect x="{x-6:.1f}" y="{y-6:.1f}" width="12" height="12" style="fill: {c}"/>')
        else: o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" style="fill: {c}"/>')
    o.append(f'<circle cx="{cx}" cy="{cy}" r="15" style="fill: {amber}"/><circle cx="{cx}" cy="{cy}" r="26" fill="none" style="stroke: {amber}" stroke-width="1.5"/></svg>')
    return ''.join(o)

#: The product's mark, the mesh cut (`apps/workspace/src/shell/BrandMark.tsx`), as the approved design draws it.
MARK = ('<svg class="mark" viewBox="0 0 48 48" aria-hidden="true">' + ''.join(
    f'<path d="{d}" style="fill: currentColor"></path>' for d in (
        'M4.9 6.7L6.4 17.2L23.9 11.1Z', 'M6.8 17.9L24.3 19.9L24.2 11.7Z', 'M6.6 18.6L8 29.1L24.2 20.7Z',
        'M8.4 30.1L9.4 41L24.4 21.2Z', 'M9.8 41.2L24.4 30.2L24.7 21.5Z', 'M25.6 11.9L26.2 29.2L43.9 25.7Z')) + '</svg>')

#: Sets the theme before the page paints. Allowed by its hash in each page's policy, and by nothing wider.
THEME_SCRIPT = ("try{if(localStorage.getItem('ospreyflow.site.theme')==='dark'){document.documentElement.classList.add('theme-dark')}}"
                "catch(e){}")
CSP = ("default-src 'self'; script-src 'self' 'sha256-" + base64.b64encode(hashlib.sha256(THEME_SCRIPT.encode()).digest()).decode()
       + "'; style-src 'self' 'unsafe-inline'; img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'")

NAV = {
 'org': [('index.html', 'Home'), ('features.html', 'Features'), ('public-sector.html', 'UK public sector'),
         ('get-started.html', 'Get started'), ('team.html', 'Team'), ('contribute.html', 'Contribute'), ('governance.html', 'Governance')],
 'net': [('index.html', 'Home'), ('sectors.html', 'Where it applies'), ('public-sector.html', 'UK public sector'),
         ('services.html', 'Services'), ('contact.html', 'Contact')],
}
TAG = {'org': 'Open-source project', 'net': 'Services'}

SOLIRIUS = ('Since 2007, Solirius has helped organisations across the public and private sector simplify complex technology '
            'problems with people-centred solutions. Solirius is part of the Reply Group. OspreyFlow is its open source '
            'intelligence mapping platform for crime analysis, anti-money-laundering, fraud detection, and event monitoring and '
            'alerting, released under the Apache License 2.0.')


def solirius_section():
    """From the current site's home page, its words, logos and photographs (the owner's instruction, 13 November 2026;
    `sites/README.md` records where each image came from)."""
    return ('<section class="band tint" id="solirius"><div class="wrap sol"><div><div class="sol-logo"><img '
            'src="assets/solirius-reply-logo-section.png" alt="Solirius Reply" width="148" height="64"></div>'
            f'<h2>Developed by Solirius Reply</h2><p>{SOLIRIUS}</p><p class="actions"><a class="btn" href="https://www.solirius.com">'
            'solirius.com</a><a class="btn" href="https://www.solirius.com/contact">Contact Solirius</a></p></div>'
            '<div class="sol-photos"><img src="assets/solirius-desk.jpg" alt="A Solirius desk with code on screen and a Solirius mug" '
            'width="700" height="312"><img src="assets/solirius-tablet.jpg" alt="A hand pointing at a service shown on a tablet" '
            'width="700" height="312"></div></div></section>')


def page(site, slug, title, desc, body):
    nav = ''.join(f'<li><a href="{h}"{" aria-current=\"page\"" if h == slug else ""}>{t}</a></li>' for h, t in NAV[site])
    org_tab = ('index.html', ' is-on" aria-current="true') if site == 'org' else (ORG, '')
    net_tab = ('index.html', ' is-on" aria-current="true') if site == 'net' else (NET, '')
    releases = ('' if site == 'org' else ORG + '/') + 'get-started.html#releases'
    sites = (f'<nav class="sites" aria-label="OspreyFlow sites"><div class="wrap">'
             f'<a class="site-tab{org_tab[1]}" href="{org_tab[0]}">Project <small>ospreyflow.org</small></a>'
             f'<a class="site-tab{net_tab[1]}" href="{net_tab[0]}">Services <small>ospreyflow.net</small></a>'
             f'<div class="tools"><a class="release" href="{releases}">Release {RELEASE}</a>'
             '<a class="reply" href="https://www.solirius.com"><img src="assets/solirius-reply-logo-header.png" alt="Solirius Reply" '
             'width="80" height="26"></a><button type="button" class="theme-btn" data-theme-toggle>Dark theme</button></div></div></nav>')
    if site == 'org':
        # The owner, 13 November 2026: one quiet line near the bottom of ospreyflow.org leads to ospreyflow.net.
        body += ('<div class="wrap"><p class="to-net">Want help to run it? Solirius Reply offers pilots, builds and support: '
                 f'<a href="{NET}">ospreyflow.net</a>.</p></div>')
        legal = ''
        foot = (f'<div><h2>The project</h2><ul><li><a href="features.html">Features</a></li><li><a href="get-started.html">Get started</a></li>'
                f'<li><a href="{REPO}">Source code</a></li><li><a href="governance.html">Governance</a></li></ul></div>'
                f'<div><h2>People</h2><ul><li><a href="team.html">Team</a></li><li><a href="contribute.html">Contribute</a></li></ul></div>'
                f'<div><h2>Elsewhere</h2><ul><li><a href="{NET}">ospreyflow.net: services from Solirius Reply</a></li>'
                f'<li><span class="soon">ospreyflow.app: the demonstration (coming)</span></li></ul></div>')
    else:
        legal = f'<p><a class="cross" href="{ORG}">The open-source project: ospreyflow.org</a></p>'
        foot = (f'<div><h2>OspreyFlow</h2><ul><li><a href="sectors.html">Where it applies</a></li><li><a href="public-sector.html">UK public sector</a></li>'
                f'<li><a href="services.html">Services</a></li><li><a href="contact.html">Contact</a></li></ul></div>'
                f'<div><h2>The project</h2><ul><li><a href="{ORG}">ospreyflow.org</a></li><li><a href="{ORG}/features.html">Every feature</a></li>'
                f'<li><a href="{ORG}/team.html">The team</a></li><li><a href="{REPO}">Source code</a></li></ul></div>'
                f'<div><h2>Elsewhere</h2><ul><li><span class="soon">ospreyflow.app: the demonstration (coming)</span></li></ul></div>')
    return f'''<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="stylesheet" href="assets/site.css">
<script>{THEME_SCRIPT}</script>
</head>
<body class="page-root is-{site}">
<a class="skip" href="#main">Skip to main content</a>
{sites}
<header class="top">
  <div class="wrap bar">
    <a class="brand" href="index.html">{MARK}<strong class="wm"><b>Osprey</b>Flow</strong></a><span class="site-tag">{TAG[site]}</span>
    <nav aria-label="Main"><ul>{nav}</ul></nav>
  </div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
  <div class="wrap cols">{foot}</div>
  <div class="wrap legal"><p>{STATEMENT}</p>{legal}</div>
</footer>
<script src="assets/site.js"></script>
</body>
</html>
'''


def player_overview():
    """The overview's markup for `source/site.js`'s player: three seats, each chapter a scene, the first one shown."""
    tabs = ''.join(f'<button type="button" class="ov-tab{" is-on" if p == 0 else ""}" aria-pressed="{"true" if p == 0 else "false"}" '
                   f'data-seat="{p}">{n}</button>' for p, (n, *_r) in enumerate(OV.SEATS))
    scenes = steps = ''
    for p, (n, _key, fns, labels) in enumerate(OV.SEATS):
        for s_, fn in enumerate(fns):
            line, sub, art = fn()
            scenes += (f'<div class="ov-scene" data-seat="{p}" data-step="{s_}"{"" if (p, s_) == (0, 0) else " hidden"}><div class="ov-head">'
                       f'<p class="ov-kicker">{n} · {s_ + 1} of {len(fns)}</p><h3 class="ov-line">{esc(line)}</h3><p class="ov-sub">{esc(sub)}</p></div>'
                       f'<div class="ov-stage">{art}</div><div class="ov-prog"><i></i></div></div>')
        steps += (f'<div class="ov-steps" data-seat="{p}"{"" if p == 0 else " hidden"}>' + ''.join(
            f'<button type="button" class="ov-step{" is-on" if s_ == 0 else ""}" data-step="{s_}">{esc(x)}</button>' for s_, x in enumerate(labels)) + '</div>')
    return (f'<div class="ov" data-player="overview"><div class="ov-top"><div class="ov-tabs" role="group" aria-label="Choose a point of view">{tabs}</div>'
            f'<button type="button" class="ov-play" data-play>Pause</button></div>{scenes}{steps}</div>')


def player_govuk():
    scenes = ''
    for s_, fn in enumerate(GV.SCENES):
        line, sub, art = fn()
        scenes += (f'<div class="gv-scene" data-seat="0" data-step="{s_}"{"" if s_ == 0 else " hidden"}><div class="gv-head">'
                   f'<p class="gv-kicker">Step {s_ + 1} of {len(GV.SCENES)}</p><h3 class="gv-line">{esc(line)}</h3><p class="gv-sub">{esc(sub)}</p></div>'
                   f'<div class="gv-stage">{art}</div><div class="gv-prog"><i></i></div></div>')
    steps = '<div class="gv-steps" data-seat="0">' + ''.join(
        f'<button type="button" class="gv-step{" is-on" if s_ == 0 else ""}" data-step="{s_}">{esc(x)}</button>' for s_, x in enumerate(GV.LABELS)) + '</div>'
    return (f'<div class="gv" data-player="govuk"><div class="gv-top"><strong>The GOV.UK theme, in four steps</strong>'
            f'<button type="button" class="gv-play" data-play>Pause</button></div>{scenes}{steps}<p class="gv-note">{esc(GV.NOTE)}</p></div>')


def overview_section():
    return sec('See it from three seats', player_overview(), ident='overview',
               intro='Follow OspreyFlow from three seats: the analyst who investigates, the developer who brings data in and writes the '
                     'rules, and the administrator who runs it. The screens are illustrations and every name is invented.')


def govuk_section():
    return sec('See the GOV.UK theme at work', player_govuk(), ident='govuk-theme',
               intro='Four short steps, from the one setting that turns it on to the screens your analysts would use. The screens are '
                     'illustrations and every name is invented.')


def hero(kicker, h1, lede, actions, site, art=True):
    acts = ''.join(f'<a class="btn {c}" href="{h}">{t}</a>' for h, t, c in actions)
    a = f'<div class="art">{network_svg(dark=(site == "net"))}</div>' if art else ''
    return (f'<section class="hero{"" if art else " plain"}"><div class="wrap grid"><div><p class="kicker">{kicker}</p><h1>{h1}</h1>'
            f'<p class="lede">{lede}</p><p class="actions">{acts}</p></div>{a}</div></section>')

def sec(h2, inner, cls='', ident='', intro=''):
    i = f' id="{ident}"' if ident else ''
    p = f'<p class="intro">{intro}</p>' if intro else ''
    return f'<section class="band {cls}"{i}><div class="wrap"><h2>{h2}</h2>{p}{inner}</div></section>'

def cards(items, cols=3):
    return f'<div class="cards c{cols}">' + ''.join(
        f'<article class="card"><h3>{t}</h3><p>{b}</p>{("<p class=more><a href=%s>%s</a></p>" % (l[0], l[1])) if l else ""}</article>'
        for t, b, *rest in items for l in [rest[0] if rest else None]) + '</div>'

def ul(items): return '<ul class="ticks">' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>'

def split(text_html, figure_html, flip=False):
    return f'<div class="split{" flip" if flip else ""}"><div>{text_html}</div>{figure_html}</div>'

DOMAINS = [
 ('Crime and intelligence analysis', 'Call records, intelligence reports, people, places and events in one network, with every link traced to the record it came from.'),
 ('Fraud detection', 'Shared addresses, accounts, contact details and directors across payments and companies, with rules that raise an alert when a pattern returns.'),
 ('Anti-money laundering and sanctions screening', 'Customers screened against sanctions lists and re-screened when a list changes; typology rules for structuring, rapid movement and circular flows.'),
 ('Prison and offender intelligence', 'Cell-shares, visits, calls, incidents and finds read together, on a map of the site and a clock of the week.'),
]
PRINCIPLES = [
 ('Every link shows where it came from', 'The source, the record and when it arrived are one click away, so a finding can be traced back at disclosure or audit.'),
 ('A model suggests, a person confirms', 'Anything a model finds is marked inferred until an analyst confirms it. Nothing a model proposes is treated as fact.'),
 ('Matches can be undone', '"Same person" is a scored link, never a merge, so a wrong match is reversed cleanly and nothing is lost.'),
 ('You see only what you are cleared for', 'Access is enforced in the store, so a hidden record leaves no trace in a count, a path or a chart.'),
]
PLACES = [
 ('The Glass', 'For investigating a case: the network, the map, the timeline, the Matrix view, reports, drawing boards and questions to a model.'),
 ('Ingest Studio', 'For bringing data in: a domain model, sources, pipelines and runs. A pipeline is verified before it is published, and a load can be reverted.'),
 ('Rules and Monitoring', 'For working alerts: one queue, rules written as sentences, hotlists, screening lists, held rows and approvals.'),
 ('Admin', 'For running the deployment: people, roles and teams, datasets, model engines, maps, operations and the audit.'),
]

# ------------------------------------------------------------------ ospreyflow.org
def org_index():
    b = hero('Open source · Apache License 2.0',
             'One network your analysts can explore, question and act on',
             'OspreyFlow is an open-source intelligence mapping platform. It turns records about people, places, objects and events into '
             'a single network, read as a graph, a map, a timeline and reports, inside your own cloud or data centre.',
             [('get-started.html', 'Get started', 'primary'), (REPO, 'Source code', ''), ('features.html', 'See every feature', 'quiet')], 'org')
    b += overview_section()
    b += sec('Where it applies', cards(DOMAINS, 4), 'tint',
             intro='For private and public sector organisations. One platform, with a domain model, rules and demonstration data for each.')
    b += sec('What makes it defensible', cards(PRINCIPLES, 4))
    b += sec('One case, five views of the same working set',
             split('<p>A filter set in one view applies in all of them. Select a person on the network and the map, the timeline and the '
                   'tables follow.</p>' + ul(['<strong>Network.</strong> Layouts, communities, ranking by centrality and the routes between two people.',
                   '<strong>Map and time.</strong> Events placed on a site or a city, and on the hours and weekdays they happen.',
                   '<strong>Matrix.</strong> The whole network as accessible tables, for a keyboard or a screen reader.',
                   '<strong>Reports.</strong> Trends and report packs, published inside OspreyFlow or exported.',
                   '<strong>Questions.</strong> Ask a model about the case; the answer cites the documents and graph facts it drew on.']) +
                   '<p class="more"><a href="features.html">Every feature</a></p>', fig('communities')))
    b += sec('Four places, each with one job', cards(PLACES, 4), 'tint',
             intro='People see only the places their roles open, and a banner always says where they are.')
    b += sec('Built in, not bolted on', split(
             '<h3>Monitoring and alerting</h3><p>Rules written as plain sentences, previewed on the last 90 days before they go live. '
             'A person decides every alert, with a reason, and a second person approves the decisions that matter.</p>'
             '<h3>Your own models, or one you choose</h3><p>The deployment\'s own model answers by default and nothing leaves. An administrator '
             'may enable a hosted engine; material reaches it only when its handling code and its dataset both allow it.</p>'
             '<h3>A UK public sector option</h3><p>The GOV.UK theme is a setting chosen at install, not a fork. '
             '<a href="public-sector.html">How it works, and what "designed to meet" means</a>.</p>', fig('rule'), flip=True))
    b += sec('Run it your way', cards([
             ('Lite', 'One computer, for evaluation and demonstrations. Docker, 16 GB of memory, and a few commands.'),
             ('Small', 'One server, in your cloud account or your own network, served over HTTPS; on a server of your own, with your organisation\'s sign-in.'),
             ('Enterprise', 'A Kubernetes cluster with the stores clustered and the cloud\'s managed services underneath.')]) +
             '<p class="more"><a href="get-started.html">Prerequisites and the install commands</a></p>')
    b += sec('Who is behind it', '<p class="intro">OspreyFlow was created at Solirius Reply, which develops it and looks after the project. '
             'It is built in the open, and contributions are welcome.</p><p class="actions"><a class="btn" href="team.html">The team</a>'
             '<a class="btn" href="contribute.html">Contribute</a><a class="btn quiet" href="governance.html">How decisions are made</a></p>')
    b += solirius_section()
    return page('org', 'index.html', 'OspreyFlow: open-source intelligence mapping', STATEMENT, b)

def org_features():
    b = hero(f'Features · release {RELEASE}', 'Everything in OspreyFlow today',
             f'Everything on this page is built and in release {RELEASE}, except the section headed "On main, coming with the next release". '
             'Screens are from demonstration deployments with synthetic data, and are being replaced.', [('get-started.html', 'Get started', 'primary')], 'org', art=False)
    toc = [('glass', 'The Glass'), ('studio', 'Ingest Studio'), ('monitoring', 'Rules and Monitoring'), ('boards', 'Drawing boards'),
           ('models', 'Models and questions'), ('admin', 'Admin and access'), ('architecture', 'Architecture'), ('coming', 'On main, coming next')]
    b += '<nav class="toc wrap" aria-label="On this page"><ul>' + ''.join(f'<li><a href="#{i}">{t}</a></li>' for i, t in toc) + '</ul></nav>'
    b += sec('The Glass: analysis', split(ul([
        '<strong>Network.</strong> Radial, organic and clustered layouts; communities; ranking by betweenness and other measures; expand from any node.',
        '<strong>Find connections.</strong> The shortest routes between two people, each step backed by its records.',
        '<strong>Connection strength.</strong> How strongly a link is drawn rests on its count and its recency. How rare a shared value is is shown beside it, explained in the Inspector and usable in a rule.',
        '<strong>Map.</strong> Events on a site plan or a street map; draw a boundary and filter to what falls inside it.',
        '<strong>Timeline.</strong> Select a period and every view dims what falls outside it; a heat map shows the hours and weekdays.',
        '<strong>Matrix.</strong> The network as accessible tables, with each link\'s strength and how rare what its two ends share is.',
        '<strong>Reports.</strong> Trends, report packs with marked notes, publishing to viewers and export.',
        '<strong>History.</strong> Every step in a view is kept and can be restored.']), fig('connections')) +
        '<div class="pair">' + fig('map-time') + fig('matrix') + '</div>', ident='glass')
    b += sec('Ingest Studio: bringing data in', split(ul([
        '<strong>1 Model.</strong> A domain model for each dataset: its entity types, link types and markings. Starters for crime, anti-money laundering, fraud and cyber.',
        '<strong>2 Sources.</strong> Files, a SQL database, an HTTP API or JSON files, and on the shared-platform profile S3 buckets and Athena, each with a declared marking and legal basis.',
        '<strong>3 Pipelines.</strong> Each source with its own profile, mapping and load, published as a version.',
        '<strong>4 Runs.</strong> By hand, on a schedule or when a file arrives. Verify shows what a file would create and which rows it would reject before anything loads.',
        '<strong>Held rows.</strong> A rule can hold rows for a reviewer before a load commits.',
        '<strong>Revert.</strong> A load can be taken back; its links and events are withdrawn and the record of it kept.',
        '<strong>Entity resolution.</strong> Matching across sources with a strictness an analyst can see and change.']), fig('verify'), flip=True),
        'tint', 'studio', 'The gate into the network. Loaded data reaches a dataset only through a pipeline someone published.')
    b += sec('Rules and Monitoring', split(ul([
        '<strong>One queue</strong> for every alert you may see, by severity and age.',
        '<strong>Rules as sentences,</strong> built from your own types and links, previewed on the last 90 days.',
        '<strong>Hotlists and watches</strong> on a phone number, an email address or an account, each with a review date.',
        '<strong>Screening lists.</strong> Connectors for the UK Sanctions List, OFAC, the EU and UN consolidated lists and OpenSanctions, re-screened when a list you load changes. The UN and OpenSanctions lists stay synthetic until their licences are confirmed.',
        '<strong>Templates</strong> for structuring, rapid movement, circular flow, high-risk jurisdictions, large cash and dormant accounts.',
        '<strong>Closing reasons, and a second person</strong> for a high-severity close.',
        '<strong>From an alert to a report pack,</strong> and to a monitoring dashboard.']), fig('second-person')) +
        '<div class="pair">' + fig('lists') + fig('hotlist') + '</div>', ident='monitoring')
    b += sec('Drawing boards', '<div class="cols2"><div><p>The analysis canvas shows what the data says. A drawing board is where an analyst '
        'writes down what they know that the data does not yet say.</p>' + ul([
        'Declare a person, an account or a place and draw the links between them, by pointer or by keyboard.',
        "Each case has its own analyst layer; the source data stays clean and no other case sees a drawn item.",
        'Every drawn item records who drew it, its marking, a grading (5x5x5 by default) and its source: a note, a document, or both.',
        'Promotion into a dataset happens as a load, reviewed by a second person where the dataset asks for it.']) + '</div><div>' + ul([
        'A drawn item that resembles a loaded one is offered as a pair; the analyst decides, and nothing is merged.',
        'An analyst can propose a new link type; a data engineer decides whether it joins the domain model.',
        'A withdrawn item is kept in the record, never erased.']) + '</div></div>', 'tint', 'boards')
    b += sec('Models and questions', split(ul([
        "<strong>Ask &amp; Chat.</strong> Ask about the documents and the graph around your selection. Each cited fact is a button that selects it on the canvas.",
        '<strong>Extraction.</strong> Names, numbers and places found in documents arrive as inferred, to accept or reject. On the shared-platform profile, a second, open-source extraction engine for structured facts in documents.',
        '<strong>Local by default.</strong> Extraction, vision, transcription and embeddings run on the deployment itself.',
        "<strong>Hosted engines, by permission.</strong> Each dataset has an egress setting, and material leaves only when that and its handling code both allow it. On the shared-platform profile, your organisation's own AI gateway, or Amazon Bedrock in London.",
        '<strong>Every answer names the engine and model that produced it.</strong>',
        '<strong>Keys are write-only,</strong> held by the model gateway alone, with limits and usage per engine.']), fig('questions'), flip=True), ident='models')
    b += sec('Admin and access', cards([
        ('People, roles and teams', 'Built-in roles (Analyst, Data Engineer, Administrator, Reports Viewer, Rule author) and roles you define. No one can give more than they hold.'),
        ('Sign-in', "OspreyFlow's own accounts. On a server of your own, your organisation's account through Microsoft Entra ID, ADFS or another OpenID Connect provider."),
        ('Markings and clearance', 'Handling markings on every record, a highest allowed marking per dataset, and reads filtered in the store.'),
        ('Audit', 'Who did what and when, including every export, every approval and every change to what may leave the deployment.'),
        ('Dashboards', 'Apache Superset embedded in a case with the same sign-in, reading a reporting feed.'),
        ('Backups and updates', 'Signed releases. On one computer or a server of your own, installed from a release, an update is backed up first and rolled back on failure; Enterprise is updated by installing the new release.'),
        ('A shared government platform', "A profile for shared government Kubernetes platforms: one namespace, the platform's managed services, non-root containers and a single-copy shape for a proof of concept, with sign-in through Microsoft Entra ID. Installed and checked on a test cluster, not yet on a platform. In this release, loads there are started by hand and reporting is not on it; the administration guide's section 6a has every limit.")]), 'tint', 'admin')
    b += sec('Architecture', '<p class="intro">Three tiers, separated by four typed ports, so an engine can be swapped without touching what sits above it.</p>' + cards([
        ('The Glass', 'React and TypeScript. Sigma.js and Graphology for the network, MapLibre GL with PMTiles for maps, Apache ECharts for charts, GOV.UK Frontend for the GOV.UK theme.'),
        ('The Conduit', 'Python and FastAPI. The API, access control, entity resolution, extraction and model routing. Stateless.'),
        ('The Vault', 'ArcadeDB for the graph, DuckDB or ClickHouse for analytics, OpenSearch or PostgreSQL for search, PostgreSQL for cases, roles and audit, Valkey, S3-compatible object storage or Azure Blob, LiteLLM as the model gateway.')]) +
        '<p>The four ports are the graph, analytics, compute and models. An adapter is supported once it passes the same conformance suite as every other adapter behind that port.</p>', ident='architecture')
    b += sec('On main, coming with the next release', ul([
        'On the shared-platform profile, scheduled runs: a pipeline\'s schedule and watched folder, rules, watches and list refreshes running as their owner.',
        'Reporting on the shared-platform profile, through Apache Superset.',
        'The shared-platform profile\'s data-safety fixes, to its backups and restore.']) +
        f'<p>These are merged in development and not in release {RELEASE}. They arrive with the next release.</p>', 'tint', 'coming')
    return page('org', 'features.html', 'Features · OspreyFlow', 'Every feature in the current OspreyFlow release: analysis, ingest, monitoring, drawing boards, models and administration.', b)

def org_public_sector():
    site = 'org'
    b = hero('UK public sector', 'OspreyFlow for the UK public sector',
             'The whole product under the GOV.UK Design System\'s look, for services on a gov.uk domain, with government security markings, '
             f'need-to-know access and a full audit trail. Everything on this page is in release {RELEASE}.',
             [('get-started.html', 'Install with a GOV.UK starter', 'primary'), (NET + '/public-sector.html', 'Help from Solirius Reply', '')],
             site, art=False)
    b += govuk_section()
    b += sec('What "designed to meet" means', f'<p class="callout">{GDS}</p>')
    b += sec('The GOV.UK theme, chosen at install', split(
        '<p>The GOV.UK theme is a deployment setting, not a separate edition or a fork. One setting gives every page the GOV.UK header and '
        'footer, the phase banner and the service\'s own name. Everything else is the same product, with the same features and the same tests.</p>' + ul([
        '<strong>For services on a gov.uk domain.</strong> The GOV.UK look belongs to those services, and is to be used for those alone. It stays available on one computer for a demonstration.',
        "<strong>Your service's name, not ours.</strong> The install asks for the service's name, the organisation and the phase.",
        '<strong>Switch back at any time.</strong> Nothing about the data or the cases changes.',
        '<strong>The four places in the GOV.UK header,</strong> with the banner as a GOV.UK notification banner.']), fig('network-govuk')), 'tint')
    b += sec('One setting changes the look', '<div class="pair">' + fig('queue-govuk', 'The alert queue under the GOV.UK theme.') +
             fig('queue-osprey', "An alert queue in OspreyFlow's own look.") + '</div>')
    b += sec('Starters: a theme and a domain in one command',
        '<div class="tablewrap"><table><caption>The ten starters</caption><thead><tr><th scope="col">Domain</th><th scope="col">OspreyFlow theme</th><th scope="col">GOV.UK theme</th></tr></thead><tbody>' +
        ''.join(f'<tr><th scope="row">{d}</th><td><code>ospreyflow-{k}</code></td><td><code>govuk-{k}</code></td></tr>' for d, k in
                [('Crime', 'crime'), ('Anti-money laundering', 'aml'), ('Fraud', 'fraud'), ('Cyber', 'cyber'), ('Blank', 'blank')]) +
        '</tbody></table></div><pre><code>ospreyflow install --mode lite --starter govuk-crime --service-name "Analyse crime intelligence" --organisation "Your organisation"</code></pre>'
        '<p>Each starter except Blank comes with its own synthetic demonstration data.</p>', 'tint')
    b += sec('What a security or architecture team will ask', cards([
        ('Where does the data live?', "Inside your own cloud account or data centre. The deployment does not call out on its own: the install downloads its images and model, a server fetches its own certificate, and anything else, such as a hosted model or your organisation's sign-in, is switched on by an administrator."),
        ('Who can see what?', 'Handling markings on every record, clearance and unit on every person, and reads filtered in the store, so a hidden record leaves no trace in a count.'),
        ('Can a finding be traced?', 'Every link keeps its source, its record and when it arrived. Every export and approval is in the audit.'),
        ('What about models?', 'Local by default. A hosted engine receives material only when the dataset and the handling code both allow it.'),
        ('Is it accessible?', 'Designed to WCAG 2.2 AA, with automated accessibility scans on every screen we test, in the light and dark themes and under GOV.UK on most of them, and a Matrix view of the network as tables. An independent audit is planned.'),
        ('What is inside it?', 'Open-source components throughout, each listed with its licence. No software licence fee.')]))
    return page(site, 'public-sector.html', 'UK public sector · OspreyFlow', 'OspreyFlow under the GOV.UK theme: designed to meet the GDS Service Standard, with security markings, need-to-know access and audit.', b)

def net_public_sector():
    """The owner, 13 November 2026: the full UK public sector page is ospreyflow.org's; this one gives the services angle
    and leads to it, so there is one source and nothing to drift."""
    b = hero('UK public sector', 'OspreyFlow for a UK public sector service',
             "OspreyFlow has a GOV.UK theme for services on a gov.uk domain, with government security markings, need-to-know access "
             "and a full audit trail. Solirius Reply helps a public sector team take it from a pilot to a live service.",
             [('contact.html', 'Talk to Solirius Reply', 'primary'), (ORG + '/public-sector.html', 'The UK public sector page on ospreyflow.org', '')],
             'net', art=False)
    b += sec('What "designed to meet" means', f'<p class="callout">{GDS}</p>')
    b += sec('How Solirius Reply helps a public sector team', ul([
        "<strong>Pilot.</strong> A few weeks on your own or anonymised data, under the GOV.UK theme with your service's name.",
        "<strong>Build.</strong> A deployment in your own tenancy, with your organisation's sign-in, roles and markings.",
        '<strong>Run and expand.</strong> Support once it is live, and help as it grows.']) +
        '<p class="more"><a href="services.html">How we work with you</a></p>', 'tint')
    b += sec('The whole picture, on the project\'s own site', f'<p>How the GOV.UK theme works, the starters and what a security or '
             f'architecture team will ask are on <a href="{ORG}/public-sector.html">ospreyflow.org\'s UK public sector page</a>.</p>')
    return page('net', 'public-sector.html', 'UK public sector · OspreyFlow', 'How Solirius Reply helps a UK public sector team adopt OspreyFlow under the GOV.UK theme.', b)


def org_start():
    b = hero(f'Get started · release {RELEASE}', 'Install OspreyFlow', 'One command per computer, then a check, then the install. Lite runs on one machine and is the place to start. '
             f'Everything on this page is in release {RELEASE}.',
             [(REPO, 'Open the repository', 'primary')], 'org', art=False)
    b += sec('Three commands', f'<pre><code>git clone {REPO}.git\ncd OspreyFlow\nsh install.sh</code></pre>'
        '<p>On Windows, run <code>install.ps1</code>. Then:</p>'
        '<pre><code>ospreyflow doctor                 # are the prerequisites in place?\nospreyflow install --mode lite    # asks a few questions; --gui opens a guided page\nospreyflow open                   # the Glass in your browser</code></pre>'
        '<p>Every question the install asks can be answered in a file instead (<code>--config install.yaml --yes</code>).</p>')
    b += sec('What each mode needs', '<div class="tablewrap"><table><thead><tr><th scope="col">Mode</th><th scope="col">What you need</th></tr></thead><tbody>'
        '<tr><th scope="row">Lite: one machine</th><td>Docker, 16 GB of memory for Docker (32 GB is comfortable), 60 GB of free disk, Git, and internet for the first install.</td></tr>'
        '<tr><th scope="row">Small: one server in your cloud</th><td>An AWS or Azure account, OpenTofu, that cloud\'s command line, Git, uv and a DNS name you control.</td></tr>'
        '<tr><th scope="row">Small: your own server</th><td>One Linux server (amd64) with 32 GB of memory, Docker, Git, uv and Python 3.12, port 443, three names in your DNS and a certificate for them, and access to the releases and their images (or your own mirror).</td></tr>'
        '<tr><th scope="row">Enterprise: Kubernetes</th><td>An EKS or AKS cluster, or the account to build one, with the cloud\'s managed PostgreSQL, Valkey and object store.</td></tr>'
        '</tbody></table></div><p><code>ospreyflow doctor</code> checks these for the mode you choose and says what to fix.</p>', 'tint')
    b += sec('Demonstration data', '<p>Each starter except Blank loads synthetic demonstration cases, so there is something to explore straight away. '
        'No install adds real data: a public dataset is one you download and accept yourself.</p>')
    b += sec('The guides', cards([
        ('Installation and Administration Guide', 'Choosing a mode, installing, people and accounts, backups, updates and every setting.'),
        ('User Guide', 'Cases, the network, map, timeline and reports, alerts and watches, and how what you see is decided.'),
        ('Developer Guide', 'The Ingest Studio from a first pipeline to a scheduled one, the domain model, screening lists and the API.'),
        ('Architecture Guide', 'How it is built, what crosses each boundary and how access is enforced, for architects and security reviewers.')], 4) +
        f'<p>Each is in the repository\'s <code>docs/</code> folder, as Markdown and as a PDF with screenshots. <a href="{REPO}">Open the repository</a>.</p>', 'tint')
    b += sec('Releases', '<p>A checkout of a release tag installs that release\'s own signed images. Nothing checks for updates on its own, '
        'because the deployment never calls out; ask with <code>ospreyflow update --check</code>.</p>', ident='releases')
    return page('org', 'get-started.html', 'Get started · OspreyFlow', 'Install OspreyFlow: prerequisites, the three commands, the modes and the guides.', b)

def person(name, role, text, placeholder=False):
    c = ' placeholder' if placeholder else ''
    return f'<article class="person{c}"><div class="avatar" aria-hidden="true">{MARK}</div><div><h3>{name}</h3><p class="role">{role}</p>{('<p>'+text+'</p>') if text else ''}</div></article>'

def org_team():
    b = hero('Team', 'The people behind OspreyFlow', 'OspreyFlow was created at Solirius Reply and is developed in the open. These are the people who '
             'started it, and the roles anyone can grow into.', [('contribute.html', 'Contribute', 'primary'), ('governance.html', 'How decisions are made', '')], 'org', art=False)
    b += sec('Project leads', '<div class="people">' +
        person('Ayan Kar', 'Creator and Chief Architect', 'Conceived OspreyFlow, designed its architecture and directs its build. Decides questions of architecture and design.') +
        person('Matthew Couldridge', 'Product Lead', 'Owns the roadmap. Runs OspreyFlow with the organisations evaluating it and brings what they need back into the product.') + '</div>')
    b += sec('Founding contributors', '<p class="intro">The people who shaped OspreyFlow before its first public release.</p><div class="people four">' +
        ''.join(person(n, 'Founding contributor', '') for n in ['Will Forbes', 'Harrison Boyle-Thomas', 'Graham Burnside', 'Laurence Rawlings']) + '</div>', 'tint')
    b += sec('How it is built', '<p>The design, the architecture and every decision in OspreyFlow are the team\'s. Much of the code is written with '
        'AI coding tools working to that design, and every change passes the same reviews, tests and checks before it is merged. '
        'We say so because provenance matters in this product, and it matters in how the product is made.</p>')
    b += sec('Roles in the project', '<div class="tablewrap"><table><thead><tr><th scope="col">Role</th><th scope="col">What it means</th><th scope="col">How someone gets there</th></tr></thead><tbody>'
        '<tr><th scope="row">Contributor</th><td>Anyone whose change, guide, bug report or review has been accepted.</td><td>Open an issue or a pull request.</td></tr>'
        '<tr><th scope="row">Maintainer</th><td>Reviews and merges changes in an area of the product.</td><td>By invitation of the project leads, after sustained contribution.</td></tr>'
        '<tr><th scope="row">Founding contributor</th><td>Recognition for the people who built OspreyFlow before its public release.</td><td>A fixed group.</td></tr>'
        '<tr><th scope="row">Project lead</th><td>Answers for the architecture or the roadmap.</td><td>Named by the project\'s steward.</td></tr>'
        '</tbody></table></div><p>Solirius Reply is the project\'s steward. <a href="governance.html">Governance</a> sets out who decides what.</p>', 'tint')
    return page('org', 'team.html', 'Team · OspreyFlow', 'The people behind OspreyFlow, their roles, and the roles contributors can grow into.', b)

def org_contribute():
    b = hero('Contribute', 'Help build OspreyFlow', 'Code is one way to contribute. A connector for a source you know, a domain model for your field, '
             'a clearer page in a guide or a well-described bug are all as welcome.', [(REPO, 'Open the repository', 'primary')], 'org', art=False)
    b += sec('Where to start', cards([
        ('Try it and tell us', 'Install Lite with a starter, work through a demonstration case, and open an issue for anything that confused you or broke.'),
        ('Connectors and pipelines', 'A connector reads one kind of source; a pipeline maps it to a domain model. Each is a small, self-contained file with its own test.'),
        ('Domain models', 'Crime, anti-money laundering, fraud and cyber ship today. A model for another field is a contribution in itself.'),
        ('Guides', 'The guides live in the repository as Markdown. Corrections and clearer wording are reviewed like code.'),
        ('Adapters', 'Each of the four ports has a conformance suite. An adapter for another engine is supported once it passes it.'),
        ('Accessibility', 'The screens are scanned automatically in the light and dark themes. Reports from people using assistive technology are especially valuable.')]))
    b += sec('What we ask of a change', ul([
        '<strong>Synthetic data only.</strong> No real person\'s data in a test, a fixture, a screenshot or an issue.',
        '<strong>A test that fails first.</strong> A fix arrives with a test that fails without it.',
        '<strong>Access control is never weakened.</strong> A read that skips the viewer\'s access is refused at review.',
        '<strong>Plain words on screen.</strong> A refusal says what was refused and why, in words a person can act on.',
        '<strong>You have the right to submit it.</strong> Contributions are made under the Apache License 2.0.']), 'tint')
    b += sec('How a change is reviewed', '<ol class="steps"><li>Open an issue describing the problem, or comment on an existing one.</li>'
        '<li>Open a pull request. A maintainer runs the project\'s checks on it before it is merged: tests, licence checks, accessibility scans and image scans.</li>'
        '<li>A maintainer reviews it. A change to access control or to what may leave a deployment gets a second reviewer.</li>'
        '<li>Once merged, it ships in the next release and is named in the change log.</li></ol>'
        '<p class="note">The repository\'s contributing guide and code of conduct are not yet in the repository. Until then, open an issue to start a conversation.</p>')
    b += sec('Security', f'<p>Please do not open a public issue for a security problem. Report it privately to <a href="mailto:{MAILBOX}">{MAILBOX}</a>. '
        "Put 'OspreyFlow security' in the subject.</p>", 'tint')
    return page('org', 'contribute.html', 'Contribute · OspreyFlow', 'How to contribute to OspreyFlow: where to start, what a change needs and how it is reviewed.', b)

def org_governance():
    b = hero('Governance', 'How decisions are made', 'A short account of who decides what in OspreyFlow, and how that can change.', [], 'org', art=False)
    b += sec('The steward', '<p>Solirius Reply created OspreyFlow, employs its project leads and looks after the project: its name, its repository, '
        'its releases and its security process. The code is released under the Apache License 2.0, which lets anyone use, change and distribute it.</p>')
    b += sec('Who decides what', '<div class="tablewrap"><table><thead><tr><th scope="col">Decision</th><th scope="col">Who decides</th></tr></thead><tbody>'
        '<tr><th scope="row">What the product does next (the roadmap)</th><td>The Product Lead, after hearing from users, maintainers and the steward.</td></tr>'
        '<tr><th scope="row">Architecture and design</th><td>The Chief Architect. Each decision is written down as a numbered record with its reasons.</td></tr>'
        '<tr><th scope="row">Whether a change is merged</th><td>A maintainer of that area. Changes to access control need two.</td></tr>'
        '<tr><th scope="row">Who becomes a maintainer</th><td>The project leads together.</td></tr>'
        '<tr><th scope="row">Releases</th><td>The project leads, once every check has passed.</td></tr>'
        '</tbody></table></div>', 'tint')
    b += sec('Principles the project holds to', ul([
        'Decisions are recorded, with their reasons, where everyone can read them.',
        'The same checks apply to everyone\'s changes, the project leads\' included.',
        'A disagreement is settled by the person who answers for that area, and the decision is written down.',
        'The open-source product is the whole product. Solirius Reply sells services around it, not a separate edition.']))
    b += sec('Changing this', '<p>This page describes how the project runs today, with a small founding team. As contributors join, it will change, '
        'and changes will be proposed in the open. <span class="note">A governance file and a list of maintainers are not yet in the repository.</span></p>', 'tint')
    return page('org', 'governance.html', 'Governance · OspreyFlow', 'Who decides what in the OspreyFlow project: the steward, the project leads and maintainers.', b)

# ------------------------------------------------------------------ ospreyflow.net
def net_index():
    b = hero('Intelligence mapping · from Solirius Reply',
             'See the whole picture. Own the platform it runs on.',
             'OspreyFlow joins records about people, places, objects and events into one network your analysts can explore, question and act on. '
             'It is open source, with no software licence fee, and runs inside your own cloud or data centre.',
             [('contact.html', 'Talk to us', 'primary'), ('services.html', 'How we work with you', ''), (ORG, 'The open-source project', 'quiet')], 'net')
    b += overview_section()
    b += sec('The problem: the picture is in pieces', cards([
        ('Five sources, five tools', 'Call records in spreadsheets, intelligence reports in another system, a network drawn by hand, pins on a separate map, watch lists somewhere else.'),
        ('What goes wrong', 'Links are missed between tools and teams. The chain back to the source breaks in every copy. Access is set up five times, five ways.'),
        ('What it costs', 'Analysts spend their weeks preparing data. Findings are hard to defend when they are challenged. Figures for leadership are typed in again by hand.')]))
    b += sec('One platform, one picture', split(
        '<p>OspreyFlow loads each source through a pipeline, resolves the same person across them and shows the result as one network, '
        'read as a graph, a map, a timeline, tables and reports. A filter in one view applies in all of them.</p>' +
        ul(['Monitoring and alerting built in: rules written as sentences, hotlists and screening lists.',
            'Questions to a model, answered from the case and citing what they drew on.',
            'Dashboards for leadership, from the same figures.']) + f'<p class="more"><a href="{ORG}/features.html">Every feature, on ospreyflow.org</a></p>', fig('network-govuk')), 'tint')
    b += sec('Why organisations choose it', cards([
        ('Defensible', 'Every link shows where it came from. A model\'s suggestion stays inferred until a person confirms it. A match can be undone.'),
        ('Yours', 'Apache-2.0 open source. You own the data, the deployment and the roadmap you ask of it. No per-seat licence.'),
        ('Inside your boundary', 'Runs in your own cloud account or data centre. Nothing leaves unless an administrator enables it for a dataset.'),
        ('Need-to-know by design', 'Access is enforced in the store, so a record someone may not see leaves no trace in a count, a path or a chart.')], 4))
    b += sec('Where it applies', cards([(t, d, ('sectors.html', 'More')) for t, d in DOMAINS], 4), 'tint',
             intro='For private and public sector organisations alike.')
    b += sec('For the UK public sector', split(
        '<p>OspreyFlow includes a dedicated configuration for UK government: the GOV.UK Design System\'s look, government security markings '
        'with need-to-know access, and a full audit trail.</p><p class="callout">' + GDS + '</p><p class="more"><a href="public-sector.html">The UK public sector option</a></p>',
        fig('queue-govuk', 'The alert queue under the GOV.UK theme.'), flip=True))
    b += sec('How Solirius Reply helps', cards([
        ('Pilot', 'A few weeks on your own or anonymised data, with a handful of analysts, ending in a short report of what was found.', ('services.html', 'More')),
        ('Build', 'A production deployment in your own tenancy: pipelines for your sources, your sign-in and your look.', ('services.html', 'More')),
        ('Run and expand', 'Support, new sources and teams, and dashboards for leadership.', ('services.html', 'More'))]) +
        '<p class="actions"><a class="btn primary" href="contact.html">Talk to us</a></p>')
    b += solirius_section()
    return page('net', 'index.html', 'OspreyFlow: intelligence mapping from Solirius Reply', STATEMENT, b)

def net_sectors():
    b = hero('Where it applies', 'One platform, four kinds of investigation', 'Every investigation comes down to the same questions: who is behind it, how two people are '
             'linked, where and when, and what leadership needs to see. OspreyFlow answers them on one canvas.', [('contact.html', 'Talk to us', 'primary')], 'net', art=False)
    S = [
     ('crime', 'Crime and intelligence analysis', 'For police forces, intelligence units and investigators.', [
        'Call records, intelligence reports, people, vehicles and places in one network.',
        'The shortest routes between two people, each step backed by its records.',
        'Who holds a group together: ranking by centrality, not just by who is busiest.',
        'A drawing board for what an analyst knows that the data does not yet say, graded and sourced.',
        'Every link traced to its source, for disclosure.'], 'connections'),
     ('fraud', 'Fraud detection', 'For counter-fraud teams in government, insurers and any organisation paying money out.', [
        'Shared addresses, bank accounts, devices and directors across claims, payments and suppliers.',
        'How rare a shared value is, shown beside each link, so a common postcode does not drown a shared bank account.',
        'Rules that raise an alert when a pattern returns, previewed on past data before they go live.',
        'Rows held for a reviewer before a load commits.',
        'Report packs and dashboards for the people who answer for the money.'], 'rule'),
     ('aml', 'Anti-money laundering and sanctions screening', 'For regulators and regulated firms.', [
        'Customers screened against the UK Sanctions List, OFAC and the EU consolidated list, and re-screened when a list you load changes.',
        'A match is a suggestion until a person confirms it.',
        'Typology templates: structuring, rapid movement, circular flow, high-risk jurisdictions, large cash and dormant accounts.',
        'Layered ownership read as a network.',
        'A closing reason on every alert, and a second person for the decisions that matter.'], 'lists'),
     ('prisons', 'Prison and offender intelligence', 'For prison intelligence units and offender management.', [
        'Cell-shares, visits, calls, incidents and finds read together.',
        'Events on a plan of the establishment, by wing and yard, and on a clock of the week.',
        'Who is the broker between groups, not only who is the most connected.',
        'Intelligence reports read by a model, with the names it finds waiting for an analyst to accept.',
        'The GOV.UK look for a service on a gov.uk domain.'], 'map-time'),
    ]
    b += '<nav class="toc wrap" aria-label="On this page"><ul>' + ''.join(f'<li><a href="#{i}">{t}</a></li>' for i, t, *_ in S) + '</ul></nav>'
    for n, (i, t, who, pts, shot) in enumerate(S):
        b += sec(t, split(f'<p class="who">{who}</p>' + ul(pts), fig(shot), flip=bool(n % 2)), 'tint' if n % 2 else '', i)
    b += sec('Something else?', '<p>OspreyFlow has a domain model for each dataset, so it adapts to fields beyond these four, cyber among them. '
             '<a href="contact.html">Tell us what you are investigating</a>.</p>')
    return page('net', 'sectors.html', 'Where it applies · OspreyFlow', 'OspreyFlow for crime and intelligence analysis, fraud detection, anti-money laundering and sanctions screening, and prison and offender intelligence.', b)

def net_services():
    b = hero('Services', 'A pilot, a build, and the running of it', 'The software is open source and free to use. Solirius Reply provides the people who make it work '
             'on your data, in your environment, for your analysts.', [('contact.html', 'Talk to us', 'primary')], 'net', art=False)
    b += sec('Three stages', '<ol class="stages"><li><h3>Pilot</h3><p>A few weeks, on your own or anonymised data, with two or three analysts and an administrator.</p>' +
        ul(['Two or three of your sources loaded through pipelines.', 'A case your analysts already know, rebuilt in OspreyFlow.', 'A short report: what was found, what it took and what a full deployment would need.']) +
        '</li><li><h3>Build</h3><p>A production deployment in your own tenancy.</p>' +
        ul(['Pipelines for your sources, scheduled and monitored.', "Your organisation's sign-in, roles and markings.", 'Your look, including the GOV.UK theme for a gov.uk service.', 'Rules, hotlists and screening lists set up with your teams.']) +
        '</li><li><h3>Run and expand</h3><p>Support once it is live, and help as it grows.</p>' +
        ul(['Managed support and updates.', 'New sources, teams and units.', 'Dashboards for leadership.', 'Training for analysts, data engineers and administrators.']) + '</li></ol>')
    b += sec('What you keep', cards([
        ('The software', 'Apache-2.0. If we part ways, everything keeps running and you can take it forward yourselves or with anyone else.'),
        ('The data', 'It never leaves your environment. We work inside your boundary, under your controls.'),
        ('The configuration', 'Your domain models, pipelines and rules are files you own and can read.')]), 'tint')
    b += sec('Deployment options', cards([
        ('Your cloud account', 'AWS or Azure, on one server or a Kubernetes cluster, using the cloud\'s managed services.'),
        ('Your own data centre', 'One Linux server or a cluster in your network, with your own certificates.'),
        ('A shared government platform', 'A profile for shared Kubernetes platforms, in the current release: installed and checked on a test cluster, not yet on a platform.')]))
    b += sec('Who we are', f'<p>Solirius Reply created OspreyFlow and leads its development. <a href="{ORG}/team.html">Meet the team</a> on the project\'s own site.</p>', 'tint')
    return page('net', 'services.html', 'Services · OspreyFlow', 'How Solirius Reply helps organisations adopt OspreyFlow: a pilot, a build, and running it.', b)

def net_contact():
    b = hero('Contact', 'Talk to us', 'Tell us what you are investigating and what you use today. We will show you OspreyFlow on data like yours.', [], 'net', art=False)
    b += sec('Get in touch', f'<div class="cols2"><div><h3>Solirius Reply</h3><p><a href="mailto:{MAILBOX}">{MAILBOX}</a></p>'
        '<p>It helps to know:</p>' + ul(['the kind of investigation or monitoring you do;', 'the sources you work from;', 'where it would need to run;', 'roughly how many analysts would use it.']) + '</div>'
        '<div><h3>See it first</h3><p><span class="soon">A demonstration at ospreyflow.app is coming.</span></p>'
        f'<p>Or install it yourself in a few minutes: <a href="{ORG}/get-started.html">get started on ospreyflow.org</a>.</p></div></div>')
    return page('net', 'contact.html', 'Contact · OspreyFlow', 'Contact Solirius Reply about OspreyFlow.', b)

#: Copied as they are into each site's assets/: the style sheet, the script, the fonts and their licences, and Solirius
#: Reply's logos and photographs (the current site's own, at the owner's instruction).
ASSETS = {'site.css': 'site.css', 'site.js': 'site.js',
          **{f'fonts/{p.name}': f'fonts/{p.name}' for p in sorted((SOURCE / 'fonts').iterdir())},
          **{p.name: f'solirius/{p.name}' for p in sorted((SOURCE / 'solirius').iterdir())}}


def build(out=OUT, shots=None, changelog=CHANGELOG):
    global RELEASE
    RELEASE = latest_release(changelog)
    if RELEASE != CHECKED_AGAINST:
        raise SystemExit(f'The CHANGELOG\'s latest release is {RELEASE}, and the pages were checked against {CHECKED_AGAINST}. Check every '
                         f'claim marked as in a release or only on main against {RELEASE}, then set CHECKED_AGAINST to it.')
    sites = {
     'org': {'index.html': org_index(), 'features.html': org_features(), 'public-sector.html': org_public_sector(), 'get-started.html': org_start(),
             'team.html': org_team(), 'contribute.html': org_contribute(), 'governance.html': org_governance()},
     'net': {'index.html': net_index(), 'sectors.html': net_sectors(), 'public-sector.html': net_public_sector(), 'services.html': net_services(),
             'contact.html': net_contact()},
    }
    for s, pages in sites.items():
        os.makedirs(f'{out}/{s}/assets/fonts', exist_ok=True)
        used = set()
        for name, content in pages.items():
            with open(f'{out}/{s}/{name}', 'w', encoding='utf-8') as f:
                f.write(content)
            used |= {k for k in SHOTS if f'assets/{k}.jpg' in content}
        for target, source in ASSETS.items():
            shutil.copyfile(SOURCE / source, f'{out}/{s}/assets/{target}')
        if shots is not None:
            from PIL import Image  # only for --images: the captures are not in the repository
            for k in sorted(used):
                im = Image.open(f'{shots}/{SHOTS[k][0]}').convert('RGB'); im.thumbnail((1280, 800))
                im.save(f'{out}/{s}/assets/{k}.jpg', quality=80, optimize=True)
        print(s, len(pages), 'pages', len(used), 'images' + ('' if shots else ' (held, not remade)'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build ospreyflow.org and ospreyflow.net.')
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--images', type=Path, default=None, metavar='SHOTS')
    parser.add_argument('--changelog', type=Path, default=CHANGELOG, help='the CHANGELOG the release is read from')
    args = parser.parse_args()
    build(args.out, args.images, args.changelog)
