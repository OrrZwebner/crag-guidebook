#!/usr/bin/env python3
"""
parse_guide_pdf.py — mode C: rebuild a crag.json draft from a guide PDF that THIS
skill rendered earlier (WeasyPrint + assets/guide.css), when the source file is lost.

It reads the PDF's text spans and recognises each element by font size, colour and
x-position — the style keys in guide_style.py (F6). It is therefore NOT for
third-party PDFs, and not for PDFs printed from a browser via the HTML fallback
(fonts and positions differ). If the PDF is not this skill's house style, stop and
rebuild the guide from sources (mode A), using the old PDF as one more source.

What it recovers
  sectors: number, name, local name / gloss, GPS, parking, altitude, aspect text,
           headline, prose (intro, climbing, gear, approach, walk, busy, warn,
           conditions_extra), field-notes box, observed shade override (flagged
           for review), topo/photo images with captions
  routes:  number, name, local name (+ † → reconstructed), grade, stars (null / 0 /
           n), top pick, length, first ascent, bolts, trad, note, xref, field note
  contents table: bolted, bolt status, bolt severity (from the text colour), type,
           height, max quickdraws, logged ascents
  --geo-csv (the CSV export_geo.py wrote for the same build): coordinates, parking,
           aspect, bank, confidence and the calculated sun window are joined in.

The generated conditions paragraph is dropped (it is regenerated on rebuild); later
conditions paragraphs are kept as conditions_extra.

Usage
-----
  python3 scripts/parse_guide_pdf.py --pdf old_guide.pdf --out rebuilt/crag.json
  python3 scripts/parse_guide_pdf.py --pdf old_guide.pdf --out rebuilt/crag.json \\
          --geo-csv old-sectors.csv --no-images

Prints a JSON report: per-sector route counts, identity I2 against the CSV,
fields that need review. Exit 0 ok, 1 count mismatch, 3 PyMuPDF missing.
"""

import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_style as gs                                           # noqa: E402

TOL = 6        # colour tolerance per channel: renderers round colours slightly


def near(c, key, tol=TOL):
    return all(abs(((c >> s) & 255) - ((key >> s) & 255)) <= tol for s in (16, 8, 0))


def szeq(a, b):
    return abs(a - b) < 0.15


def bold(sp):
    return 'bold' in sp['f'].lower()


def unspace(t):
    """'F I E L D  N O T E S' (letter-spaced) -> 'FIELD NOTES'."""
    t = t.strip()
    tokens = t.split(' ')
    if len(tokens) > 3 and sum(1 for x in tokens if len(x) <= 2) > 0.6 * len(tokens):
        return re.sub(r'\s+', ' ', re.sub(r'(?<=\S) (?=\S)', '', t))
    return t


def squash(t):
    return re.sub(r'\s+', '', t).upper()


def join(lines):
    """Join wrapped lines. The house style has no auto-hyphenation, so a line-end
    hyphen after a letter is a real hyphen: join without a space."""
    txt = ''
    for ln in lines:
        ln = ln.strip()
        if not txt:
            txt = ln
        elif re.search(r'[A-Za-z]-$', txt):
            txt += ln
        else:
            txt += ' ' + ln
    return re.sub(r'\s+([,.;:])', r'\1', txt)


def spans(page):
    out = []
    for b in page.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            for s in ln['spans']:
                if s['text'].strip():
                    out.append(dict(x=s['bbox'][0], y=s['bbox'][1], y1=s['bbox'][3],
                                    t=s['text'], f=s['font'], sz=round(s['size'], 1),
                                    c=s['color']))
    return out


def lines_of(sp):
    """Group spans into visual lines (same column, |dy| < 3)."""
    out = []
    for s in sorted(sp, key=lambda s: (round(s['y']), s['x'])):
        if out and abs(out[-1]['y'] - s['y']) < 3:
            out[-1]['parts'].append(s)
        else:
            out.append(dict(y=s['y'], parts=[s]))
    for ln in out:
        ln['parts'].sort(key=lambda s: s['x'])
        ln['y'] = ln['parts'][0]['y']      # leftmost span: fallback-font glyphs sit higher
        ln['t'] = ''.join(p['t'] for p in ln['parts'])
    return out


