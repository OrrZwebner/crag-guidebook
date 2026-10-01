#!/usr/bin/env python3
"""
build_guide.py — render crag.json into the guide: a PDF (WeasyPrint) or, when
WeasyPrint is missing or broken, ONE self-contained HTML file to print from a browser.

Everything structural is generated: cover, contents with page numbers, sector pages,
coordinate tables, the shade-planning tables, the A–Z index. Everything editorial —
Important before you go, sources and method, how to read, the crag page, the
contradictions appendix — comes from front_pages / mid_pages / back_pages in the crag
file as HTML you wrote. Layout is mechanical; the prose is the actual work.

Usage
-----
  python3 scripts/build_guide.py --crag crag.json --out guide.pdf
  python3 scripts/build_guide.py --crag crag.json --out guide.pdf --force-html
  python3 scripts/build_guide.py --crag crag.json --out guide.pdf --html debug.html

--assets is the directory image paths in crag.json are relative to (default: the
folder holding crag.json).

Output: a JSON summary on stdout, e.g.
  {"ok": true, "renderer": "weasyprint", "pdf": "guide.pdf", "html": null, ...}
  {"ok": true, "renderer": "html", "pdf": null, "html": "guide.html",
   "next_step": "Open guide.html in a browser → Print → Save as PDF ..."}
Exit codes: 0 ok, 2 missing images or bad input.
"""

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guide_style as gs                                           # noqa: E402

DEFAULT_CSS = os.path.join(HERE, '..', 'assets', 'guide.css')

PRINT_STEPS = ('Open the HTML file in a browser (Chrome, Edge, Firefox or Safari) → '
               'choose Print → set the destination to "Save as PDF", paper A4, and turn '
               'on "Background graphics" → Save.')


def e(x):
    return html.escape(str(x)) if x is not None else ''


def log(*a):
    print(*a, file=sys.stderr)


# ------------------------------------------------------------------ route rows

def stars_html(route, meta):
    if gs.is_top_pick(route):
        return ('<span class="pick" title="%s">%s</span>'
                % (e(meta.get('top_pick_label') or gs.DEFAULT_TOP_PICK_LABEL),
                   e(meta.get('top_pick_symbol') or gs.DEFAULT_TOP_PICK_SYMBOL)))
    v = route.get('stars')
    if v is None:
        return '<span class="nost">—</span>'
    if v == 0:
        return '<span class="nost">0★</span>'
    return '<span class="st">%d★</span>' % int(v)


def field_by(meta):
    by, date = meta.get('field_notes_by'), meta.get('field_notes_date')
    return by, date


def route_row(r, meta):
    meta_bits = []
    if r.get('fa'):
        meta_bits.append(e(r['fa']))
    if r.get('bolts'):
        b = str(r['bolts'])
        meta_bits.append(e(b) + (' bolts' if b.isdigit() else ''))
    if r.get('type') == 'trad':
        meta_bits.append('<b>trad</b>')
    note = r.get('note') or ''
    hazard = any(k in note.upper() for k in gs.HAZARD_WORDS)
    length = r.get('length')
    local = ''
    if r.get('local_name'):
        dag = ('<span class="dag">†</span>'
               if gs.local_src(r) == 'reconstructed' else '')
        local = '<div class="rlocal">%s%s</div>' % (e(r['local_name']), dag)
    field = ''
    if r.get('field_note'):
        by, date = field_by(meta)
        who = ', '.join(x for x in (by, date) if x) or 'Field note'
        field = '<div class="rfield"><b>%s:</b> %s</div>' % (e(who), e(r['field_note']))
    return ('<div class="rtw"><div class="rt%s%s"><div class="rn">%s</div><div class="rb">'
            '<div class="rname">%s</div>%s%s%s%s%s</div>'
            '<div class="rs">%s</div><div class="rg">%s</div><div class="rl">%s</div></div></div>'
            % (' warnrt' if hazard else '', ' fieldrt' if field else '',
               e(r.get('n', '')), e(r['name']), local,
               ('<div class="rmeta">%s</div>' % ' · '.join(meta_bits)) if meta_bits else '',
               ('<div class="rnote">%s</div>' % e(note)) if note else '',
               ('<div class="rxref">%s</div>' % e(r['xref'])) if r.get('xref') else '',
               field, stars_html(r, meta), e(r.get('grade') or '—'),
               e(length) if length and length != '—' else '—'))


