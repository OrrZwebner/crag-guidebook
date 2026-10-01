#!/usr/bin/env python3
"""
verify_guide.py — check a built guide (PDF or the HTML fallback) against its crag.json.

Checks (each reported as pass/fail with detail):
  no_sun_headlines       no "Sun HH:MM–HH:MM" anywhere: conditions are printed as shade
  headlines_say_shade    every sector's headline is printed and contains "Shade"
  contents_shade_column  the contents column is headed "Shade, <month>", not "Sun"
  I1_route_total         routes in crag.json = crag.spine_total (or Σ routes_count)
  I2_baseline_counts     per-sector route counts = --baseline (a previous crag.json)
  I3_shade_complement    sun window inside daylight and |shade| + |sun| = |daylight|
  I4_local_names         sourced + reconstructed + blank = total; every name printed;
                         a † printed for every reconstructed name
  I5_images              image placements >= topos + cover + maps
  I6_field_notes         field-notes boxes appear in exactly the sectors that have them
  I7_coordinates         every sector within --max-km of the median position
  I8_contents_pages      (PDF only) each contents page number = the sector's real page
  overrides_printed      every shade_override headline appears in its sector
  parking_printed        every parking coordinate is printed
  approaches_box         an Approaches box is printed iff crag.approach_tips exist
  top_pick               the top-pick symbol is printed iff a route has rating top_pick
  important_first        the first front page is "Important before you go" and printed
  html_self_contained    (HTML only) no external src/href; every <img> is a data: URI

Usage
-----
  python3 scripts/verify_guide.py --guide guide.pdf --crag crag.json
  python3 scripts/verify_guide.py --guide guide.html --crag crag.json --baseline old/crag.json

Prints {"checks": [{"name", "pass", "detail"}], "all_pass": bool}; exit 0 if all pass,
1 otherwise, 3 if a PDF cannot be read (PyMuPDF missing and no pdftotext).
"""

import argparse
import html as htmllib
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_style as gs                                           # noqa: E402


def flat(t):
    return re.sub(r'\s+', ' ', t).strip()


def squash(t):
    return re.sub(r'\s+', '', t).upper()


def near(c, key, tol=6):
    return all(abs(((c >> s) & 255) - ((key >> s) & 255)) <= tol for s in (16, 8, 0))


# ------------------------------------------------------------------ readers

def read_pdf(path):
    """-> (pages_text, sector_page_index {n: page_idx}, image_count, contents_pages {n: printed})"""
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
    except Exception:                                              # noqa: BLE001
        pymupdf = None
    if pymupdf is None:
        try:
            txt = subprocess.run(['pdftotext', path, '-'], capture_output=True, text=True,
                                 check=True).stdout
        except Exception:                                          # noqa: BLE001
            return None
        return txt.split('\f'), {}, None, {}
    doc = pymupdf.open(path)
    pages, starts, images, contents = [], {}, 0, {}
    for i, page in enumerate(doc):
        pages.append(page.get_text())
        images += len(page.get_image_info())
        d = page.get_text('dict')
        sp = [s for b in d['blocks'] for ln in b.get('lines', []) for s in ln['spans']
              if s['text'].strip()]
        badge = [s for s in sp if abs(s['size'] - gs.SZ_SECTOR_NO) < 0.15
                 and near(s['color'], gs.WHITE) and s['text'].strip().isdigit()
                 and s['bbox'][1] < 120]
        if badge:
            starts[int(badge[0]['text'])] = i
        heads = {squash(s['text']): s['bbox'][0] for s in sp
                 if abs(s['size'] - 6.0) < 0.15 and 'bold' in s['font'].lower()}
        if 'PAGE' in heads and 'BOLTSTATUS' in heads:
            x0 = heads['PAGE'] - 15
            x1 = min([x for x in heads.values() if x > heads['PAGE']] + [x0 + 60]) - 2
            hy = max(s['bbox'][1] for s in sp if squash(s['text']) == 'PAGE')
            rows = sorted((s['bbox'][1], int(s['text'])) for s in sp
                          if s['text'].strip().isdigit() and s['bbox'][0] < 45
                          and s['bbox'][1] > hy + 5 and abs(s['size'] - 8.0) < 0.15)
            for y, n in rows:
                cell = [s['text'].strip() for s in sp if abs(s['bbox'][1] - y) < 4
                        and x0 <= s['bbox'][0] < x1 and s['text'].strip().isdigit()]
                if cell:
                    contents[n] = int(cell[0])
    return pages, starts, images, contents


