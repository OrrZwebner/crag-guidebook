#!/usr/bin/env python3
"""
make_maps.py — scaled plan maps of a crag, with labelled sector pins.

Satellite imagery is usually out of reach: tile servers are blocked by egress
policy in most sandboxes, and a screenshot of an online map arrives as pixels in
a conversation rather than as a file you can place in a PDF. So this draws the
map from the coordinates instead — the valley axis, a numbered pin per sector,
an arrow showing which way each wall faces, leader lines out to labels, a scale
bar and a north arrow. It is correct to the metre and it prints well, which a
screenshot is not.

Give the reader satellite imagery separately through the KML that export_geo.py
writes; the two complement each other.

Long thin crags do not fit one page usefully, so pass --split to cut the sector
list into several maps at the big gaps.

Usage
-----
  python3 scripts/make_maps.py --crag crag.json --out maps/
  python3 scripts/make_maps.py --crag crag.json --out maps/ --axis-file axis.json
  python3 scripts/make_maps.py --crag crag.json --out maps/ --split 1-3,4-6
  python3 scripts/make_maps.py --crag crag.json --out maps/ --split auto

Needs matplotlib. Without it, prints {"ok": false, "missing": "matplotlib", ...}
and exits 3: skip the map pages (leave "maps" empty) and say so.
Prints a JSON summary on stdout.
"""

import argparse
import json
import math
import os
import sys

plt = withStroke = None                    # imported lazily in main(): optional dependency

INK = '#12160f'
ROAD = '#e6cf82'
ROAD_EDGE = '#6b6030'
PIN = '#e0452b'
ARROW = '#ffd36b'
LEADER = '#8d9478'


def projector(lat0):
    mlat = 111132.0
    mlon = 111320.0 * math.cos(math.radians(lat0))
    return lambda lat, lon: (lon * mlon, lat * mlat)


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

    # auto: order along the crag, cut where consecutive sectors are far apart
    lat0 = sum(s['lat'] for s in sectors) / len(sectors)
    proj = projector(lat0)
    pts = {s['n']: proj(s['lat'], s['lon']) for s in sectors}
    order = sorted(nums, key=lambda n: -sectors[nums.index(n)]['lat'])
    gaps = []
    for a, b in zip(order, order[1:]):
        gaps.append((math.dist(pts[a], pts[b]), a, b))
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