# ------------------------------------------------------------------ conditions

def conditions_sentence(s, meta):
    """The generated paragraph. Always carries gs.GENERATED_MARKER (mode C drops it)."""
    asp, deg = s.get('aspect'), s.get('aspect_deg')
    bank = s.get('bank', '')
    where = (' on the %s bank' % bank.lower()) if bank and bank != 'stated' else ''
    face = ('The wall faces <b>%s</b> (%s°)%s. ' % (e(asp), e(deg), where)) if asp else ''
    hedge = (' The aspect here is calculated rather than observed and is less certain '
             'than elsewhere in this guide.' if s.get('aspect_confidence') == 'low' else '')
    sunrise, sunset = gs.daylight(meta)
    w = s.get('sun')
    if not w:
        body = face + 'By calculation it stays <b>in shade all day</b>.'
    else:
        main, other = gs.shade_parts(w, sunrise, sunset)
        if main is None:
            body = face + ('By calculation it is in direct sun almost all day, about '
                           '<b>%s–%s</b>, so there is hardly any shade.' % tuple(w))
        else:
            body = face + ('By calculation it is <b>in shade %s</b>%s, and in direct sun '
                           'from about %s to %s.'
                           % (main, (' and <b>%s</b>' % other) if other else '', w[0], w[1]))
    cm = meta.get('conditions_meta') or {}
    if cm.get('sunrise'):
        body += (' Sunrise %s, sunset %s; the sun is highest at %s (%s°).'
                 % (cm['sunrise'], cm['sunset'], cm.get('solar_noon', '?'),
                    cm.get('max_elevation', '?')))
    return (body + ' <i>%s — treat it as approximate (see "Important before you go" at '
            'the front).</i>%s' % (gs.GENERATED_MARKER, hedge))


def sector_images(s):
    out = list(s.get('topos') or [])
    if s.get('topo'):
        out.insert(0, {'image': s['topo'], 'caption': s.get('topo_caption')})
    return out


