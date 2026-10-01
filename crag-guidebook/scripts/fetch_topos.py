#!/usr/bin/env python3
"""
fetch_topos.py — rung 1 of the topo ladder: OpenStreetMap climbing data + Wikimedia
Commons photos, with licence and credit recorded. Standard library only.

Subcommands
-----------
  find   list climbing-tagged OSM objects around a point or in a bbox (Overpass API):
         name, coordinates, OSM id, wikimedia_commons[:N] tags and their :path tags.
  fetch  for chosen objects from a `find` result: ask the Commons API for each photo's
         URL, licence, author and file page; download a thumbnail into topo/; attach it
         to a sector in crag.json with caption, source, licence, credit, source_url,
         retrieved, and the route lines (wikimedia_commons[:N]:path) drawn on it.

Usage
-----
  python3 scripts/fetch_topos.py find --lat 46.50 --lon 11.80 --radius 1500 > osm.json
  python3 scripts/fetch_topos.py find --bbox 46.49,11.79,46.51,11.81 > osm.json
  python3 scripts/fetch_topos.py fetch --objects osm.json --crag crag.json
  python3 scripts/fetch_topos.py fetch --objects osm.json --crag crag.json \\
      --select node/123,relation/456 --sector 3 --allow-personal-use

Politeness: a descriptive User-Agent (Wikimedia policy), --delay seconds between
requests, no retries. On HTTP 403/429, a challenge page or a network failure it stops
and prints {"status": "blocked"|"offline", ...} (exit 4) — record the gap in HANDOVER.md.
NC or unknown licences are skipped unless --allow-personal-use (the user confirmed).
The route-line format is described in references/topos.md.

Output: JSON on stdout. Exit 0 ok, 2 bad input, 4 blocked/offline.
"""

import argparse
import datetime
import html
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = 'crag-guidebook/1.1 (https://github.com/OrrZwebner/crag-guidebook)'
OVERPASS = 'https://overpass-api.de/api/interpreter'
COMMONS = 'https://commons.wikimedia.org/w/api.php'
IMG_KEY = re.compile(r'^wikimedia_commons(?::?(\d+))?$')
POINT_TYPES = {'B': 'bolt', 'A': 'anchor', 'P': 'piton', 'S': 'sling', 'U': 'unfinished'}
TOPO_KINDS = ('crag', 'area')


class Stop(Exception):
    """A block or network failure: stop, never retry."""

    def __init__(self, status, url, detail):
        super().__init__(detail)
        self.status, self.url, self.detail = status, url, detail


class Client:
    def __init__(self, delay, timeout):
        self.delay, self.timeout, self.calls = delay, timeout, 0

    def get(self, url, data=None, expect_json=True):
        if self.calls and self.delay:
            time.sleep(self.delay)
        self.calls += 1
        body = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw, ctype = r.read(), r.headers.get('Content-Type', '')
                challenge = r.headers.get('cf-mitigated')
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429) or exc.headers.get('cf-mitigated'):
                raise Stop('blocked', url, 'HTTP %d' % exc.code)
            raise Stop('offline', url, 'HTTP %d' % exc.code)
        except (urllib.error.URLError, OSError) as exc:
            raise Stop('offline', url, str(getattr(exc, 'reason', exc)))
        if challenge:
            raise Stop('blocked', url, 'challenge page (cf-mitigated)')
        if not expect_json:
            return raw
        try:
            return json.loads(raw.decode('utf-8'))
        except ValueError:
            kind = 'challenge page' if 'html' in ctype.lower() else 'non-JSON reply'
            raise Stop('blocked', url, kind)


def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    return code


def stopped(exc, **extra):
    out = {'status': exc.status, 'url': exc.url, 'detail': exc.detail,
           'next_step': 'Stop here; do not retry in a loop. Record the gap (what was not '
                        'fetched, and why) in HANDOVER.md and tell the user.'}
    out.update(extra)
    return emit(out, 4)


# ------------------------------------------------------------------ find