def draw(path, sectors, ids, axis_xy, proj, right_ids, width, height,
         pad_factor=1.0, scale_hint=None):
    chosen = [s for s in sectors if s['n'] in ids]
    pts = {s['n']: proj(s['lat'], s['lon']) for s in chosen}
    xs = [p[0] for p in pts.values()]
    ys = [p[1] for p in pts.values()]
    spread = max(max(ys) - min(ys), 1.0)
    pad = max(spread * 0.06, 150.0) * pad_factor

    xmin, xmax = min(xs) - pad * 2.6, max(xs) + pad * 2.6
    ymin, ymax = min(ys) - pad * 1.45, max(ys) + pad * 0.55
    span = ymax - ymin

    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    ax.set_facecolor(INK)

    if axis_xy:
        ax.plot([p[0] for p in axis_xy], [p[1] for p in axis_xy],
                color=ROAD_EDGE, lw=7, solid_capstyle='round', zorder=1)
        ax.plot([p[0] for p in axis_xy], [p[1] for p in axis_xy],
                color=ROAD, lw=3.4, solid_capstyle='round', zorder=2)

    for side in (0, 1):
        group = sorted([n for n in ids if (n in right_ids) == bool(side)],
                       key=lambda n: pts[n][1])
        if not group:
            continue
        minsep = span * 0.036
        last = -1e18
        lab_y = {}
        for n in group:
            y = max(pts[n][1], last + minsep)
            lab_y[n] = y
            last = y
        shift = ((pts[group[0]][1] + pts[group[-1]][1]) / 2
                 - (lab_y[group[0]] + lab_y[group[-1]]) / 2)
        for n in group:
            lab_y[n] += shift

        lab_x = xmax - (xmax - xmin) * 0.035 if side else xmin + (xmax - xmin) * 0.035
        ha = 'right' if side else 'left'
        for n in group:
            s = next(x for x in chosen if x['n'] == n)
            px, py = pts[n]
            ax.plot([px, lab_x], [py, lab_y[n]], color=LEADER, lw=0.8,
                    alpha=0.85, zorder=3)
            if s.get('aspect_deg') is not None:
                a = math.radians(s['aspect_deg'])
                ax.annotate('', xy=(px + math.sin(a) * pad * 0.42,
                                    py + math.cos(a) * pad * 0.42),
                            xytext=(px, py),
                            arrowprops=dict(arrowstyle='-|>', color=ARROW, lw=1.5,
                                            alpha=0.95, shrinkA=9, shrinkB=0),
                            zorder=4)
            ax.plot([px], [py], 'o', ms=15, color=PIN, mec='white', mew=1.6, zorder=6)
            ax.text(px, py, str(n), ha='center', va='center', color='white',
                    fontsize=7.6, fontweight='bold', zorder=7)
            ax.text(lab_x, lab_y[n], '%d  %s' % (n, s['name']), ha=ha, va='center',
                    color='white', fontsize=8.4, fontweight='bold', zorder=7,
                    path_effects=[withStroke(linewidth=3, foreground='#0b0d08')])
            sub = ' · '.join(x for x in (s.get('aspect'), s.get('asl')) if x)
            if sub:
                ax.text(lab_x, lab_y[n] - span * 0.0155, sub, ha=ha, va='center',
                        color='#c9cfb6', fontsize=6.5, zorder=7,
                        path_effects=[withStroke(linewidth=2.4, foreground='#0b0d08')])

    sb = scale_hint or (500 if (xmax - xmin) > 2500 else 200)
    bx = xmin + (xmax - xmin) * 0.05
    by = ymin + span * 0.022
    ax.plot([bx, bx + sb], [by, by], color='white', lw=3, solid_capstyle='butt', zorder=8)
    for end in (bx, bx + sb):
        ax.plot([end, end], [by - span * 0.006, by + span * 0.006],
                color='white', lw=2, zorder=8)
    ax.text(bx + sb / 2, by + span * 0.011, '%d m' % sb, ha='center',
            color='white', fontsize=7.5, zorder=8)

    nx = xmax - (xmax - xmin) * 0.06
    ny = ymin + span * 0.016
    ax.annotate('', xy=(nx, ny + span * 0.050), xytext=(nx, ny),
                arrowprops=dict(arrowstyle='-|>', color='white', lw=2), zorder=8)
    ax.text(nx, ny - span * 0.014, 'N', ha='center', color='white',
            fontsize=9, fontweight='bold', zorder=8)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect('equal')
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color('#39402d')
    fig.tight_layout(pad=0.25)
    fig.savefig(path, facecolor=INK)
    plt.close(fig)
    return path


def main():
    global plt, withStroke
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True)
    ap.add_argument('--out', default='maps')
    ap.add_argument('--axis-file', help='JSON list of [lat, lon] for the road/river')
    ap.add_argument('--split', help='"1-3,4-6", or "auto", or omit for one map')
    ap.add_argument('--width', type=float, default=7.0)
    ap.add_argument('--height', type=float, default=8.6)
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as _plt
        from matplotlib.patheffects import withStroke as _ws
        plt, withStroke = _plt, _ws
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
    proj = projector(lat0)

    axis_xy = None
    if args.axis_file:
        with open(args.axis_file, encoding='utf-8') as f:
            pts = json.load(f)
        if isinstance(pts, dict):
            pts = pts.get('points') or pts.get('coordinates')
        axis_xy = [proj(p[0], p[1]) for p in pts]

    groups = parse_split(args.split, sectors)
    written = []
    for i, ids in enumerate(groups, 1):
        # Labels go on whichever side keeps them clear of the pins: sectors east of
        # the group's centre get right-hand labels, the rest go left.
        chosen = [s for s in sectors if s['n'] in ids]
        mid = sum(s['lon'] for s in chosen) / len(chosen)
        right = {s['n'] for s in chosen if s['lon'] >= mid}
        name = 'map_%d.png' % i if len(groups) > 1 else 'map.png'
        path = os.path.join(args.out, name)
        draw(path, sectors, ids, axis_xy, proj, right, args.width, args.height)
        written.append({'image': path, 'sectors': ids})

    notes = []
    if not axis_xy:
        notes.append('No --axis-file, so no valley line is drawn; every sector is still '
                     'placed correctly.')
    notes.append('Look at each map. The label placer spreads labels vertically but cannot '
                 'solve every collision; split a dense cluster into its own map with --split.')
    print(json.dumps({'ok': True, 'maps': written, 'notes': notes,
                      'next_step': 'Add each image to "maps" in crag.json (path relative to '
                                   'the crag folder) with kicker, title, caption and sectors.'},
                     indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