def sector_html(s, meta, img):
    facts = [('GPS', '%.6f, %.6f' % (s['lat'], s['lon']))]
    if s.get('parking'):
        facts.append(('Parking / start', '%.6f, %.6f' % tuple(s['parking'][:2])))
    if s.get('asl'):
        facts.append(('Altitude', e(s['asl'])))
    if s.get('aspect'):
        flag = ' · calc., contradicted' if s.get('shade_override') else ''
        facts.append(('Aspect', '%s (%s°)%s%s' % (
            e(s['aspect']), e(s.get('aspect_deg', '?')),
            (' · %s bank' % e(s['bank'])) if s.get('bank') and s.get('bank') != 'stated' else '',
            flag)))
    facts_html = ''.join('<div><span>%s</span> %s</div>' % (k, v) for k, v in facts)

    head_bits = [e(gs.shade_headline(s, meta))]
    if s.get('routes_count'):
        head_bits.append('%s routes' % e(s['routes_count']))
    if s.get('grades'):
        head_bits.append(e(s['grades']))
    if s.get('height'):
        head_bits.append('up to %s' % e(s['height']))

    prose = ['<p class="lead">%s</p>' % e(s.get('intro', ''))]
    if s.get('field_notes'):
        by, date = field_by(meta)
        title = 'Field notes' + (' — %s' % by if by else '') + (', visit of %s' % date if date else '')
        prose.append('<div class="field"><div class="fieldh">%s</div>%s</div>'
                     % (e(title), ''.join('<p>%s</p>' % p for p in s['field_notes'])))
    if s.get('climbing'):
        prose.append('<h3>Climbing</h3><p>%s</p>' % e(s['climbing']))
    if s.get('shade_override'):
        prose.append('<h3>Conditions</h3><p>%s</p>' % s['shade_override']['sentence'])
        calc = dict(s)
        calc.pop('shade_override')
        prose.append('<p class="small">Calculation, contradicted by the observation above: %s. '
                     '%s.</p>' % (e(gs.shade_headline(calc, meta)), gs.GENERATED_MARKER))
    else:
        prose.append('<h3>Conditions</h3><p>%s</p>' % conditions_sentence(s, meta))
    if s.get('conditions_extra'):
        prose.append('<p>%s</p>' % e(s['conditions_extra']))
    if s.get('gear'):
        prose.append('<h3>Gear</h3><p>%s</p>' % e(s['gear']))
    if s.get('warn'):
        prose.append('<div class="warn"><div class="warnh">Warning</div>%s</div>' % e(s['warn']))
    if s.get('approach'):
        walk = (' <span class="wt">(Walking time: %s)</span>' % e(s['walk'])) if s.get('walk') else ''
        prose.append('<h3>Approach%s</h3><p>%s</p>' % (walk, e(s['approach'])))
    if s.get('busy'):
        prose.append('<h3>How busy</h3><p>%s</p>' % e(s['busy']))

    topo = ''.join(
        '<div class="topo%s"><img src="%s"><div class="cap">%s</div></div>'
        % (' photo' if t.get('photo') else '', img(t['image']),
           e(t.get('caption') or 'Topo — %s' % s['name']))
        for t in sector_images(s))

    sub = ' · '.join(x for x in (s.get('local_name'), s.get('en')) if x)
    return ('<section class="sector" id="s%s">'
            '<div class="shead"><div class="sbadge">%s</div>'
            '<div class="stitles"><div class="skicker">%s</div><h1>%s</h1>'
            '<div class="sgr">%s</div></div>'
            '<div class="sfacts">%s</div></div>'
            '<div class="shade"><b>%s</b> &nbsp;%s</div>'
            '<div class="prose">%s</div>'
            '<div class="rthead"><div class="rn"></div><div class="rb">Route</div>'
            '<div class="rs"></div><div class="rg">Grade</div><div class="rl">Len</div></div>'
            '<div class="rlist">%s</div>%s</section>'
            % (e(s.get('n', '')), e(s.get('n', '')), e(meta.get('name', '')), e(s['name']),
               e(sub), facts_html, e(gs.month_label(meta)),
               ' · '.join(head_bits), '\n'.join(prose),
               '\n'.join(route_row(r, meta) for r in s.get('routes', [])), topo))


# ------------------------------------------------------------------ contents

def rated(s):
    return [r.get('stars') for r in s.get('routes', [])
            if r.get('stars') is not None and not gs.is_top_pick(r)]