def overpass_query(args):
    if args.bbox:
        s, w, n, e = [float(x) for x in args.bbox.split(',')]
        area = ''
    else:
        dlat = args.radius / 111132.0
        dlon = args.radius / (111320.0 * max(math.cos(math.radians(args.lat)), 0.01))
        s, w, n, e = args.lat - dlat, args.lon - dlon, args.lat + dlat, args.lon + dlon
        area = '(around:%d,%f,%f)' % (args.radius, args.lat, args.lon)
    # the global [bbox] lets Overpass narrow spatially before matching tags
    return ('[out:json][timeout:25][bbox:%.6f,%.6f,%.6f,%.6f];'
            '(nwr["climbing"]%s;nwr["sport"="climbing"]%s;);out tags center;'
            % (s, w, n, e, area, area))


def summarise(el):
    tags = el.get('tags') or {}
    lat = el.get('lat', (el.get('center') or {}).get('lat'))
    lon = el.get('lon', (el.get('center') or {}).get('lon'))
    images = []
    for k in sorted(tags):
        m = IMG_KEY.match(k)
        if m and tags[k].strip():
            images.append({'key': k, 'n': int(m.group(1) or 1), 'file': norm_file(tags[k]),
                           'path': tags.get(k + ':path')})
    images.sort(key=lambda i: i['n'])
    grade = next((tags[k] for k in sorted(tags) if k.startswith('climbing:grade:')
                  and not k.endswith(':mean')), None)
    return {'osm': '%s/%s' % (el['type'], el['id']), 'name': tags.get('name'),
            'climbing': tags.get('climbing'), 'lat': lat, 'lon': lon, 'grade': grade,
            'images': images}


def norm_file(v):
    v = v.split(';')[0].strip()
    v = re.sub(r'^(?:file|image):', '', v, flags=re.I)
    return 'File:' + v.replace('_', ' ')


def cmd_find(args, cl):
    if not args.bbox and (args.lat is None or args.lon is None):
        return emit({'status': 'error', 'error': 'give --lat and --lon, or --bbox'}, 2)
    q = overpass_query(args)
    try:
        data = cl.get(args.overpass_url, {'data': q})
    except Stop as exc:
        return stopped(exc, query=q)
    objs = [summarise(el) for el in data.get('elements', [])]
    objs.sort(key=lambda o: (o['climbing'] not in TOPO_KINDS, o['osm']))
    return emit({'status': 'ok', 'query': q, 'count': len(objs),
                 'with_images': sum(1 for o in objs if o['images']),
                 'attribution': '© OpenStreetMap contributors, ODbL',
                 'objects': objs,
                 'next_step': 'Save this as osm.json and run `fetch --objects osm.json '
                              '--crag crag.json` (optionally --select ids).'})


# ------------------------------------------------------------------ fetch

def parse_path(s):
    """'0.1,0.9|0.2,0.5B:|0.3,0.1A' -> [{'x','y','type','dotted_before'}] (see topos.md)."""
    pts, prev_dotted = [], False
    for seg in [t for t in (s or '').split('|') if t]:
        dotted_after = seg.endswith(':')
        seg = seg.rstrip(':')
        x, _, y = seg.partition(',')
        typ = None
        if y and y[-1] in POINT_TYPES:
            typ, y = POINT_TYPES[y[-1]], y[:-1]
        try:
            p = {'x': float(x), 'y': float(y)}
        except ValueError:
            continue
        if typ:
            p['type'] = typ
        if pts and prev_dotted:
            p['dotted_before'] = True
        pts.append(p)
        prev_dotted = dotted_after
    return pts


def strip_html(v):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', v or ''))).strip()


def personal_use_only(lic):
    l = (lic or '').lower()
    return not l or 'nc' in re.split(r'[^a-z]+', l) or 'non-commercial' in l or 'unknown' in l


def dist_m(a_lat, a_lon, b_lat, b_lon):
    dy = (a_lat - b_lat) * 111132.0
    dx = (a_lon - b_lon) * 111320.0 * math.cos(math.radians(a_lat))
    return math.hypot(dx, dy)


def nearest_sector(sectors, lat, lon, max_m):
    best = None
    for s in sectors:
        if s.get('lat') is None or lat is None:
            continue
        d = dist_m(lat, lon, s['lat'], s['lon'])
        if d <= max_m and (best is None or d < best[0]):
            best = (d, s)
    return best[1] if best else None


