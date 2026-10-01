#!/usr/bin/env python3
"""
export_geo.py — KML, GPX and CSV of the sectors.

The KML is how the reader gets satellite imagery. Importing it into Google My Maps
or opening it in Google Earth puts every sector on Google's own satellite layer as
a labelled pin, with grades, aspect and sun times in the info box — which is what
people actually want when they ask for "the crag on a satellite map", and it works
on a phone. A flat screenshot of a map cannot do any of that.

The GPX is the same waypoints for an offline phone GPS app. Worth having: mobile
signal at crags is unreliable, and that is exactly when you want the coordinates.

The CSV is for anyone who wants the numbers in a spreadsheet, and carries a
ready-made Google Maps link per sector.

Shade text comes from guide_style.py (the same F1 rule the guide prints), so the
map files, the CSV and the PDF never disagree. An observed shade_override wins.

Usage
-----
  python3 scripts/export_geo.py --crag crag.json --out . --slug my-crag

Prints a JSON summary on stdout (paths, sector and parking counts).
"""

import argparse
import csv
import json
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_style as gs                                           # noqa: E402

PIN_ICON = 'http://maps.google.com/mapfiles/kml/paddle/red-circle.png'
PARK_ICON = 'http://maps.google.com/mapfiles/kml/shapes/parking_lot.png'


def describe(s, month_label, meta):
    bits = []
    if s.get('routes_count'):
        head = '%s routes' % s['routes_count']
        if s.get('grades'):
            head += ' · %s' % s['grades']
        if s.get('height'):
            head += ' · up to %s' % s['height']
        bits.append('<b>%s</b>' % escape(head))
    if s.get('aspect'):
        conf = ' (approximate)' if s.get('aspect_confidence') == 'low' else ''
        bits.append('Aspect: %s (%s°)%s' % (s['aspect'], s.get('aspect_deg', '?'), conf))
    bits.append('%s (%s, approx.)' % (escape(gs.shade_text(s, meta)), escape(month_label or '')))
    if s.get('asl'):
        bits.append('Altitude: %s' % escape(s['asl']))
    if s.get('bolt_status'):
        bits.append('Bolts: %s' % escape(str(s['bolt_status'])))
    if s.get('ticks') is not None:
        bits.append('Logged ascents: %s' % s['ticks'])
    if s.get('approach'):
        bits.append('<br>%s' % escape(s['approach']))
    return '<![CDATA[%s]]>' % '<br>'.join(bits)


def write_kml(path, crag, sectors):
    meta = crag.get('crag', {})
    name = meta.get('name', 'Crag')
    month = gs.month_label(meta)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>',
           '<name>%s — climbing sectors</name>' % escape(name),
           '<description>%s</description>' % escape(
               '%d sectors. Switch the base map to satellite. '
               'Coordinates and route data from the sources listed in the guidebook.'
               % len(sectors)),
           '<Style id="sec"><IconStyle><scale>1.15</scale>'
           '<Icon><href>%s</href></Icon></IconStyle>'
           '<LabelStyle><scale>0.9</scale></LabelStyle></Style>' % PIN_ICON,
           '<Style id="park"><IconStyle><scale>0.9</scale>'
           '<Icon><href>%s</href></Icon></IconStyle>'
           '<LabelStyle><scale>0.7</scale></LabelStyle></Style>' % PARK_ICON,
           '<Folder><name>Sectors</name>']
    for s in sectors:
        label = '%s. %s' % (s['n'], s['name']) if s.get('n') else s['name']
        out.append('<Placemark><name>%s</name><styleUrl>#sec</styleUrl>'
                   '<description>%s</description>'
                   '<Point><coordinates>%.6f,%.6f,0</coordinates></Point></Placemark>'
                   % (escape(label), describe(s, month, meta), s['lon'], s['lat']))
    out.append('</Folder>')

    parks = [s for s in sectors if s.get('parking')]
    if parks:
        out.append('<Folder><name>Parking / path start</name>')
        for s in parks:
            p = s['parking']
            out.append('<Placemark><name>P — %s %s</name><styleUrl>#park</styleUrl>'
                       '<Point><coordinates>%.6f,%.6f,0</coordinates></Point></Placemark>'
                       % (s.get('n', ''), escape(s['name']), p[1], p[0]))
        out.append('</Folder>')

    for extra in crag.get('waypoints', []):
        out.append('<Placemark><name>%s</name><styleUrl>#park</styleUrl>'
                   '<Point><coordinates>%.6f,%.6f,0</coordinates></Point></Placemark>'
                   % (escape(extra['name']), extra['lon'], extra['lat']))

    out.append('</Document></kml>')
    open(path, 'w', encoding='utf-8').write('\n'.join(out))