def contents_html(crag, html_mode):
    sectors = crag['sectors']
    meta = crag.get('crag', {})
    maxt = max([s.get('ticks') or 0 for s in sectors] + [0])
    rows = []
    for i, s in enumerate(sectors):
        st = rated(s)
        if st:
            avg = sum(st) / len(st)
            three = sum(1 for v in st if v == 3)
            rate = '<span class="st">%s</span> %.1f' % ('★' * max(int(round(avg)), 1), avg)
            if three:
                rate += '<div class="tgr">%d × ★★★</div>' % three
        else:
            rate = '<span class="tgr">unrated</span>'
        trad = sum(1 for r in s.get('routes', []) if r.get('type') == 'trad')
        total = len(s.get('routes', []))
        typ = 'Trad' if trad and trad == total else ('Sport + %d trad' % trad if trad else 'Sport')
        ticks = s.get('ticks') or 0
        if ticks and maxt:
            pop = ('<span class="bar" style="width:%.1fmm"></span>%s'
                   % (max(1.0, 26.0 * ticks / maxt), format(ticks, ',')))
        else:
            pop = '<span class="tgr">none logged</span>'
        shade = gs.shade_table(s, meta)
        if s.get('aspect_confidence') == 'low':
            shade += '<div class="tgr">aspect approximate</div>'
        sub = ' · '.join(x for x in (s.get('local_name'), s.get('en')) if x)
        link = ('§%s' % e(s.get('n', ''))) if html_mode else ''
        rows.append(
            '<tr class="%s"><td class="tn">%s</td>'
            '<td><span class="tname">%s</span><div class="tgr">%s</div></td>'
            '<td class="pg"><a href="#s%s">%s</a></td><td>%s</td>'
            '<td><b>%s</b><div class="tgr">%s · %s</div></td><td>%s</td>'
            '<td class="num">%s</td><td>%s</td><td class="sev%s">%s</td>'
            '<td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
            % ('alt' if i % 2 else '', e(s.get('n', '')), e(s['name']), e(sub),
               e(s.get('n', '')), link, shade, e(s.get('grades', '')), e(s.get('aspect', '')),
               e((s.get('asl') or '').replace(' – ', '–')), rate, pop,
               e(s.get('bolted', '—')), e(s.get('bolt_severity', 1)),
               e(s.get('bolt_status', '')), typ, e(s.get('height', '')), e(s.get('qd', ''))))

    legend = crag.get('pages_contents_legend') or (
        '<b>Shade</b> — when the wall is in the shade and comfortable to climb: the '
        'complement of the sun window calculated from the sector\'s aspect and the solar '
        'position, or a first-hand observation where one exists. Approximate: see "Important '
        'before you go".&nbsp; <b>Rating</b> — mean star rating across rated routes, with the '
        'count of three-star routes beneath.&nbsp; <b>Popularity</b> — logged ascents; the bar '
        'is relative to the busiest sector.&nbsp; <b>Bolt status</b> — <span class="sev3">red'
        '</span> where a source explicitly flags rebolting or bad bolting, <span class="sev2">'
        'amber</span> for run-outs, <span class="sev0">green</span> where hardware is new or '
        'maintained, grey where no source says anything. Grey is not a clean bill of health.'
        '&nbsp; <b>Max QDs</b> — the most quickdraws any single route in the sector needs.')
    page_head = 'Sector' if html_mode else 'Page'
    return ('<div class="landscape"><div class="phk">Contents</div>'
            '<h2 class="ph">%s</h2><div class="rule"></div>'
            '<table class="toc"><tr>'
            '<th>#</th><th style="width:38mm">Sector</th><th style="text-align:right">%s</th>'
            '<th style="width:27mm">Shade, %s</th><th style="width:26mm">Grades · aspect</th>'
            '<th style="width:20mm">Rating</th><th style="width:26mm;text-align:right">Popularity</th>'
            '<th style="width:34mm">Bolted</th><th style="width:40mm">Bolt status</th>'
            '<th style="width:22mm">Type</th><th style="text-align:right">Height</th>'
            '<th style="text-align:right">Max QDs</th></tr>%s</table>'
            '<div class="tlegend">%s</div></div>'
            % (e(crag.get('contents_title', 'The sectors at a glance')), page_head,
               e(gs.month_label(meta)), '\n'.join(rows), legend))


def coord_table(sectors, meta):
    rows = []
    for i, s in enumerate(sectors):
        park = ''
        if s.get('parking'):
            park = "<div class='small'>P %.6f, %.6f</div>" % tuple(s['parking'][:2])
        rows.append("<tr class='%s'><td><b>%s</b></td>"
                    "<td><b>%s</b><div class='small'>%s</div></td>"
                    "<td>%.6f<br>%.6f%s</td><td>%s</td>"
                    "<td>%s<br><span class='small'>%s°</span></td>"
                    "<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
                    % ('alt' if i % 2 else '', e(s.get('n', '')), e(s['name']),
                       e(s.get('local_name', '')), s['lat'], s['lon'], park,
                       e(s.get('asl', '')), e(s.get('aspect', '')), e(s.get('aspect_deg', '')),
                       gs.shade_short(s, meta), e(s.get('routes_count', '')),
                       e(s.get('grades', '')), e(s.get('ticks', ''))))
    return ('<table class="tbl"><tr><th>#</th><th>Sector</th><th>GPS (WGS84)</th>'
            '<th>Altitude</th><th>Aspect</th><th>Shade</th><th>Routes</th>'
            '<th>Grades</th><th>Ascents</th></tr>%s</table>' % '\n'.join(rows))