def svg_overlay(lines, w, h):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d">' % (w, h)]
    for ln in lines:
        pts = ' '.join('%.1f,%.1f' % (p['x'] * w, p['y'] * h) for p in ln['points'])
        out.append('<polyline points="%s" fill="none" stroke="#e8262b" stroke-width="%.1f"/>'
                   % (pts, max(w, h) / 250.0))
    out.append('</svg>')
    return '\n'.join(out)


def cmd_fetch(args, cl):
    try:
        with open(args.objects, encoding='utf-8') as f:
            found = json.load(f)
        with open(args.crag, encoding='utf-8') as f:
            crag = json.load(f)
    except (OSError, ValueError) as exc:
        return emit({'status': 'error', 'error': str(exc)}, 2)
    objs = found.get('objects', found if isinstance(found, list) else [])
    sel = set(x.strip() for x in (args.select or '').split(',') if x.strip())
    chosen = [o for o in objs if o.get('images') and
              (o['osm'] in sel if sel else o.get('climbing') in TOPO_KINDS)]
    if sel - {o['osm'] for o in objs}:
        return emit({'status': 'error', 'error': 'not in --objects: %s'
                     % sorted(sel - {o['osm'] for o in objs})}, 2)

    # route lines: every object (usually routes) whose image tag names the same file
    lines_by_file = {}
    for o in objs:
        for im in o.get('images', []):
            if im.get('path'):
                lines_by_file.setdefault(im['file'], []).append(
                    {'osm': o['osm'], 'name': o.get('name'), 'grade': o.get('grade'),
                     'path': im['path'], 'points': parse_path(im['path'])})

    base = os.path.abspath(args.assets or os.path.dirname(os.path.abspath(args.crag)))
    by_n = {s.get('n'): s for s in crag['sectors']}
    today = args.date or datetime.date.today().isoformat()
    added, skipped, unassigned, done_files = [], [], [], set()

    try:
        for o in chosen:
            if args.sector is not None:
                sec = by_n.get(args.sector)
            else:
                sec = nearest_sector(crag['sectors'], o.get('lat'), o.get('lon'), args.max_m)
            if sec is None:
                unassigned.append({'osm': o['osm'], 'name': o.get('name'),
                                   'reason': 'no sector within %d m; pass --sector N'
                                             % args.max_m})
                continue
            attached = {t.get('commons_file') for t in sec.get('topos') or []}
            files = []
            for im in o['images']:
                if im['file'] in attached:
                    skipped.append({'file': im['file'], 'osm': o['osm'],
                                    'reason': 'already attached to sector %s' % sec.get('n')})
                elif im['file'] not in done_files:
                    files.append(im['file'])
            if not files:
                continue
            info = cl.get(args.commons_api, {
                'action': 'query', 'format': 'json', 'formatversion': '2',
                'prop': 'imageinfo', 'iiprop': 'url|extmetadata|size',
                'iiurlwidth': str(args.width), 'titles': '|'.join(files)})
            pages = {p.get('title'): p for p in (info.get('query') or {}).get('pages', [])}
            for norm in (info.get('query') or {}).get('normalized', []):
                if norm.get('to') in pages:
                    pages[norm['from']] = pages[norm['to']]
            for fname in files:
                done_files.add(fname)
                ii = ((pages.get(fname) or {}).get('imageinfo') or [None])[0]
                if not ii:
                    skipped.append({'file': fname, 'osm': o['osm'], 'reason': 'not on Commons'})
                    continue
                md = ii.get('extmetadata') or {}
                lic = strip_html((md.get('LicenseShortName') or {}).get('value'))
                artist = strip_html((md.get('Artist') or {}).get('value')) or 'unknown author'
                if personal_use_only(lic) and not args.allow_personal_use:
                    skipped.append({'file': fname, 'osm': o['osm'], 'licence': lic or 'unknown',
                                    'reason': 'NC or unknown licence: personal use only; '
                                              'rerun with --allow-personal-use if the user '
                                              'confirms'})
                    continue
                url = ii.get('thumburl') or ii.get('url')
                blob = None if args.dry_run else cl.get(url, expect_json=False)
                ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower() or '.jpg'
                have = {t.get('image') for t in sec.get('topos') or []}
                n = sec.get('n')
                rel = next('topo/osm_%02d%s%s' % (n, c, ext) for c in 'abcdefghijklmnopqrstuvwxyz'
                           if 'topo/osm_%02d%s%s' % (n, c, ext) not in have
                           and not os.path.exists(os.path.join(base, 'topo/osm_%02d%s%s'
                                                                % (n, c, ext))))
                if blob is not None:
                    os.makedirs(os.path.join(base, 'topo'), exist_ok=True)
                    with open(os.path.join(base, rel), 'wb') as f:
                        f.write(blob)
                title = o.get('name') or fname[5:]
                lic_txt = lic or 'licence unknown (personal use)'
                entry = {'image': rel,
                         'caption': 'Topo — %s · %s · %s · Wikimedia Commons'
                                    % (title, artist, lic_txt),
                         'source': 'Wikimedia Commons via OpenStreetMap (%s)' % o['osm'],
                         'licence': lic_txt, 'credit': artist,
                         'source_url': ii.get('descriptionurl') or '',
                         'retrieved': today, 'commons_file': fname}
                w, h = ii.get('thumbwidth') or ii.get('width'), ii.get('thumbheight') or ii.get('height')
                if w and h:
                    entry['size'] = [int(w), int(h)]
                lines = lines_by_file.get(fname) or []
                if lines:
                    entry['lines'] = lines
                    if w and h and not args.dry_run:
                        with open(os.path.join(base, os.path.splitext(rel)[0] + '.lines.svg'),
                                  'w', encoding='utf-8') as f:
                            f.write(svg_overlay(lines, int(w), int(h)))
                if personal_use_only(lic):
                    entry['caption'] += ' (personal use)'
                sec.setdefault('topos', []).append(entry)
                added.append({'sector': n, 'image': rel, 'file': fname, 'licence': lic_txt,
                              'credit': artist, 'lines': len(lines)})
    except Stop as exc:
        if added and not args.dry_run:
            write(args.crag, crag)
        return stopped(exc, added=added, skipped=skipped, unassigned=unassigned)

    if added and not args.dry_run:
        write(args.crag, crag)
    return emit({'status': 'ok', 'dry_run': args.dry_run, 'added': added, 'skipped': skipped,
                 'unassigned': unassigned, 'requests': cl.calls,
                 'next_step': 'Add "Map data © OpenStreetMap contributors (ODbL)" to the '
                              'sources page; rebuild; check every topo is the right way up.'})


