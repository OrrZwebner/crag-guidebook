#!/usr/bin/env python3
"""
make_maps.py — scaled plan maps of a crag: OpenStreetMap context, numbered sector pins.

Satellite imagery is usually out of reach (tile servers are blocked in most sandboxes,
and a screenshot is pixels in a conversation, not a file for the PDF). So this draws
the map itself, on a light printable background:

  context   roads by class, tracks, footpaths, cliffs, rivers, lakes, coastline,
            buildings and car parks from OpenStreetMap (Overpass API), clipped to the
            map. Fetched once and cached as JSON next to the image, so a rebuild works
            offline and draws the same map.
  crag      a numbered pin per sector, an arrow for the aspect used in the shade
            calculation, leader lines to labels, a "P" for every sector parking spot,
            the valley axis if given, a scale bar, a north arrow and the OSM credit.

The frame is fitted to the sectors (no empty bands). Long thin crags or several
separate crags do not fit one page: pass --split to draw one map per group.
Give the reader satellite imagery separately through the KML from export_geo.py.

Context sources (--context):
  auto   use the cache next to the map if present, else fetch from Overpass; on a
         block or network failure draw without context and say so (default)
  osm    always fetch (refresh the cache)
  file   use --context-file (Overpass JSON, `out geom`) for every map
  none   pins only

Requests are paced (--delay, default 10 s). An overloaded server (5xx, timeout) falls
through to public mirrors; HTTP 403/429 or a challenge page stops fetching for the
rest of the run (no retries) and is reported: record the gap, never work around a block.
Maps already fetched are cached, so a later run only fetches what is missing.

Usage
-----
  python3 scripts/make_maps.py --crag crag.json --out maps/
  python3 scripts/make_maps.py --crag crag.json --out maps/ --axis-file axis.json
  python3 scripts/make_maps.py --crag crag.json --out maps/ --split 1-3,4-6
  python3 scripts/make_maps.py --crag crag.json --out maps/ --split auto --context none

Needs matplotlib. Without it, prints {"ok": false, "missing": "matplotlib", ...}
and exits 3: skip the map pages (leave "maps" empty) and say so.
Prints a JSON summary on stdout. OSM data is © OpenStreetMap contributors (ODbL):
the maps print the credit; also list it on the guide's credits page.
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

plt = withStroke = withTickedStroke = None   # imported lazily in main(): optional dependency

UA = 'crag-guidebook/1.2 (https://github.com/OrrZwebner/crag-guidebook)'
OVERPASS = 'https://overpass-api.de/api/interpreter'
# public mirrors, tried in order only when a server is overloaded or offline (5xx, timeout),
# never after a 403/429 block
MIRRORS = ['https://overpass.private.coffee/api/interpreter',
           'https://overpass.kumi.systems/api/interpreter']
ATTRIBUTION = 'Map data © OpenStreetMap contributors (ODbL)'

PAPER = '#f4f0e6'
TEXT = '#1d1f17'
HALO = '#fbf9f3'
PIN = '#d63a20'
ARROW = '#c27a00'
LEADER = '#8b8676'
AXIS, AXIS_EDGE = '#f0c95a', '#9c7d24'
WATER, WATER_LINE = '#bcd6e4', '#6fa3c4'
BUILDING, BUILDING_EDGE = '#ddd3c1', '#c4b79e'
PARKING_FILL = '#e3e7ef'
CLIFF = '#6b5440'
PARK_PIN = '#2c5aa0'
# highway class -> (casing colour, fill colour, width, dash)
ROADS = {
    'major':  ('#a8946b', '#fbe3a0', 3.4, None),
    'minor':  ('#b3a787', '#ffffff', 2.4, None),
    'track':  (None, '#9a7f52', 1.1, (0, (4, 2))),
    'path':   (None, '#8a5f3c', 0.9, (0, (1.2, 1.6))),
}
MAJOR = {'motorway', 'trunk', 'primary', 'secondary', 'motorway_link', 'trunk_link',
         'primary_link', 'secondary_link'}
MINOR = {'tertiary', 'tertiary_link', 'unclassified', 'residential', 'living_street',
         'service', 'road'}
PATHS = {'path', 'footway', 'steps', 'bridleway', 'cycleway', 'pedestrian'}


class Stop(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def projector(lat0):
    mlat = 111132.0
    mlon = 111320.0 * math.cos(math.radians(lat0))
    fwd = lambda lat, lon: (lon * mlon, lat * mlat)
    inv = lambda x, y: (y / mlat, x / mlon)
    return fwd, inv


def parse_split(spec, sectors):
    """'1-14,15-20' -> [[1..14], [15..20]]; 'auto' cuts at the largest gaps."""
    nums = [s['n'] for s in sectors]
    if not spec:
        return [nums]
    if spec != 'auto':
        groups = []
        for part in spec.split(','):
            if '-' in part:
                a, b = part.split('-')
                groups.append([n for n in nums if int(a) <= n <= int(b)])
            else:
                groups.append([int(part)])
        return [g for g in groups if g]

    lat0 = sum(s['lat'] for s in sectors) / len(sectors)
    proj, _ = projector(lat0)
    pts = {s['n']: proj(s['lat'], s['lon']) for s in sectors}
    order = sorted(nums, key=lambda n: -sectors[nums.index(n)]['lat'])
    gaps = [(math.dist(pts[a], pts[b]), a, b) for a, b in zip(order, order[1:])]
    if not gaps:
        return [nums]
    biggest = max(g[0] for g in gaps)
    median = sorted(g[0] for g in gaps)[len(gaps) // 2] or 1.0
    if biggest < 6 * median:
        return [order]
    groups, cur = [], [order[0]]
    for dist, _a, b in gaps:
        if dist >= 6 * median:
            groups.append(cur)
            cur = [b]
        else:
            cur.append(b)
    groups.append(cur)
    return groups


# ------------------------------------------------------------------ OSM context
def overpass_query(bbox):
    s, w, n, e = bbox
    b = '(%.6f,%.6f,%.6f,%.6f)' % (s, w, n, e)
    return ('[out:json][timeout:60];('
            'way["highway"]%s;way["natural"="cliff"]%s;way["waterway"]%s;'
            'way["natural"="water"]%s;way["landuse"="reservoir"]%s;way["natural"="coastline"]%s;'
            'way["building"]%s;way["amenity"="parking"]%s;node["amenity"="parking"]%s;'
            ');out geom;' % ((b,) * 9))


def fetch_context(bbox, urls, timeout):
    """Try each endpoint; an overloaded/offline server falls through, a block stops."""
    last = None
    for url in urls:
        try:
            return _fetch(bbox, url, timeout)
        except Stop as exc:
            if exc.status == 'blocked':
                raise
            last = exc
    raise last


def _fetch(bbox, url, timeout):
    body = urllib.parse.urlencode({'data': overpass_query(bbox)}).encode()
    req = urllib.request.Request(url, data=body, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, ctype = r.read(), r.headers.get('Content-Type', '')
            if r.headers.get('cf-mitigated'):
                raise Stop('blocked', 'challenge page (cf-mitigated)')
    except urllib.error.HTTPError as exc:
        raise Stop('blocked' if exc.code in (403, 429) else 'offline', 'HTTP %d' % exc.code)
    except (urllib.error.URLError, OSError) as exc:
        raise Stop('offline', str(getattr(exc, 'reason', exc)))
    try:
        data = json.loads(raw.decode('utf-8'))
    except ValueError:
        raise Stop('blocked' if 'html' in ctype.lower() else 'offline', 'non-JSON reply')
    data['_bbox'] = list(bbox)
    data['_source'] = url
    return data


def classify(tags):
    hw = tags.get('highway')
    if hw:
        if hw in MAJOR:
            return 'major'
        if hw in MINOR:
            return 'minor'
        if hw == 'track':
            return 'track'
        if hw in PATHS:
            return 'path'
        return None
    if tags.get('natural') == 'cliff':
        return 'cliff'
    if tags.get('natural') == 'coastline':
        return 'coast'
    if tags.get('natural') == 'water' or tags.get('landuse') == 'reservoir':
        return 'water'
    if tags.get('waterway'):
        return 'waterway'
    if tags.get('building'):
        return 'building'
    if tags.get('amenity') == 'parking':
        return 'parking'
    return None


def draw_context(ax, data, proj):
    """Draw Overpass `out geom` elements; returns a count per class."""
    layers = {k: [] for k in ('water', 'building', 'parking', 'waterway', 'coast', 'cliff',
                              'path', 'track', 'minor', 'major', 'pnode')}
    for el in data.get('elements', []):
        cls = classify(el.get('tags', {}))
        if not cls:
            continue
        if el.get('type') == 'node':
            if cls == 'parking':
                layers['pnode'].append(proj(el['lat'], el['lon']))
            continue
        geom = el.get('geometry') or []
        xy = [proj(p['lat'], p['lon']) for p in geom if p]
        if len(xy) >= 2:
            layers[cls].append(xy)
    for cls in ('water', 'building', 'parking'):
        fill, edge = {'water': (WATER, WATER_LINE), 'building': (BUILDING, BUILDING_EDGE),
                      'parking': (PARKING_FILL, '#aab3c5')}[cls]
        for xy in layers[cls]:
            ax.fill([p[0] for p in xy], [p[1] for p in xy], color=fill, ec=edge, lw=0.4, zorder=1)
    for xy in layers['waterway']:
        ax.plot(*zip(*xy), color=WATER_LINE, lw=1.0, zorder=1.5)
    for xy in layers['coast']:
        ax.plot(*zip(*xy), color=WATER_LINE, lw=1.6, zorder=1.5)
    for cls in ('path', 'track', 'minor', 'major'):
        case, fill, w, dash = ROADS[cls]
        for xy in layers[cls]:
            xs, ys = zip(*xy)
            if case:
                ax.plot(xs, ys, color=case, lw=w + 1.2, solid_capstyle='round', zorder=2)
            ax.plot(xs, ys, color=fill, lw=w, solid_capstyle='round',
                    linestyle=dash if dash else '-', zorder=2.2)
    for xy in layers['cliff']:
        # OSM draws a cliff with its lower side on the RIGHT of the way direction; ticks hang (matplotlib: -90° = right of travel)
        # down-slope (checked against south-facing Sella walls: ways run W→E, ticks south).
        effects = [withTickedStroke(angle=-90, spacing=5, length=0.6)] if withTickedStroke else None
        ax.plot(*zip(*xy), color=CLIFF, lw=1.3, zorder=2.5, path_effects=effects)
    for x, y in layers['pnode']:
        ax.text(x, y, 'P', ha='center', va='center', fontsize=5.5, color='#5a6680',
                fontweight='bold', zorder=2.6)
    return {k: len(v) for k, v in layers.items() if v}


def cliff_check(chosen, data, proj, radius=80.0):
    """Compare each sector's aspect with the down-slope side of the nearest OSM cliff.

    OSM draws a cliff with its lower side on the right of the way direction, so the
    right-hand normal of the nearest segment is the cliff's facing. Mappers sometimes draw
    cliffs backwards, so a disagreement is a flag to check, not a verdict."""
    segs = []
    for el in (data or {}).get('elements', []):
        if el.get('type') != 'way' or el.get('tags', {}).get('natural') != 'cliff':
            continue
        xy = [proj(p['lat'], p['lon']) for p in el.get('geometry') or [] if p]
        segs += [(a, b, el.get('id')) for a, b in zip(xy, xy[1:]) if a != b]
    out = []
    for s in chosen:
        if s.get('aspect_deg') is None or not segs:
            continue
        px, py = proj(s['lat'], s['lon'])
        best = None
        for (ax_, ay), (bx, by), wid in segs:
            dx, dy = bx - ax_, by - ay
            t = max(0.0, min(1.0, ((px - ax_) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            d = math.hypot(px - (ax_ + t * dx), py - (ay + t * dy))
            if best is None or d < best[0]:
                best = (d, dx, dy, wid)
        if best is None or best[0] > radius:
            continue
        d, dx, dy, wid = best
        facing = math.degrees(math.atan2(dy, -dx)) % 360   # right-hand normal (dy, -dx) as a bearing
        diff = abs((facing - float(s['aspect_deg']) + 180) % 360 - 180)
        out.append({'sector': s['n'], 'aspect_deg': s['aspect_deg'], 'osm_cliff_facing': round(facing),
                    'difference': round(diff), 'distance_m': round(d), 'osm_way': wid,
                    'agrees': diff <= 90})
    return out


# ------------------------------------------------------------------ map
def frame(chosen, proj, width, height_max):
    """Map extent in metres, fitted to the figure so there are no empty bands."""
    pts = [proj(s['lat'], s['lon']) for s in chosen]
    for s in chosen:
        if s.get('parking'):
            pts.append(proj(*s['parking']))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    sx, sy = max(xs) - min(xs), max(ys) - min(ys)
    pad = max(max(sx, sy) * 0.12, 120.0)
    side = max(sx, 2 * pad) * 0.9                      # room for labels left and right
    xmin, xmax = min(xs) - pad - side, max(xs) + pad + side
    ymin, ymax = min(ys) - pad * 1.6, max(ys) + pad    # scale bar below
    aspect = (ymax - ymin) / (xmax - xmin)
    height = min(max(width * aspect, width * 0.5), height_max)
    want = height / width
    if aspect < want:
        grow = ((xmax - xmin) * want - (ymax - ymin)) / 2
        ymin, ymax = ymin - grow, ymax + grow
    else:
        grow = ((ymax - ymin) / want - (xmax - xmin)) / 2
        xmin, xmax = xmin - grow, xmax + grow
    return (xmin, xmax, ymin, ymax), height, pad


def draw(path, chosen, axis_xy, proj, right_ids, width, height, ext, pad, context):
    xmin, xmax, ymin, ymax = ext
    span = ymax - ymin
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    ax.set_facecolor(PAPER)
    ctx_counts = draw_context(ax, context, proj) if context else {}

    if axis_xy:
        ax.plot([p[0] for p in axis_xy], [p[1] for p in axis_xy],
                color=AXIS_EDGE, lw=6, solid_capstyle='round', zorder=2.8, alpha=0.8)
        ax.plot([p[0] for p in axis_xy], [p[1] for p in axis_xy],
                color=AXIS, lw=3, solid_capstyle='round', zorder=2.9, alpha=0.9)

    pts = {s['n']: proj(s['lat'], s['lon']) for s in chosen}
    halo = lambda w: [withStroke(linewidth=w, foreground=HALO)]
    for s in chosen:
        if s.get('parking'):
            px, py = proj(*s['parking'])
            ax.plot([px], [py], 's', ms=9, color=PARK_PIN, mec='white', mew=1.1, zorder=5)
            ax.text(px, py, 'P', ha='center', va='center', color='white', fontsize=6,
                    fontweight='bold', zorder=5.1)

    for side in (0, 1):
        group = sorted([s['n'] for s in chosen if (s['n'] in right_ids) == bool(side)],
                       key=lambda n: pts[n][1])
        if not group:
            continue
        minsep = span * 0.05
        last, lab_y = -1e18, {}
        for n in group:
            lab_y[n] = max(pts[n][1], last + minsep)
            last = lab_y[n]
        shift = ((pts[group[0]][1] + pts[group[-1]][1]) / 2
                 - (lab_y[group[0]] + lab_y[group[-1]]) / 2)
        for n in group:
            lab_y[n] += shift
        lab_x = xmax - (xmax - xmin) * 0.03 if side else xmin + (xmax - xmin) * 0.03
        ha = 'right' if side else 'left'
        for n in group:
            s = next(x for x in chosen if x['n'] == n)
            px, py = pts[n]
            ax.plot([px, lab_x], [py, lab_y[n]], color=LEADER, lw=0.7, alpha=0.9, zorder=3)
            if s.get('aspect_deg') is not None:
                a = math.radians(s['aspect_deg'])
                ax.annotate('', xy=(px + math.sin(a) * pad * 0.55, py + math.cos(a) * pad * 0.55),
                            xytext=(px, py),
                            arrowprops=dict(arrowstyle='-|>', color=ARROW, lw=1.6,
                                            shrinkA=8, shrinkB=0), zorder=4)
            ax.plot([px], [py], 'o', ms=13, color=PIN, mec='white', mew=1.5, zorder=6)
            ax.text(px, py, str(n), ha='center', va='center', color='white',
                    fontsize=6.8, fontweight='bold', zorder=7)
            ax.text(lab_x, lab_y[n], '%d  %s' % (n, s['name']), ha=ha, va='center',
                    color=TEXT, fontsize=8, fontweight='bold', zorder=7, path_effects=halo(3))
            sub = ' · '.join(x for x in (s.get('aspect'), s.get('asl')) if x)
            if sub:
                ax.text(lab_x, lab_y[n] - span * 0.022, sub, ha=ha, va='center',
                        color='#55584a', fontsize=6.3, zorder=7, path_effects=halo(2.4))

    width_m = xmax - xmin
    sb = next((v for v in (2000, 1000, 500, 200, 100) if v <= width_m * 0.22), 50)
    bx, by = xmin + width_m * 0.04, ymin + span * 0.05
    ax.plot([bx, bx + sb], [by, by], color=TEXT, lw=2.6, solid_capstyle='butt', zorder=8)
    for end in (bx, bx + sb):
        ax.plot([end, end], [by - span * 0.01, by + span * 0.01], color=TEXT, lw=1.6, zorder=8)
    ax.text(bx + sb / 2, by + span * 0.02, ('%d km' % (sb // 1000)) if sb >= 1000 else '%d m' % sb,
            ha='center', color=TEXT, fontsize=7, zorder=8, path_effects=halo(2.4))

    nx, ny = xmax - width_m * 0.05, ymin + span * 0.05
    ax.annotate('', xy=(nx, ny + span * 0.08), xytext=(nx, ny),
                arrowprops=dict(arrowstyle='-|>', color=TEXT, lw=1.8), zorder=8)
    ax.text(nx, ny + span * 0.1, 'N', ha='center', color=TEXT, fontsize=8.5,
            fontweight='bold', zorder=8, path_effects=halo(2.4))
    if context:
        ax.text(xmax - width_m * 0.012, ymin + span * 0.012, ATTRIBUTION, ha='right', va='bottom',
                color='#55584a', fontsize=5.2, zorder=8, path_effects=halo(2))

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color('#b9b29f')
    fig.subplots_adjust(0.004, 0.004, 0.996, 0.996)
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)
    return ctx_counts


def main():
    global plt, withStroke, withTickedStroke
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True)
    ap.add_argument('--out', default='maps')
    ap.add_argument('--axis-file', help='JSON list of [lat, lon] for the road/river')
    ap.add_argument('--split', help='"1-3,4-6", or "auto", or omit for one map')
    ap.add_argument('--context', choices=('auto', 'osm', 'file', 'none'), default='auto',
                    help='OpenStreetMap context layer (see above)')
    ap.add_argument('--context-file', help='Overpass JSON (out geom) for --context file')
    ap.add_argument('--overpass-url', default=OVERPASS,
                    help='first endpoint; public mirrors follow on 5xx/timeout')
    ap.add_argument('--no-mirrors', action='store_true', help='use --overpass-url only')
    ap.add_argument('--timeout', type=float, default=40)
    ap.add_argument('--delay', type=float, default=10,
                    help='seconds between Overpass requests (its rate limit answers 429 to bursts)')
    ap.add_argument('--width', type=float, default=7.0, help='inches')
    ap.add_argument('--height', type=float, default=8.6, help='maximum height, inches')
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as _plt
        from matplotlib import patheffects as _pe
        plt, withStroke = _plt, _pe.withStroke
        withTickedStroke = getattr(_pe, 'withTickedStroke', None)
    except Exception as exc:                                       # noqa: BLE001
        print(json.dumps({'ok': False, 'missing': 'matplotlib', 'error': str(exc),
                          'degraded': 'No plan maps. Leave "maps" empty in crag.json, build '
                                      'the guide without map pages, and rely on the KML for '
                                      'the map view.'}))
        return 3

    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    sectors = crag['sectors']
    os.makedirs(args.out, exist_ok=True)

    lat0 = sum(s['lat'] for s in sectors) / len(sectors)
    proj, inv = projector(lat0)

    axis_xy = None
    if args.axis_file:
        with open(args.axis_file, encoding='utf-8') as f:
            pts = json.load(f)
        if isinstance(pts, dict):
            pts = pts.get('points') or pts.get('coordinates')
        axis_xy = [proj(p[0], p[1]) for p in pts]

    file_ctx = None
    if args.context == 'file':
        if not args.context_file:
            ap.error('--context file needs --context-file')
        with open(args.context_file, encoding='utf-8') as f:
            file_ctx = json.load(f)

    groups = parse_split(args.split, sectors)
    written, notes, stopped, fetched = [], [], None, 0
    for i, ids in enumerate(groups, 1):
        chosen = [s for s in sectors if s['n'] in ids]
        mid = sum(s['lon'] for s in chosen) / len(chosen)
        right = {s['n'] for s in chosen if s['lon'] >= mid}
        base = 'map_%d' % i if len(groups) > 1 else 'map'
        path = os.path.join(args.out, base + '.png')
        ext, height, pad = frame(chosen, proj, args.width, args.height)
        s_, w_ = inv(ext[0], ext[2])
        n_, e_ = inv(ext[1], ext[3])
        bbox = (s_, w_, n_, e_)

        context, ctx_status = None, 'none'
        cache = os.path.join(args.out, base + '_osm.json')
        if args.context == 'file':
            context, ctx_status = file_ctx, 'file'
        elif args.context in ('auto', 'osm'):
            if args.context == 'auto' and os.path.exists(cache):
                with open(cache, encoding='utf-8') as f:
                    context = json.load(f)
                same = ([round(v, 5) for v in context.get('_bbox', [])]
                        == [round(v, 5) for v in bbox])
                ctx_status = 'cache' if same else 'none'
                if not same:
                    context = None
            if context is None and stopped is None:
                try:
                    if fetched and args.delay:
                        time.sleep(args.delay)
                    fetched += 1
                    context = fetch_context(bbox, [args.overpass_url] + ([] if args.no_mirrors else MIRRORS),
                                            args.timeout)
                    with open(cache, 'w', encoding='utf-8') as f:
                        json.dump(context, f)
                    ctx_status = 'fetched'
                except Stop as exc:
                    stopped = {'status': exc.status, 'detail': exc.detail, 'map': path}
            if context is None:
                ctx_status = 'unavailable'
        counts = draw(path, chosen, axis_xy, proj, right, args.width, height, ext, pad, context)
        checks = cliff_check(chosen, context, proj) if context else []
        written.append({'image': path, 'sectors': ids, 'context': ctx_status,
                        'cliff_check': checks,
                        'context_features': counts,
                        'context_cache': cache if ctx_status in ('fetched', 'cache') else None})

    if not axis_xy:
        notes.append('No --axis-file, so no valley line is drawn; every sector is still '
                     'placed correctly.')
    if stopped:
        notes.append('OpenStreetMap context stopped (%s: %s) from %s on: those maps are pins '
                     'only. Do not retry in a loop; record the gap in HANDOVER.md, or pass a '
                     'saved Overpass export with --context file.'
                     % (stopped['status'], stopped['detail'], stopped['map']))
    if any(m['context'] in ('fetched', 'cache', 'file') for m in written):
        notes.append('The maps show OSM data: keep the "%s" credit on the credits page, and '
                     'keep the *_osm.json caches next to the maps so a rebuild is offline.'
                     % ATTRIBUTION)
    bad = [c for m in written for c in m['cliff_check'] if not c['agrees']]
    if bad:
        notes.append('Aspect vs OSM cliff: %s. The nearest mapped cliff faces >90° away from the '
                     'aspect used for shade. Either the OSM cliff is drawn backwards (common) or '
                     'the aspect is wrong: check imagery or the source text, and list it in the '
                     'contradictions appendix.' % ', '.join(
                         '§%d (aspect %s°, cliff %s°)' % (c['sector'], c['aspect_deg'],
                                                         c['osm_cliff_facing']) for c in bad))
    notes.append('Look at each map. The label placer spreads labels vertically but cannot '
                 'solve every collision; split a dense cluster into its own map with --split.')
    print(json.dumps({'ok': True, 'maps': written, 'notes': notes, 'context_stopped': stopped,
                      'next_step': 'Add each image to "maps" in crag.json (path relative to '
                                   'the crag folder) with kicker, title, caption and sectors.'},
                     indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