def map_pages(crag, img):
    out = []
    meta = crag.get('crag', {})
    for m in crag.get('maps', []):
        ids = m.get('sectors')
        subset = [s for s in crag['sectors'] if ids is None or s.get('n') in ids]
        out.append(
            '<div class="page"><div class="phk">%s</div><h2 class="ph">%s</h2>'
            '<div class="rule"></div>'
            '<table class="mapwrap"><tr><td class="mc1">'
            '<div class="mapimg"><img src="%s"></div>'
            '<div class="cap">%s</div></td><td>%s</td></tr></table>'
            '<div style="height:3mm"></div>%s</div>'
            % (e(m.get('kicker', 'Overview')), e(m.get('title', 'Overview')),
               img(m['image']), e(m.get('caption', '')), m.get('html', ''),
               coord_table(subset, meta)))
    return ''.join(out)


# ------------------------------------------------------------------ planning

def pick(s):
    best = ([r for r in s.get('routes', []) if gs.is_top_pick(r)] or
            sorted([r for r in s.get('routes', []) if r.get('stars') is not None],
                   key=lambda r: (-r['stars'], str(r.get('n')))))
    return ('%s %s' % (best[0]['name'].split(' / ')[0], best[0].get('grade', ''))) if best else '—'


def planning_html(crag):
    """Sectors grouped by morning vs afternoon shade; observed overrides last."""
    meta = crag.get('crag', {})
    sunrise, sunset = gs.daylight(meta)
    groups = {'before': [], 'after': [], 'all': [], 'none': []}
    for s in crag['sectors']:
        segs = gs.shade_segments(s.get('sun'), sunrise, sunset)
        groups[segs[0][0] if segs else 'none'].append(s)
    groups['before'].sort(key=lambda s: s['sun'][0], reverse=True)   # longest morning shade first
    groups['before'].sort(key=lambda s: bool(s.get('shade_override')))  # observed last (stable)
    groups['after'].sort(key=lambda s: (bool(s.get('shade_override')), s['sun'][1]))

    def table(items, head, col):
        rows = ''.join('<tr class="%s"><td><b>%s %s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>'
                       % ('alt' if i % 2 else '', e(s.get('n', '')), e(s['name']), col(s),
                          e(len(s.get('routes', []))), e(pick(s)))
                       for i, s in enumerate(items))
        return ('<table class="tbl"><tr><th>Sector</th><th>%s</th><th>Routes</th><th>Pick</th></tr>'
                '%s</table>' % (head, rows))

    def cell(s, calc):
        if s.get('shade_override'):
            return '%s <span class="small">(observed)</span>' % s['shade_override']['short']
        return calc

    out = ['<div class="two">']
    if groups['before']:
        out.append('<div class="box"><div class="boxh">Morning shade</div>'
                   '<p>In the shade from first light until the time shown.</p>%s</div>'
                   % table(groups['before'], 'Shade until', lambda s: cell(s, e(s['sun'][0]))))
    if groups['after']:
        out.append('<div class="box"><div class="boxh">Afternoon shade</div>'
                   '<p>In the shade from the time shown until sunset.</p>%s</div>'
                   % table(groups['after'], 'Shade from', lambda s: cell(s, e(s['sun'][1]))))
    if groups['all']:
        out.append('<div class="box"><div class="boxh">Shade all day</div>%s</div>'
                   % table(groups['all'], 'Shade', lambda s: cell(s, 'all day')))
    if groups['none']:
        out.append('<div class="box"><div class="boxh">Little or no shade</div>%s</div>'
                   % table(groups['none'], 'Sun', lambda s: cell(s, '%s–%s' % tuple(s['sun']))))
    if any(s.get('shade_override') for s in crag['sectors']):
        out.append('<p class="small">Sectors marked <i>observed</i> are placed last in their '
                   'group: a first-hand observation contradicted the calculation there.</p>')
    out.append('</div>')
    return ''.join(out)


# ------------------------------------------------------------------ pages