def read_html(path):
    with open(path, encoding='utf-8') as f:
        raw = f.read()
    body = re.sub(r'<style.*?</style>', '', raw, flags=re.S)
    chunks = re.split(r'(?=<section class="sector"|<div class="(?:page|landscape|cover)")', body)
    pages = [htmllib.unescape(re.sub(r'<[^>]+>', ' ', c)) for c in chunks]
    starts = {}
    for i, c in enumerate(chunks):
        m = re.match(r'<section class="sector" id="s(\d+)"', c)
        if m:
            starts[int(m.group(1))] = i
    images = len(re.findall(r'<img\b', body))
    return pages, starts, images, raw


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--guide', required=True, help='the built guide: .pdf or .html')
    ap.add_argument('--crag', required=True)
    ap.add_argument('--baseline', help='previous crag.json (e.g. parsed from the old PDF)')
    ap.add_argument('--max-km', type=float, default=10.0,
                    help='coordinate plausibility radius around the median (assumption)')
    args = ap.parse_args()

    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    meta = crag.get('crag', {})
    sectors = crag['sectors']
    is_html = args.guide.lower().endswith(('.html', '.htm'))
    raw = None
    if is_html:
        pages, starts, images, raw = read_html(args.guide)
        contents = {}
    else:
        got = read_pdf(args.guide)
        if got is None:
            print(json.dumps({'ok': False, 'missing': 'PyMuPDF or pdftotext',
                              'degraded': 'Cannot read the PDF text; look at it by eye.'}))
            return 3
        pages, starts, images, contents = got
    text = '\n'.join(pages)
    ftext = flat(text)
    checks = []

    def check(name, cond, detail=''):
        checks.append({'name': name, 'pass': bool(cond), 'detail': detail})

    # sector segments: from the sector's first page up to the next sector / free page
    order = sorted(starts.items(), key=lambda kv: kv[1])
    seg = {}
    for i, (n, p) in enumerate(order):
        end = order[i + 1][1] if i + 1 < len(order) else len(pages)
        seg[n] = flat(' '.join(pages[p:end]))

    # 1-3 shade wording
    bad = re.findall(r'Sun \d\d:\d\d\s*[–-]\s*\d\d:\d\d', text)
    check('no_sun_headlines', not bad, '%d found' % len(bad))
    missing = [s['n'] for s in sectors
               if 'Shade' not in gs.shade_headline(s, meta)
               or flat(gs.shade_headline(s, meta)) not in seg.get(s['n'], ftext)]
    check('headlines_say_shade', not missing and len(seg) == len(sectors),
          'missing in sectors %s; %d/%d sector pages found' % (missing, len(seg), len(sectors)))
    month = gs.month_label(meta)
    sq = squash(text)
    check('contents_shade_column', ('SHADE,' + squash(month)) in sq and 'SUN,' + squash(month) not in sq,
          'expects "Shade, %s"' % month)

    # I1
    total = sum(len(s.get('routes', [])) for s in sectors)
    spine = meta.get('spine_total')
    if spine is None and all(s.get('routes_count') is not None for s in sectors):
        spine = sum(int(s['routes_count']) for s in sectors)
    check('I1_route_total', spine is None or total == int(spine),
          '%d routes; spine claims %s' % (total, spine))

    # I2
    if args.baseline:
        with open(args.baseline, encoding='utf-8') as f:
            base = json.load(f)
        bc = {s['n']: len(s.get('routes', [])) for s in base['sectors']}
        cc = {s['n']: len(s.get('routes', [])) for s in sectors}
        diff = {n: (bc.get(n), cc.get(n)) for n in set(bc) | set(cc) if bc.get(n) != cc.get(n)}
        check('I2_baseline_counts', not diff, 'differences (baseline, now): %s' % diff)

    # I3
    sunrise, sunset = gs.daylight(meta)
    D = gs.to_min(sunset) - gs.to_min(sunrise)
    bad3 = []
    for s in sectors:
        w = s.get('sun')
        if not w:
            continue
        a, b = gs.to_min(w[0]), gs.to_min(w[1])
        shade = (a - gs.to_min(sunrise)) + (gs.to_min(sunset) - b)
        if not (gs.to_min(sunrise) <= a <= b <= gs.to_min(sunset)) or shade + (b - a) != D:
            bad3.append(s['n'])
    check('I3_shade_complement', not bad3, 'daylight %s–%s (%d min); bad sectors %s'
          % (sunrise, sunset, D, bad3))

    # I4
    tally = {'source': 0, 'reconstructed': 0, 'blank': 0}
    unprinted = []
    for s in sectors:
        for r in s.get('routes', []):
            if not r.get('local_name'):
                tally['blank'] += 1
                continue
            src = gs.local_src(r)
            tally['reconstructed' if src == 'reconstructed' else 'source'] += 1
            if flat(r['local_name']) not in ftext:
                unprinted.append(r['local_name'])
    daggers = text.count('†')
    check('I4_local_names', sum(tally.values()) == total and not unprinted
          and daggers >= tally['reconstructed'],
          'tally %s; unprinted %s; † printed %d' % (tally, unprinted, daggers))

    # I5
    wanted = (sum(len(s.get('topos') or []) + (1 if s.get('topo') else 0) for s in sectors)
              + (1 if crag.get('cover', {}).get('image') else 0) + len(crag.get('maps', [])))
    check('I5_images', images is None or images >= wanted,
          '%s placements, %d wanted' % (images, wanted))

    # I6
    want6 = sorted(s['n'] for s in sectors if s.get('field_notes'))
    got6 = sorted(n for n, t in seg.items() if 'FIELDNOTES' in squash(t))
    check('I6_field_notes', want6 == got6, 'expected %s, found %s' % (want6, got6))

    # I7
    lats = sorted(s['lat'] for s in sectors)
    lons = sorted(s['lon'] for s in sectors)
    mlat, mlon = lats[len(lats) // 2], lons[len(lons) // 2]
    far = []
    for s in sectors:
        dy = (s['lat'] - mlat) * 111.132
        dx = (s['lon'] - mlon) * 111.320 * math.cos(math.radians(mlat))
        if math.hypot(dx, dy) > args.max_km:
            far.append(s['n'])
    check('I7_coordinates', not far, 'outside %.0f km: %s' % (args.max_km, far))

    # I8
    if not is_html and contents:
        wrong = {n: (contents.get(n), starts.get(n, -2) + 1) for n in starts
                 if contents.get(n) != starts[n] + 1}
        check('I8_contents_pages', not wrong, 'wrong (printed, actual): %s' % wrong)
    elif not is_html:
        check('I8_contents_pages', False, 'could not read the contents page numbers')

    # overrides, parking
    ov = [s['n'] for s in sectors if s.get('shade_override')
          and flat(gs.strip_tags(s['shade_override']['headline'])) not in seg.get(s['n'], '')]
    check('overrides_printed', not ov, 'missing in %s' % ov)
    pk = [s['n'] for s in sectors if s.get('parking')
          and ('%.6f, %.6f' % tuple(s['parking'][:2])) not in ftext]
    check('parking_printed', not pk, 'missing for %s' % pk)

    tips = meta.get('approach_tips') or []
    has_box = 'APPROACHES' in sq and (not tips or flat(gs.strip_tags(tips[0])) in ftext)
    check('approaches_box', has_box if tips else True,
          '%d tips in crag.json' % len(tips))

    sym = meta.get('top_pick_symbol') or gs.DEFAULT_TOP_PICK_SYMBOL
    picks = [r for s in sectors for r in s.get('routes', []) if gs.is_top_pick(r)]
    in_rows = any(sym in t for t in seg.values())
    check('top_pick', in_rows == bool(picks), '%d top picks; symbol in sector pages: %s'
          % (len(picks), in_rows))

    fronts = crag.get('front_pages', [])
    first = fronts[0] if fronts else {}
    check('important_first', 'important' in (first.get('title', '') + first.get('kicker', '')).lower()
          and flat(first.get('title', '')) in ftext, 'first front page: %r' % first.get('title'))

    if is_html:
        ext = re.findall(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', re.sub(r'<style.*?</style>', '', raw, flags=re.S))
        nondata = [m for m in re.findall(r'<img[^>]*src="([^"]{0,30})', raw) if not m.startswith('data:')]
        check('html_self_contained', not ext and not nondata,
              '%d external refs, %d non-data images' % (len(ext), len(nondata)))

    all_pass = all(c['pass'] for c in checks)
    print(json.dumps({'guide': args.guide, 'renderer': 'html' if is_html else 'pdf',
                      'checks': checks, 'all_pass': all_pass,
                      'next_step': 'Also look at the pages: cover, contents, the Important page, '
                                   'a dense and a sparse sector, every sector with field notes '
                                   'or an override, and the index.'},
                     ensure_ascii=False, indent=1))
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