def is_sector_start(sp):
    badge = [s for s in sp if szeq(s['sz'], gs.SZ_SECTOR_NO) and near(s['c'], gs.WHITE)
             and s['t'].strip().isdigit() and s['y'] < 120]
    title = [s for s in sp if szeq(s['sz'], gs.SZ_TITLE) and bold(s) and s['y'] < 120]
    return (int(badge[0]['t']), title) if badge and title else (None, None)


def is_free_page(sp):
    return any(szeq(s['sz'], 19.0) and bold(s) and s['y'] < 90 for s in sp)


# ------------------------------------------------------------------ prose

def classify(ln, section):
    p0 = ln['parts'][0]
    if szeq(p0['sz'], gs.SZ_H3) and bold(p0):
        return 'head'
    if near(p0['c'], gs.STAR) and squash(p0['t']).startswith('WARN'):
        return 'warnhead'
    if near(p0['c'], gs.PICK) and squash(p0['t']).startswith('FIELDNOTES'):
        return 'fieldhead'
    if szeq(p0['sz'], gs.SZ_LEAD):
        return 'lead'
    if szeq(p0['sz'], gs.SZ_WARN):
        return 'field' if section == 'field_notes' else 'warn'
    return 'text'


HEADS = (('Climbing', 'climbing'), ('Conditions', 'conditions'), ('Gear', 'gear'),
         ('Approach', 'approach'), ('How busy', 'busy'))


def prose_fields(lines):
    """Sort prose lines into fields. Lines come column by column, top to bottom."""
    fields, paras = {}, {}
    section, last_y, last_kind = 'intro', None, None
    for ln in lines:
        p0 = ln['parts'][0]
        if (last_kind == 'fieldhead' and near(p0['c'], gs.PICK) and bold(p0)
                and szeq(p0['sz'], 6.8)):
            # the letter-spaced field-notes header wrapped (font metrics differ by
            # platform): the next header-styled line continues it, not the intro
            fields['_field_header'] = unspace(fields.get('_field_header', '') + ' ' + ln['t'])
            last_y = ln['y']
            continue
        k = classify(ln, section)
        if k == 'head':
            m = [v for h, v in HEADS if ln['t'].strip().startswith(h)]
            section = m[0] if m else 'text'
            wm = re.search(r'\(Walking time: ([^)]*)\)', ln['t'])
            if wm:
                fields['walk'] = wm.group(1)
            last_y, last_kind = ln['y'], k
            continue
        if k in ('warnhead', 'fieldhead'):
            section = 'warn' if k == 'warnhead' else 'field_notes'
            if k == 'fieldhead':
                fields['_field_header'] = unspace(ln['t'])
            last_y, last_kind = ln['y'], k
            continue
        sec = 'intro' if k == 'lead' else ('warn' if k == 'warn' else section)
        if k == 'field':
            sec = 'field_notes'
        elif section == 'field_notes' and k != 'field':
            section = 'intro'                    # box ended; body text resumes
            sec = section if k != 'lead' else 'intro'
        gap = (ln['y'] - last_y) if last_y is not None else 0
        new = (not paras.get(sec) or gap > 13.5 or gap < -5 or last_kind in
               ('head', 'warnhead', 'fieldhead') or (sec == 'field_notes' and gap > 12))
        if gap < -5 and paras.get(sec) and not re.search(r'[.!?:")”]$',
                                                         paras[sec][-1][-1].strip()):
            new = False                          # column jump mid-sentence continues
        paras.setdefault(sec, [])
        if new:
            paras[sec].append([])
        paras[sec][-1].append(ln['t'])
        last_y, last_kind = ln['y'], k
    P = {k: [join(p) for p in v if p] for k, v in paras.items()}
    if P.get('intro'):
        fields['intro'] = ' '.join(P['intro'])
    for k in ('climbing', 'gear', 'approach', 'busy', 'warn'):
        if P.get(k):
            fields[k] = '\n\n'.join(P[k])
    if P.get('field_notes'):
        fields['field_notes'] = P['field_notes']
    cond = [p for p in P.get('conditions', [])]
    fields['_conditions'] = cond
    return fields