def write(path, crag):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(crag, f, ensure_ascii=False, indent=1)


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--delay', type=float, default=1.5, help='seconds between requests')
    common.add_argument('--timeout', type=float, default=60)
    common.add_argument('--overpass-url', default=OVERPASS, help='Overpass endpoint')
    common.add_argument('--commons-api', default=COMMONS, help='Commons API endpoint')
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', metavar='{find,fetch}')
    sub.required = True

    f = sub.add_parser('find', parents=[common],
                       help='list climbing-tagged OSM objects (Overpass)')
    f.add_argument('--lat', type=float)
    f.add_argument('--lon', type=float)
    f.add_argument('--radius', type=int, default=1500, help='metres (default 1500)')
    f.add_argument('--bbox', help='south,west,north,east')

    g = sub.add_parser('fetch', parents=[common], help='download Commons photos for chosen objects into crag.json')
    g.add_argument('--objects', required=True, help='the JSON printed by `find`')
    g.add_argument('--crag', required=True)
    g.add_argument('--select', help='comma-separated OSM ids (default: every crag/area '
                                    'object with an image)')
    g.add_argument('--sector', type=int, help='attach to this sector (default: nearest)')
    g.add_argument('--max-m', type=int, default=400,
                   help='nearest-sector search radius in metres (default 400)')
    g.add_argument('--width', type=int, default=1280, help='thumbnail width (default 1280)')
    g.add_argument('--assets', help='crag folder (default: folder of --crag)')
    g.add_argument('--allow-personal-use', action='store_true',
                   help='include NC/unknown-licence images (only after the user confirms)')
    g.add_argument('--date', help='retrieved date (default today)')
    g.add_argument('--dry-run', action='store_true',
                   help='query licences only; download nothing, write nothing')
    args = ap.parse_args()
    cl = Client(args.delay, args.timeout)
    return cmd_find(args, cl) if args.cmd == 'find' else cmd_fetch(args, cl)


if __name__ == '__main__':
    sys.exit(main())
