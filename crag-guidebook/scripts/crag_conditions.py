#!/usr/bin/env python3
"""
crag_conditions.py — work out which way each sector faces, and when the sun hits it.

Guidebooks almost never publish aspect or sun/shade times, yet it is the single
most useful thing to know when planning a day. This derives both from geometry.

Two steps:

  1. AXIS. A gorge, valley or escarpment has a line running through it. A cliff on
     one side of that line faces across it, so if you know the line and which side
     a sector sits on, you know its aspect. The line comes from the road or river
     centreline (best), or is fitted through the sector coordinates themselves
     (fallback — see --axis auto).

  2. SUN. Solar azimuth and elevation are computed for the target date, then a wall
     is "in the sun" when the sun is within --arc degrees of its aspect AND high
     enough to clear the far side of the valley (--horizon).

The horizon term matters more than people expect. An east-facing wall in a gorge
does not catch the sun at sunrise; it waits for the sun to climb over the ridge
opposite, often two hours later. Ignore it and every morning figure is wrong.

Usage
-----
  python3 scripts/crag_conditions.py --crag crag.json                  # writes back in place
  python3 scripts/crag_conditions.py --crag crag.json --axis auto      # no road data
  python3 scripts/crag_conditions.py --crag crag.json --axis file --axis-file axis.json
  python3 scripts/crag_conditions.py --crag crag.json --date 2026-06-15 --tz 2 --horizon 25

Writes `aspect`, `aspect_deg`, `bank`, `dist_to_axis_m`, `axis_bearing`, `sun`,
`sun_flat` and `aspect_confidence` onto every sector, plus a `conditions_meta` block
(sunrise, sunset, solar noon, method) so the guide can state its method honestly.
It never touches `shade_override`, `conditions_extra` or any prose: a first-hand
observation survives a rerun. Keep the axis file next to crag.json so this can be rerun.

Prints a JSON summary on stdout; warnings go to stderr and into "warnings".
"""

import argparse
import datetime
import json
import math
import sys

# ---------------------------------------------------------------- geometry

COMPASS = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
           'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']


def cardinal(deg):
    return COMPASS[int((deg + 11.25) % 360 // 22.5)]


def projector(lat0):
    """Local equirectangular projection, metres. Fine over a few km."""
    mlat = 111132.0
    mlon = 111320.0 * math.cos(math.radians(lat0))
    return lambda lat, lon: (lon * mlon, lat * mlat)


def principal_axis(points):
    """Direction of greatest spread, oriented northwards. points = [(x, y), ...]"""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    syy = sum((p[1] - my) ** 2 for p in points)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    th = 0.5 * math.atan2(2 * sxy, sxx - syy)
    dx, dy = math.cos(th), math.sin(th)
    if dy < 0:
        dx, dy = -dx, -dy
    return (mx, my), (dx, dy)


def smoothed_tangent(axis, i, window):
    """
    Local direction of the axis near vertex i, fitted over every vertex within
    `window` metres. Raw segment bearings swing wildly on switchbacks and would
    hand you a different aspect for two sectors fifty metres apart; the fit
    averages that out.
    """
    cx, cy = axis[i]
    near = [p for p in axis if math.hypot(p[0] - cx, p[1] - cy) <= window]
    if len(near) < 3:
        near = axis[max(0, i - 3): i + 4]
    if len(near) < 2:
        return (0.0, 1.0)
    return principal_axis(near)[1]


def nearest_on_axis(axis, px, py, window):
    """Closest point on the polyline, plus the smoothed tangent and side there."""
    best = (float('inf'), 0.0, 0.0, 0)
    if len(axis) < 2:
        raise ValueError('axis needs at least two distinct points')
    for i in range(len(axis) - 1):
        ax, ay = axis[i]
        bx, by = axis[i + 1]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 == 0:
            continue
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
        cx, cy = ax + t * dx, ay + t * dy
        d = math.hypot(px - cx, py - cy)
        if d < best[0]:
            best = (d, cx, cy, i)
    d, cx, cy, i = best
    tx, ty = smoothed_tangent(axis, i, window)
    cross = tx * (py - cy) - ty * (px - cx)      # >0 = left of northward travel = west
    bearing = math.degrees(math.atan2(tx, ty)) % 360
    return d, cross, bearing


# ---------------------------------------------------------------- solar

def sun_position(when, lat, lon, tz):
    """Azimuth (deg from N, clockwise) and elevation (deg) for a naive local time."""
    utc = when - datetime.timedelta(hours=tz)
    jd = (utc.toordinal() + 1721424.5
          + (utc.hour + utc.minute / 60 + utc.second / 3600) / 24.0)
    n = jd - 2451545.0
    mean_lon = (280.460 + 0.9856474 * n) % 360
    anomaly = math.radians((357.528 + 0.9856003 * n) % 360)
    ecliptic = math.radians((mean_lon + 1.915 * math.sin(anomaly)
                             + 0.020 * math.sin(2 * anomaly)) % 360)
    obliquity = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(obliquity) * math.sin(ecliptic), math.cos(ecliptic))
    dec = math.asin(math.sin(obliquity) * math.sin(ecliptic))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    lst = math.radians((gmst * 15 + lon) % 360)
    ha = lst - ra
    la = math.radians(lat)
    el = math.asin(math.sin(la) * math.sin(dec)
                   + math.cos(la) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha),
                    math.tan(dec) * math.cos(la) - math.sin(la) * math.cos(ha))
    return math.degrees(az) % 360, math.degrees(el)