# ------------------------------------------------------------------ routes

def route_spans(zone, cur):
    for colsel, x0 in ((lambda s: s['x'] < gs.COLUMN_SPLIT_X, gs.COLUMN_ORIGINS[0]),
                       (lambda s: s['x'] >= gs.COLUMN_SPLIT_X, gs.COLUMN_ORIGINS[1])):
        col = [s for s in zone if colsel(s)]
        # Badges sit ~2 pt lower than the route name: order them 5 pt earlier, or
        # every badge attaches to the previous route (off-by-one).
        items = [(s['y'] - 5, 0, [s]) for s in col if is_badge(s)]
        items += [(ln['y'], 1, ln['parts']) for ln in lines_of([s for s in col if not is_badge(s)])]
        for _, _, parts in sorted(items, key=lambda i: (i[0], i[1])):
            for s in parts:
                route_span(s, s['x'] - x0, cur)


def route_span(s, rel, cur):
    t = s['t'].strip()
    if is_badge(s):
        cur['routes'].append(dict(n=t, name='', meta=[], note=[], xref=[], field=[],
                                  local=[], stars=None, grade=None, length=None))
        return
    if not cur['routes']:
        return
    r = cur['routes'][-1]
    if near(s['c'], gs.INK) and bold(s) and szeq(s['sz'], gs.SZ_NAME):
        if rel > gs.GRADE_MIN_OFFSET:
            r['grade'] = ((r['grade'] + ' ') if r['grade'] else '') + t
        else:
            r['name'] = (r['name'] + ' ' + t).strip()
    elif near(s['c'], gs.META, 3):
        r['meta'].append(t if not bold(s) else '<b>%s</b>' % t)
    elif near(s['c'], gs.NOTE):
        r['note'].append(t)
    elif near(s['c'], gs.XREF):
        r['xref'].append(t)
    elif near(s['c'], gs.FIELD):
        r['field'].append((t, bold(s)))
    elif near(s['c'], gs.DAGGER, 3) and t == '†':
        r['dagger'] = True
    elif near(s['c'], gs.LOCAL, 3) and szeq(s['sz'], gs.SZ_LOCAL):
        r['local'].append(t)
    elif near(s['c'], gs.PICK):
        r['top_pick'] = True
    elif near(s['c'], gs.STAR):
        m = re.match(r'(\d+)', t)
        if m:
            r['stars'] = int(m.group(1))
    elif near(s['c'], gs.NOSTAR, 3):
        if t.startswith('0'):
            r['stars'] = 0                   # "0★": rated zero
        elif t.startswith('\u2014'):
            r['stars'] = None                # "—": unrated
    elif near(s['c'], gs.LENGTH, 3):
        r['length'] = t


def is_badge(s):
    return near(s['c'], gs.WHITE) and szeq(s['sz'], gs.SZ_BADGE)


def finish_route(r, report):
    out = dict(n=int(r['n']) if r['n'].isdigit() else r['n'], name=r['name'],
               grade=r['grade'], stars=r['stars'], length=r['length'])
    meta = join(r['meta'])
    if '<b>trad</b>' in meta:
        out['type'] = 'trad'
        meta = re.sub(r'\s*·?\s*<b>trad</b>', '', meta)
    mb = re.search(r'(?:^|·\s*)(\d+) bolts$', meta)
    if mb:
        out['bolts'] = int(mb.group(1))
        meta = re.sub(r'\s*·?\s*\d+ bolts$', '', meta)
    if meta.strip(' ·'):
        out['fa'] = meta.strip(' ·')
    if r['note']:
        out['note'] = join(r['note'])
    if r['xref']:
        out['xref'] = join(r['xref'])
    if r['local']:
        out['local_name'] = join(r['local']).rstrip('†').strip()
        out['local_src'] = 'reconstructed' if r.get('dagger') else 'source'
    if r.get('top_pick'):
        out['rating'] = 'top_pick'
    if r['field']:
        head = ''.join(t for t, b in r['field'] if b)
        body = join([t for t, b in r['field'] if not b])
        out['field_note'] = body
        m = re.match(r'(.*), ([^,]+):$', head.strip())
        if m:
            report.setdefault('field_by', (m.group(1), m.group(2)))
    return out