def write_gpx(path, crag, sectors):
    meta = crag.get('crag', {})
    name = meta.get('name', 'Crag')
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<gpx version="1.1" creator="crag-guidebook" '
           'xmlns="http://www.topografix.com/GPX/1/1">',
           '<metadata><name>%s climbing sectors</name></metadata>' % escape(name)]
    for s in sectors:
        desc = '%s routes, %s. %s facing. %s' % (
            s.get('routes_count', '?'), s.get('grades', '?'),
            s.get('aspect', '?'), gs.shade_text(s, meta))
        out.append('<wpt lat="%.6f" lon="%.6f"><name>%s %s</name>'
                   '<desc>%s</desc><sym>Summit</sym></wpt>'
                   % (s['lat'], s['lon'], s.get('n', ''), escape(s['name']),
                      escape(desc)))
        if s.get('parking'):
            p = s['parking']
            out.append('<wpt lat="%.6f" lon="%.6f"><name>P %s %s</name>'
                       '<sym>Parking Area</sym></wpt>'
                       % (p[0], p[1], s.get('n', ''), escape(s['name'])))
    for extra in crag.get('waypoints', []):
        out.append('<wpt lat="%.6f" lon="%.6f"><name>%s</name>'
                   '<sym>Flag</sym></wpt>'
                   % (extra['lat'], extra['lon'], escape(extra['name'])))
    out.append('</gpx>')
    open(path, 'w', encoding='utf-8').write('\n'.join(out))


def write_csv(path, sectors, meta):
    cols = ['n', 'sector', 'local_name', 'lat', 'lon', 'parking_lat', 'parking_lon',
            'altitude', 'aspect', 'aspect_deg', 'aspect_confidence', 'bank',
            'calc_sun_from', 'calc_sun_to', 'shade', 'routes', 'routes_listed', 'grades', 'height', 'max_qd',
            'bolted', 'bolt_status', 'logged_ascents', 'google_maps']
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for s in sectors:
            sun = s.get('sun') or ('', '')
            p = s.get('parking') or ('', '')
            w.writerow([
                s.get('n', ''), s['name'], s.get('local_name', ''),
                '%.6f' % s['lat'], '%.6f' % s['lon'],
                ('%.6f' % p[0]) if p[0] != '' else '',
                ('%.6f' % p[1]) if p[1] != '' else '',
                s.get('asl', ''), s.get('aspect', ''), s.get('aspect_deg', ''),
                s.get('aspect_confidence', ''), s.get('bank', ''),
                sun[0], sun[1], gs.shade_text(s, meta), s.get('routes_count', ''),
                len(s.get('routes', [])), s.get('grades', ''),
                s.get('height', ''), s.get('qd', ''), s.get('bolted', ''),
                s.get('bolt_status', ''), s.get('ticks', ''),
                'https://www.google.com/maps/search/?api=1&query=%.6f,%.6f'
                % (s['lat'], s['lon'])])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True)
    ap.add_argument('--out', default='.')
    ap.add_argument('--slug', help='filename stem (default: from the crag name)')
    args = ap.parse_args()

    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    sectors = crag['sectors']
    slug = args.slug or (crag.get('crag', {}).get('name', 'crag')
                         .lower().replace(' ', '-'))
    os.makedirs(args.out, exist_ok=True)

    paths = {
        'kml': os.path.join(args.out, '%s-sectors.kml' % slug),
        'gpx': os.path.join(args.out, '%s-sectors.gpx' % slug),
        'csv': os.path.join(args.out, '%s-sectors.csv' % slug),
    }
    write_kml(paths['kml'], crag, sectors)
    write_gpx(paths['gpx'], crag, sectors)
    write_csv(paths['csv'], sectors, crag.get('crag', {}))

    import xml.etree.ElementTree as ET
    for kind in ('kml', 'gpx'):
        ET.parse(paths[kind])                     # fail loudly rather than ship broken XML
    print(json.dumps({
        'ok': True, 'files': paths, 'sectors': len(sectors),
        'parking_pins': sum(1 for s in sectors if s.get('parking')),
        'extra_waypoints': len(crag.get('waypoints', [])),
        'next_step': 'Tell the reader how to use the KML: Google My Maps → Create a new map '
                     '→ Import, or open it in Google Earth, then switch the base layer to '
                     'satellite. The GPX is for an offline phone GPS app.'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