def sun_track(date, lat, lon, tz, step_min=5):
    out = []
    t = datetime.datetime.combine(date, datetime.time(3, 0))
    end = datetime.datetime.combine(date, datetime.time(22, 0))
    while t <= end:
        az, el = sun_position(t, lat, lon, tz)
        out.append((t, az, el))
        t += datetime.timedelta(minutes=step_min)
    return out


def lit_window(track, aspect, horizon, arc):
    """First and last sample where the wall is in direct sun. None if never."""
    on = [t for t, az, el in track
          if el > horizon and abs((az - aspect + 180) % 360 - 180) < arc]
    if not on:
        return None
    return [on[0].strftime('%H:%M'), on[-1].strftime('%H:%M')]


# ---------------------------------------------------------------- axis sources

def axis_from_file(path, project):
    pts = json.load(open(path))
    if isinstance(pts, dict):
        pts = pts.get('points') or pts.get('coordinates')
    return [project(p[0], p[1]) for p in pts]


def axis_from_osm(bbox, name_match, project):
    """
    Try to pull a road/river centreline straight from OpenStreetMap.

    This is often blocked by egress policy in sandboxed environments. When it
    fails, fetch the same URL from a browser that does have access, save the
    node list as JSON and pass it with --axis-file. See references/sources.md.
    """
    import urllib.request
    import xml.etree.ElementTree as ET
    url = ('https://www.openstreetmap.org/api/0.6/map?bbox=%s' % bbox)
    req = urllib.request.Request(url, headers={'User-Agent': 'crag-guidebook/1.0'})
    with urllib.request.urlopen(req, timeout=40) as r:
        root = ET.fromstring(r.read())
    nodes = {n.get('id'): (float(n.get('lat')), float(n.get('lon')))
             for n in root.iter('node')}
    picked = []
    for w in root.iter('way'):
        tags = {t.get('k'): t.get('v') for t in w.iter('tag')}
        if not (tags.get('highway') or tags.get('waterway')):
            continue
        if name_match and name_match not in (tags.get('name') or ''):
            continue
        picked += [nodes[nd.get('ref')] for nd in w.iter('nd') if nd.get('ref') in nodes]
    if not picked:
        raise ValueError('no matching way found in the bbox; widen it or drop --axis-name')
    picked.sort(key=lambda p: p[0])
    thinned, last = [], None
    for p in picked:
        if last is None or abs(p[0] - last) > 0.00035:
            thinned.append(p)
            last = p[0]
    return [project(p[0], p[1]) for p in thinned]