def approaches_box(meta):
    tips = meta.get('approach_tips') or []
    if not tips:
        return ''
    return ('<div class="appr"><div class="boxh">Approaches</div><ul>%s</ul></div>'
            % ''.join('<li>%s</li>' % t for t in tips))


def free_page(p, crag, extra=''):
    cls = 'landscape' if p.get('landscape') else 'page'
    body = p.get('html', '')
    if p.get('generate') == 'shade_planning':
        body = planning_html(crag) + body
    return ('<div class="%s"><div class="phk">%s</div><h2 class="ph">%s</h2>'
            '<div class="rule"></div>%s%s</div>'
            % (cls, e(p.get('kicker', '')), e(p.get('title', '')), body, extra))


def index_page(crag):
    items = []
    for s in crag['sectors']:
        for r in s.get('routes', []):
            items.append((r['name'].split(' / ')[0], r.get('grade', '—'), s.get('n', ''), s['name']))
    items.sort(key=lambda x: x[0].lower())
    half = (len(items) + 1) // 2

    def col(sub):
        return '\n'.join(
            "<div class='rt'><div class='rb'>"
            "<div class='rname' style='font-size:7.4pt'>%s</div>"
            "<div class='rmeta'>%s %s</div></div>"
            "<div class='rg' style='flex:0 0 11mm;font-size:7.4pt'>%s</div></div>"
            % (e(nm), e(sn), e(sname), e(g)) for nm, g, sn, sname in sub)

    return ("<div class='page'><div class='phk'>Index</div>"
            "<h2 class='ph'>All %d routes A–Z</h2><div class='rule'></div>"
            "<div class='two'>%s%s</div></div>" % (len(items), col(items[:half]), col(items[half:])))


def cover_html(crag, img):
    c = crag.get('cover', {})
    meta = crag.get('crag', {})
    im = ('<div class="cimg"><img src="%s"></div>' % img(c['image'])) if c.get('image') else ''
    return ('<div class="cover">%s<div class="cgrad"></div>'
            '<div class="ctag">%s</div><div class="ctxt"><h1>%s</h1>'
            '<div class="cyear">%s</div><div class="csub">%s</div></div></div>'
            % (im, e(c.get('tag', meta.get('country', ''))),
               c.get('title_html') or e('Mini guide: %s' % meta.get('name', '')),
               e(meta.get('year', '')), e(c.get('blurb', ''))))


def wanted_images(crag):
    w = []
    if crag.get('cover', {}).get('image'):
        w.append(crag['cover']['image'])
    w += [m['image'] for m in crag.get('maps', []) if m.get('image')]
    w += [t['image'] for s in crag['sectors'] for t in sector_images(s)]
    return w


def assemble(crag, css, img, html_mode):
    meta = crag.get('crag', {})
    parts = []
    if html_mode:
        parts.append('<div class="printhint"><b>To make the PDF:</b> %s</div>' % e(PRINT_STEPS))
    parts.append(cover_html(crag, img))
    if not crag.get('_no_contents'):
        parts.append(contents_html(crag, html_mode))
    fronts = crag.get('front_pages', [])
    box = approaches_box(meta)
    target = next((i for i, p in enumerate(fronts) if p.get('approaches')), len(fronts) - 1)
    for i, p in enumerate(fronts):
        parts.append(free_page(p, crag, box if (box and i == target) else ''))
    if box and not fronts:
        parts.append(free_page({'kicker': 'The crag', 'title': 'Approaches'}, crag, box))
    parts.append(map_pages(crag, img))
    for p in crag.get('mid_pages', []):
        parts.append(free_page(p, crag))
    for s in crag['sectors']:
        parts.append(sector_html(s, meta, img))
    for p in crag.get('back_pages', []):
        parts.append(free_page(p, crag))
    if not crag.get('_no_index'):
        parts.append(index_page(crag))
    return ('<!doctype html><html lang="en"%s><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><style>%s</style></head><body>%s</body></html>'
            % (' class="htmlmode"' if html_mode else '', e(meta.get('name', 'Crag guide')),
               css, ''.join(parts)))