def drop_generated(paras):
    """Drop the generated conditions paragraph(s): from one starting 'The wall faces' /
    'By calculation' through the one carrying GENERATED_MARKER, plus any paragraph
    that carries the marker itself. Everything else is kept (conditions_extra)."""
    keep, skipping = [], False
    for p in paras:
        if p.startswith(('The wall faces', 'By calculation it')) and not skipping:
            skipping = True
        if skipping or gs.GENERATED_MARKER in p:
            if gs.GENERATED_MARKER in p:
                skipping = False
            continue
        keep.append(p)
    return keep


# ------------------------------------------------------------------ contents

HEADER_KEYS = {'POPULARITY': 'ticks', 'BOLTED': 'bolted', 'BOLTSTATUS': 'bolt_status',
               'TYPE': 'type', 'HEIGHT': 'height', 'QDS': 'qd', 'MAXQDS': 'qd',
               'PAGE': 'page', 'SECTOR': 'sector_col'}


def parse_contents(doc):
    rows = {}
    for pno in range(min(len(doc), 4)):
        sp = spans(doc[pno])
        heads = [s for s in sp if szeq(s['sz'], 6.0) and bold(s)]
        if not any(re.sub(r'\s', '', s['t']).upper() == 'BOLTSTATUS' for s in heads):
            continue
        cols = sorted({round(s['x']): re.sub(r'[\s·]', '', s['t']).upper() for s in heads}.items())
        bands = []
        for i, (x, name) in enumerate(cols):
            x2 = cols[i + 1][0] if i + 1 < len(cols) else 10000
            bands.append((x - 3, x2 - 3, HEADER_KEYS.get(name)))
        hy = max(s['y'] for s in heads)
        anchors = sorted((s['y'], int(s['t'])) for s in sp
                         if s['t'].strip().isdigit() and bold(s) and s['x'] < 45 and s['y'] > hy + 5
                         and szeq(s['sz'], 8.0))
        for i, (y, n) in enumerate(anchors):
            y2 = anchors[i + 1][0] if i + 1 < len(anchors) else y + 40
            row = [s for s in sp if y - 3 <= s['y'] < y2 - 3]
            rec = {}
            for a, b, key in bands:
                if not key:
                    continue
                cell = [s for s in row if a <= s['x'] < b]
                if key == 'bolt_status' and cell:
                    rec['bolt_severity'] = next((v for c, v in gs.SEVERITY_BY_COLOUR.items()
                                                 if near(cell[0]['c'], c)), 1)
                rec[key] = ' '.join(s['t'].strip() for s in sorted(cell, key=lambda s: (round(s['y']), s['x'])))
            if rec.get('ticks') in ('none logged', ''):
                rec['ticks'] = 0
            elif rec.get('ticks'):
                rec['ticks'] = int(re.sub(r'\D', '', rec['ticks']) or 0)
            rows[n] = rec
    return rows


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--pdf', required=True, help='a guide PDF rendered by this skill')
    ap.add_argument('--out', required=True, help='crag.json draft to write')
    ap.add_argument('--geo-csv', help='the *-sectors.csv from the same build')
    ap.add_argument('--no-images', action='store_true', help='do not extract topo images')
    args = ap.parse_args()

    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
    except Exception as exc:                                       # noqa: BLE001
        print(json.dumps({'ok': False, 'missing': 'PyMuPDF', 'error': str(exc),
                          'degraded': 'Mode C cannot run. Ask the user whether to install '
                                      'PyMuPDF, or rebuild the guide from sources (mode A).'}))
        return 3

    doc = pymupdf.open(args.pdf)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    report = {'review': []}
    sectors, cur, month = [], None, None
    zone = []

    for pno in range(len(doc)):
        page = doc[pno]
        sp = spans(page)
        if not sp:
            continue
        n, title = is_sector_start(sp)
        if n is not None:
            cur = dict(n=n, name=' '.join(s['t'].strip() for s in title), routes=[],
                       pages=[pno + 1], captions=[], images=[])
            sectors.append(cur)
            sub = [s for s in sp if szeq(s['sz'], 9.6) and s['y'] < 120]
            subt = ' '.join(s['t'].strip() for s in sub)
            if subt:
                bits = subt.split(' · ')
                cur['local_name'] = bits[0]
                if len(bits) > 1:
                    cur['en'] = bits[1]
            head_rows = lines_of([s for s in sp if szeq(s['sz'], gs.SZ_HEADLINE) and s['y'] < 200])
            hl = next((r for r in head_rows if 'Shade' in r['t']), None)
            hy = hl['y'] if hl else 100
            if hl:
                month = month or hl['parts'][0]['t'].strip()
                cur['_headline'] = re.sub(r'\s+', ' ', hl['t'][len(hl['parts'][0]['t']):]).strip()
            facts = ' '.join(l['t'] for l in lines_of([s for s in sp if s['x'] > gs.COLUMN_SPLIT_X
                                                       and s['y'] < hy - 2]))
            for key, rx in (('gps', r'GPS\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)'),
                            ('parking', r'PARKING / START\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)')):
                m = re.search(rx, facts)
                if m:
                    v = [float(m.group(1)), float(m.group(2))]
                    if key == 'gps':
                        cur['lat'], cur['lon'] = v
                    else:
                        cur['parking'] = v
            m = re.search(r'ALTITUDE\s*(.*?)(?=\s+ASPECT|$)', facts)
            if m:
                cur['asl'] = m.group(1).strip()
            rhead = [s for s in sp if s['t'].strip() == 'ROUTE']
            ry = rhead[0]['y'] if rhead else 9999
            pz = [s for s in sp if hy + 12 < s['y'] < ry - 5]
            plines = []
            for col in (lambda s: s['x'] < gs.COLUMN_SPLIT_X, lambda s: s['x'] >= gs.COLUMN_SPLIT_X):
                plines += lines_of([s for s in pz if col(s)])
            cur['_prose'] = plines
            stop = [s['y'] for s in sp if squash(s['t']).startswith(gs.APPENDIX_MARKER)]
            zone = [s for s in sp if ry + 10 < s['y'] < (stop[0] - 5 if stop else 810)]
        elif cur is not None and not is_free_page(sp):
            has_badge = any(is_badge(s) for s in sp)
            has_img = bool(page.get_image_info())
            if not has_badge and not has_img:
                cur = None
                continue
            cur['pages'].append(pno + 1)
            zone = [s for s in sp if 30 < s['y'] < 810]
        else:
            cur = None
            continue
        caps = [s for s in zone if s['y'] > 0 and szeq(s['sz'], 6.6) and near(s['c'], 0x8a8a8a, 4)]
        for ln in lines_of(caps):
            cur['captions'].append(ln['t'].strip())
        zone = [s for s in zone if s not in caps and not (s['y'] > 800 and near(s['c'], 0x888888, 4))]
        route_spans(zone, cur)
        if not args.no_images:
            for info in page.get_image_info(xrefs=True):     # per page, not the shared list
                if info.get('xref') and info['bbox'][2] - info['bbox'][0] > 40:
                    cur['images'].append(info['xref'])

    geo = {}
    if args.geo_csv:
        with open(args.geo_csv, encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('n', '').isdigit():
                    geo[int(row['n'])] = row

    contents = parse_contents(doc)
    out_sectors, counts, mismatches = [], {}, []
    for s in sectors:
        f = prose_fields(s.pop('_prose'))
        sec = {k: v for k, v in s.items() if k in ('n', 'name', 'local_name', 'en', 'lat',
                                                   'lon', 'parking', 'asl')}
        sec.update({k: v for k, v in f.items() if not k.startswith('_')})
        cond = f.get('_conditions', [])
        headline = s.get('_headline', '')
        generated = re.match(r'^Shade (\(climbable\)|all day|: hardly any)', headline)
        keep = drop_generated(cond)
        if headline and not generated:
            shade_head = re.split(r' · \d+ routes', headline)[0]
            sec['shade_override'] = dict(headline=shade_head,
                                         sentence=keep[0] if keep else '',
                                         table=shade_head, short=shade_head)
            keep = keep[1:]
            report['review'].append('Sector %s: observed shade override recovered from the '
                                    'headline; rewrite its "table" and "short" cells.' % s['n'])
        if keep:
            sec['conditions_extra'] = '\n\n'.join(keep)
        sec.update({k: v for k, v in contents.get(s['n'], {}).items()
                    if k not in ('page', 'sector_col')})
        g = geo.get(s['n'])
        if g:
            for key, col, conv in (('lat', 'lat', float), ('lon', 'lon', float),
                                   ('aspect', 'aspect', str), ('bank', 'bank', str),
                                   ('aspect_confidence', 'aspect_confidence', str)):
                if g.get(col):
                    sec[key] = conv(g[col])
            if g.get('aspect_deg'):
                sec['aspect_deg'] = int(float(g['aspect_deg']))
            if g.get('parking_lat'):
                sec['parking'] = [float(g['parking_lat']), float(g['parking_lon'])]
            if g.get('calc_sun_from'):
                sec['sun'] = [g['calc_sun_from'], g['calc_sun_to']]
            elif 'calc_sun_from' in g:
                sec['sun'] = None
            if g.get('routes', '').isdigit():
                sec['routes_count'] = int(g['routes'])
        sec['routes'] = [finish_route(r, report) for r in s['routes']]
        for r in sec['routes']:
            if r.get('rating') == 'top_pick':
                report['review'].append('Sector %s route %s is a top pick: its spine stars are '
                                        'not printed; take them from the field note or the '
                                        'spine source.' % (s['n'], r['n']))
        # images
        topos = []
        if s['images']:
            os.makedirs(os.path.join(out_dir, 'topo'), exist_ok=True)
        for i, xref in enumerate(s['images']):
            try:
                img = doc.extract_image(xref)
            except Exception:                                      # noqa: BLE001
                continue
            name = os.path.join('topo', 'pdf_%02d%s.%s' % (s['n'], 'abcdefghij'[i % 10], img['ext']))
            with open(os.path.join(out_dir, name), 'wb') as fh:
                fh.write(img['image'])
            cap = s['captions'][i] if i < len(s['captions']) else 'Topo — %s' % s['name']
            t = {'image': name, 'caption': cap}
            if ' photo ' in cap.lower() or cap.lower().startswith('photo'):
                t['photo'] = True
            topos.append(t)
        if topos:
            sec['topos'] = topos
        n_parsed = len(sec['routes'])
        counts[s['n']] = n_parsed
        if g:
            want = g.get('routes_listed') or g.get('routes')
            if want and want.isdigit() and int(want) != n_parsed:
                mismatches.append({'sector': s['n'], 'parsed': n_parsed, 'csv': int(want)})
        out_sectors.append(sec)

    meta = {'name': None, 'month_label': month}
    if 'field_by' in report:
        meta['field_notes_by'], meta['field_notes_date'] = report.pop('field_by')
    if doc and len(doc):
        big = [s for s in spans(doc[0]) if s['sz'] >= 30]
        meta['name'] = re.sub(r'^Mini guide:\s*', '', ' '.join(s['t'].strip() for s in big)) or None
        report['review'].append('crag.name was taken from the cover title ("%s"); correct it.'
                                % meta['name'])
    crag = {'_rebuilt_from': os.path.basename(args.pdf), 'crag': meta,
            'front_pages': [], 'maps': [], 'mid_pages': [], 'back_pages': [],
            'sectors': out_sectors}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(crag, f, ensure_ascii=False, indent=1)

    if not args.geo_csv:
        report['review'].append('No --geo-csv: sun windows are missing. Rerun '
                                'crag_conditions.py (mode A step) before rebuilding.')
    report['review'].append('Editorial pages (front/mid/back) are not recovered: copy them '
                            'from the old PDF text or rewrite them.')
    ok = not mismatches
    print(json.dumps({'ok': ok, 'written': args.out, 'sectors': len(out_sectors),
                      'routes': sum(counts.values()), 'routes_per_sector': counts,
                      'I2_mismatches': mismatches,
                      'images_extracted': sum(len(s.get('topos', [])) for s in out_sectors),
                      'review': report['review']}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