def axis_from_sectors(sector_pts, smooth_n=5):
    """
    Fallback with no road data: trace a centreline through the sectors themselves.

    A single straight fit is not good enough for anything that bends — on a
    meandering gorge it gets barely half the banks right, because one line cannot
    follow five kilometres of switchbacks. So instead: order the sectors along the
    overall trend, treat that ordered sequence as a rough centreline, and run a
    moving average over it. Sectors sit alternately on either bank, so the raw
    sequence zigzags about the true centre and the smoothing averages that out.

    It is still a poorer input than a real road or river centreline, and it fails
    where sectors bunch heavily on one bank. Prefer real data when you can get it,
    and state in the guidebook which one you used.
    """
    origin, (dx, dy) = principal_axis(sector_pts)
    ordered = sorted(sector_pts,
                     key=lambda p: (p[0] - origin[0]) * dx + (p[1] - origin[1]) * dy)

    def straight():
        span = max([abs((p[0] - origin[0]) * dx + (p[1] - origin[1]) * dy)
                    for p in sector_pts] + [500.0]) * 1.3
        return [(origin[0] - dx * span, origin[1] - dy * span),
                (origin[0] + dx * span, origin[1] + dy * span)]

    # Smoothing needs enough points to average over. With only a handful of
    # sectors every window would cover the whole set, collapsing the polyline to
    # a single point, so fall back to the straight principal axis instead.
    if len(ordered) < 6:
        return straight()

    half = max(1, min(smooth_n // 2, (len(ordered) - 1) // 3))
    smoothed = []
    for i in range(len(ordered)):
        lo, hi = max(0, i - half), min(len(ordered), i + half + 1)
        window = ordered[lo:hi]
        smoothed.append((sum(p[0] for p in window) / len(window),
                         sum(p[1] for p in window) / len(window)))

    # extend past the end sectors so the first and last still project onto a segment
    def extend(a, b, dist=400.0):
        vx, vy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(vx, vy)
        if n < 1e-9:
            return (a[0] - dx * dist, a[1] - dy * dist)
        return (a[0] - vx / n * dist, a[1] - vy / n * dist)

    line = ([extend(smoothed[0], smoothed[1])] + smoothed
            + [extend(smoothed[-1], smoothed[-2])])

    # Heavily clustered sectors can still smooth down to near-nothing; a polyline
    # with no length cannot tell you which side anything is on.
    total = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
    return line if total > 50.0 else straight()


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True, help='crag JSON (modified in place)')
    ap.add_argument('--axis', default='auto', choices=['auto', 'file', 'osm'],
                    help='where the valley/gorge centreline comes from')
    ap.add_argument('--axis-file', help='JSON list of [lat, lon] along the centreline')
    ap.add_argument('--axis-bbox', help='minlon,minlat,maxlon,maxlat for --axis osm')
    ap.add_argument('--axis-name', default='', help='substring of the way name to keep')
    ap.add_argument('--date', help='YYYY-MM-DD (default: 15th of the crag month)')
    ap.add_argument('--tz', type=float, help='UTC offset in hours at that date')
    ap.add_argument('--horizon', type=float,
                    help='elevation the sun must clear, degrees. 0-5 open crag, '
                         '20-30 deep narrow gorge, 10-15 broad valley')
    ap.add_argument('--arc', type=float, default=88.0,
                    help='half-angle either side of the aspect counted as sunlit')
    ap.add_argument('--smooth', type=float, default=260.0,
                    help='metres over which the axis tangent is averaged')
    ap.add_argument('--out', help='write here instead of back into --crag')
    args = ap.parse_args()

    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    meta = crag.setdefault('crag', {})
    sectors = crag['sectors']
    if not sectors:
        print(json.dumps({'ok': False, 'error': 'no sectors in the crag file'}))
        return 2

    tz = args.tz if args.tz is not None else meta.get('tz_offset', 0)
    horizon = args.horizon if args.horizon is not None else meta.get('horizon_deg', 20)
    if args.date:
        date = datetime.date.fromisoformat(args.date)
    elif meta.get('conditions_date'):
        date = datetime.date.fromisoformat(meta['conditions_date'])
    else:
        date = datetime.date(datetime.date.today().year,
                             meta.get('month', datetime.date.today().month), 15)

    lat0 = sum(s['lat'] for s in sectors) / len(sectors)
    lon0 = sum(s['lon'] for s in sectors) / len(sectors)
    project = projector(lat0)
    pts = [project(s['lat'], s['lon']) for s in sectors]

    if args.axis == 'file':
        if not args.axis_file:
            print(json.dumps({'ok': False, 'error': '--axis file needs --axis-file'}))
            return 2
        axis = axis_from_file(args.axis_file, project)
        axis_desc = 'centreline from %s' % args.axis_file
    elif args.axis == 'osm':
        if not args.axis_bbox:
            print(json.dumps({'ok': False, 'error': '--axis osm needs --axis-bbox'}))
            return 2
        try:
            axis = axis_from_osm(args.axis_bbox, args.axis_name, project)
            axis_desc = 'OpenStreetMap centreline (%s)' % (args.axis_name or 'ways in bbox')
        except Exception as exc:                                   # noqa: BLE001
            print(json.dumps({'ok': False, 'error': 'OSM fetch failed: %s' % exc,
                              'next_step': 'Fetch the same URL in a browser, save the '
                              'centreline as a JSON list of [lat, lon] and rerun with '
                              '--axis file --axis-file; see references/sources.md.'}))
            return 2
    else:
        axis = axis_from_sectors(pts)
        axis_desc = 'line fitted through the sector coordinates (no road data)'

    track = sun_track(date, lat0, lon0, tz)
    up = [s for s in track if s[2] > 0]
    noon = max(track, key=lambda s: s[2])

    manual = 0
    for s, (px, py) in zip(sectors, pts):
        dist, cross, bearing = nearest_on_axis(axis, px, py, args.smooth)
        west = cross > 0
        aspect = (bearing + 90) % 360 if west else (bearing - 90) % 360

        # An escape hatch for when you simply know: a stated aspect from a source,
        # or your own eyes on satellite imagery, beats any amount of geometry.
        if s.get('aspect_manual') is not None:
            aspect = float(s['aspect_manual'])
            west = None
            manual += 1

        s['aspect_deg'] = round(aspect)
        s['aspect'] = cardinal(aspect)
        s['bank'] = ('stated' if west is None else ('West' if west else 'East'))
        s['dist_to_axis_m'] = round(dist)
        s['axis_bearing'] = round(bearing)
        s['sun'] = lit_window(track, aspect, horizon, args.arc)
        s['sun_flat'] = lit_window(track, aspect, 0.5, args.arc)

        # Which side of the line a sector falls on decides its aspect outright, so a
        # sector sitting almost on the line is a coin flip. Flag those rather than
        # presenting them as solid. A fitted axis (--axis auto) is uncertain
        # everywhere, not just near the line — measured against a real centreline it
        # put roughly one sector in six on the wrong bank, and proximity did not
        # reliably predict which. So under --axis auto nothing is marked high.
        if s.get('aspect_manual') is not None:
            s['aspect_confidence'] = 'high'
        else:
            s['aspect_confidence'] = ('low' if (args.axis == 'auto' or dist < 12)
                                      else 'high')

    meta['conditions_meta'] = {
        'date': date.isoformat(),
        'tz_offset': tz,
        'horizon_deg': horizon,
        'arc_deg': args.arc,
        'smooth_m': args.smooth,
        'axis': axis_desc,
        'sunrise': up[0][0].strftime('%H:%M') if up else None,
        'sunset': up[-1][0].strftime('%H:%M') if up else None,
        'solar_noon': noon[0].strftime('%H:%M'),
        'max_elevation': round(noon[2], 1),
        'lat': round(lat0, 5),
        'lon': round(lon0, 5),
    }

    out = args.out or args.crag
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(crag, f, ensure_ascii=False, indent=1)

    warnings = []
    auto_derived = [s for s in sectors if s.get('aspect_manual') is None]
    if args.axis == 'auto' and len(auto_derived) < 4 and auto_derived:
        warnings.append('A line fitted through %d sector(s) lies through them, so which side '
                        'each is on is arbitrary and those aspects are not meaningful. Supply '
                        'a real centreline (--axis file) or set "aspect_manual" on each sector.'
                        % len(auto_derived))
    elif args.axis == 'auto':
        warnings.append('Every aspect is low confidence: the axis was fitted through the '
                        'sectors, not taken from a road or river. Against a real centreline '
                        'this put about one sector in six on the wrong bank. Get a real '
                        'centreline (references/sources.md) or check each sector on imagery.')
    else:
        unsure = [s['name'] for s in sectors if s['aspect_confidence'] == 'low']
        if unsure:
            warnings.append('Within 12 m of the axis, so the bank (and aspect) is not well '
                            'determined: ' + ', '.join(unsure))
    overrides = [s['name'] for s in sectors if s.get('shade_override')]
    for w in warnings:
        print('WARNING: ' + w, file=sys.stderr)

    print(json.dumps({
        'ok': True, 'written': out, 'conditions_meta': meta['conditions_meta'],
        'stated_aspects': manual,
        'sectors': [{'n': s.get('n'), 'name': s['name'], 'bank': s['bank'],
                     'aspect': s['aspect'], 'aspect_deg': s['aspect_deg'],
                     'dist_to_axis_m': s['dist_to_axis_m'], 'sun': s['sun'],
                     'confidence': s['aspect_confidence'],
                     'observed_override_kept': bool(s.get('shade_override'))}
                    for s in sectors],
        'overrides_kept': overrides,
        'warnings': warnings,
        'next_step': 'Cross-check against every source that states conditions directly '
                     '("sunny until midday", "afternoon sector"). If one disagrees, find '
                     'out which is wrong before printing.'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