def data_uri(path):
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    with open(path, 'rb') as f:
        return 'data:%s;base64,%s' % (mime, base64.b64encode(f.read()).decode('ascii'))


def count_pages(pdf):
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        return len(pymupdf.open(pdf))
    except Exception:                                              # noqa: BLE001
        pass
    try:
        info = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
        m = re.search(r'^Pages:\s+(\d+)', info, re.M)
        return int(m.group(1)) if m else None
    except Exception:                                              # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True, help='crag.json')
    ap.add_argument('--out', default='guide.pdf',
                    help='PDF path; the HTML fallback writes the same name with .html')
    ap.add_argument('--assets', default=None,
                    help='directory image paths are relative to (default: folder of --crag)')
    ap.add_argument('--css', default=None, help='house style (default: assets/guide.css)')
    ap.add_argument('--html', help='also write the intermediate (non-embedded) HTML here')
    ap.add_argument('--force-html', action='store_true',
                    help='skip WeasyPrint and write the self-contained HTML')
    ap.add_argument('--no-contents', action='store_true')
    ap.add_argument('--no-index', action='store_true')
    args = ap.parse_args()

    try:
        with open(args.crag, encoding='utf-8') as f:
            crag = json.load(f)
    except (OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': 'cannot read crag file: %s' % exc}))
        return 2
    crag['_no_contents'], crag['_no_index'] = args.no_contents, args.no_index
    base = os.path.abspath(args.assets or os.path.dirname(os.path.abspath(args.crag)))
    with open(args.css or DEFAULT_CSS, encoding='utf-8') as f:
        css = f.read() + '\n' + gs.key_css()

    # WeasyPrint drops images it cannot find without raising: refuse to build instead.
    wanted = wanted_images(crag)
    missing = [p for p in wanted if not os.path.exists(os.path.join(base, p))]
    if missing:
        print(json.dumps({'ok': False, 'error': 'missing image files (paths are relative '
                          'to --assets)', 'assets': base, 'missing': missing}, indent=1))
        return 2

    n_routes = sum(len(s.get('routes', [])) for s in crag['sectors'])
    result = {'ok': True, 'sectors': len(crag['sectors']), 'routes': n_routes,
              'images': len(wanted), 'pdf': None, 'html': None, 'pages': None}

    if args.html:
        doc_rel = assemble(crag, css, lambda p: e(p), False)
        with open(args.html, 'w', encoding='utf-8') as f:
            f.write(doc_rel)

    weasy_error = None
    if not args.force_html:
        try:
            from weasyprint import HTML                            # may raise OSError too
            doc = assemble(crag, css, lambda p: e(p), False)
            HTML(string=doc, base_url=base + os.sep).write_pdf(args.out)
            result.update(renderer='weasyprint', pdf=args.out, pages=count_pages(args.out),
                          size_mb=round(os.path.getsize(args.out) / 1e6, 2),
                          next_step='Open the PDF and look: contents page numbers, a dense '
                                    'sector, a sparse one, every topo the right way up. Then '
                                    'run verify_guide.py.')
        except Exception as exc:                                   # noqa: BLE001
            weasy_error = '%s: %s' % (type(exc).__name__, str(exc).splitlines()[0][:200]
                                      if str(exc) else '')
            log('WeasyPrint unavailable (%s); writing the self-contained HTML instead.'
                % weasy_error)

    if args.force_html or weasy_error:
        out_html = re.sub(r'\.pdf$', '', args.out, flags=re.I) + '.html'
        doc = assemble(crag, css, lambda p: data_uri(os.path.join(base, p)), True)
        with open(out_html, 'w', encoding='utf-8') as f:
            f.write(doc)
        result.update(renderer='html', html=out_html,
                      size_mb=round(os.path.getsize(out_html) / 1e6, 2),
                      weasyprint_error=weasy_error, print_steps=PRINT_STEPS,
                      next_step='Tell the user: ' + PRINT_STEPS + ' The contents shows '
                                'sector numbers instead of page numbers (browsers cannot '
                                'compute them).')
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
