#!/usr/bin/env python3
"""
Fixture tests for the crag-guidebook skill (standard library only; used by CI).

Runs every script on the synthetic crag in crag-guidebook/examples/ and compares the
results with tests/expected.json, whose values were derived by hand.

  python3 tests/run_tests.py            # all tests; optional-dependency tests skip
  CRAG_PDF_PYTHON=/path/to/python python3 tests/run_tests.py
                                         # run the PDF + mode-C round trip with an
                                         # interpreter that has WeasyPrint and PyMuPDF
"""
import csv
import http.server
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, 'crag-guidebook')
SCRIPTS = os.path.join(SKILL, 'scripts')
EXAMPLES = os.path.join(SKILL, 'examples')
with open(os.path.join(ROOT, 'tests', 'expected.json'), encoding='utf-8') as _f:
    EXP = json.load(_f)
PY = sys.executable
PY_PDF = os.environ.get('CRAG_PDF_PYTHON', PY)

sys.path.insert(0, SCRIPTS)
import guide_style as gs                                           # noqa: E402

CLIS = ['crag_conditions.py', 'make_maps.py', 'export_geo.py', 'build_guide.py',
        'verify_guide.py', 'parse_guide_pdf.py', 'photo_gps.py', 'attach_images.py',
        'fetch_topos.py']


def run(script, *args, py=PY):
    p = subprocess.run([py, os.path.join(SCRIPTS, script)] + list(args),
                       capture_output=True, text=True)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = None
    return p.returncode, out, p


def has(mod, py=PY):
    # import for real: a package can be installed but unusable (e.g. WeasyPrint without a
    # loadable pango, as on an x86_64 Python next to arm64 Homebrew libraries)
    if py == PY and importlib.util.find_spec(mod) is None:
        return False
    return subprocess.run([py, '-c', 'import ' + mod], capture_output=True).returncode == 0


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='crag-test-')
        self.ex = os.path.join(self.tmp, 'ex')
        shutil.copytree(EXAMPLES, self.ex)
        self.crag_path = os.path.join(self.ex, 'crag.json')
        with open(self.crag_path, encoding='utf-8') as f:
            self.crag = json.load(f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ------------------------------------------------------------ basics
    def test_help(self):
        for s in CLIS:
            p = subprocess.run([PY, os.path.join(SCRIPTS, s), '--help'], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, s + p.stderr)
            self.assertIn('usage', p.stdout.lower(), s)

    def test_fixture_counts(self):
        counts = {str(s['n']): len(s['routes']) for s in self.crag['sectors']}
        self.assertEqual(counts, EXP['routes_per_sector'])
        self.assertEqual(sum(counts.values()), EXP['routes_total'])

    # ------------------------------------------------------------ shade rule (F1, I3)
    def test_headlines(self):
        meta = self.crag['crag']
        for s in self.crag['sectors']:
            h = gs.shade_headline(s, meta)
            self.assertEqual(h, EXP['headlines'][str(s['n'])])
            self.assertIn('Shade', h)
            self.assertNotRegex(h, r'Sun \d\d:\d\d')

    def test_shade_complement(self):
        sr, ss = gs.daylight(self.crag['crag'])
        D = gs.to_min(ss) - gs.to_min(sr)
        self.assertEqual(D, EXP['daylight_min'])
        for s in self.crag['sectors']:
            if s.get('sun'):
                a, b = (gs.to_min(t) for t in s['sun'])
                self.assertEqual((a - gs.to_min(sr)) + (gs.to_min(ss) - b) + (b - a), D)

    def test_shade_edge_cases(self):
        self.assertEqual(gs.shade_parts(['07:05', '18:55'], '07:00', '19:00'), (None, None))
        self.assertIn('Shade', gs.shade_headline({'sun': ['07:05', '18:55']}, {}))
        self.assertEqual(gs.shade_parts(['07:00', '12:00'], '07:00', '19:00'), ('after 12:00', None))
        self.assertEqual(gs.shade_parts(None, '07:00', '19:00'), ('all day', None))

    # ------------------------------------------------------------ build (HTML fallback)
    def build_html(self):
        code, out, p = run('build_guide.py', '--crag', self.crag_path,
                           '--out', os.path.join(self.tmp, 'guide.pdf'), '--force-html')
        self.assertEqual(code, 0, p.stderr)
        return out

    def test_html_fallback(self):
        out = self.build_html()
        self.assertEqual(out['renderer'], 'html')
        self.assertIsNone(out['pdf'])
        self.assertIn('Save as PDF', out['print_steps'])
        with open(out['html'], encoding='utf-8') as f:
            doc = f.read()
        self.assertIn('Topo and photo credits', doc)            # on the "Sources" page
        self.assertIn('A. Visitor, 2026-06-01 · own photo', doc)  # licence added to caption
        self.assertNotRegex(doc, r'(src|href)\s*=\s*["\'](https?:)?//')
        self.assertEqual(doc.count('<img src="data:'), EXP['images_wanted'])
        self.assertIn('<style>', doc)
        self.assertNotIn('<link', doc)

    def test_verify_html_passes(self):
        out = self.build_html()
        code, v, p = run('verify_guide.py', '--guide', out['html'], '--crag', self.crag_path)
        failed = [c for c in v['checks'] if not c['pass']]
        self.assertEqual(code, 0, failed)
        self.assertTrue(v['all_pass'])
        self.assertEqual(len(v['warnings']), 3)                 # 2 personal use + 1 own photo
        i4 = next(c for c in v['checks'] if c['name'] == 'I4_local_names')
        self.assertIn(str(EXP['local_tally']).replace('"', "'"), i4['detail'])

    def test_verify_catches_errors(self):
        out = self.build_html()
        bad = json.loads(json.dumps(self.crag))
        bad['sectors'][2]['field_notes'] = ['invented']        # not in the built guide
        bad['crag']['spine_total'] = 13
        del bad['sectors'][0]['topos'][0]['credit']
        bp = os.path.join(self.tmp, 'bad.json')
        with open(bp, 'w', encoding='utf-8') as f:
            json.dump(bad, f)
        code, v, _ = run('verify_guide.py', '--guide', out['html'], '--crag', bp)
        self.assertEqual(code, 1)
        failed = {c['name'] for c in v['checks'] if not c['pass']}
        self.assertTrue({'I6_field_notes', 'I1_route_total', 'image_credits'} <= failed, failed)

    def test_missing_image_refuses(self):
        self.crag['sectors'][0]['topos'].append({'image': 'topo/nope.png'})
        with open(self.crag_path, 'w', encoding='utf-8') as f:
            json.dump(self.crag, f)
        code, out, _ = run('build_guide.py', '--crag', self.crag_path,
                           '--out', os.path.join(self.tmp, 'g.pdf'), '--force-html')
        self.assertEqual(code, 2)
        self.assertFalse(out['ok'])
        self.assertEqual(out['missing'], ['topo/nope.png'])

    # ------------------------------------------------------------ geo files
    def test_export_geo(self):
        code, out, p = run('export_geo.py', '--crag', self.crag_path, '--out', self.tmp,
                           '--slug', 'test')
        self.assertEqual(code, 0, p.stderr)
        self.assertEqual(out['parking_pins'], EXP['parking_pins'])
        kml = ET.parse(out['files']['kml'])
        marks = kml.getroot().iter('{http://www.opengis.net/kml/2.2}Placemark')
        self.assertEqual(len(list(marks)), 4 + EXP['parking_pins'])
        ET.parse(out['files']['gpx'])
        with open(out['files']['csv'], encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual({r['n']: r['shade'] for r in rows}, EXP['csv_shade'])
        self.assertEqual(rows[0]['calc_sun_from'], '09:00')
        with open(out['files']['kml'], encoding='utf-8') as f:
            self.assertNotRegex(f.read(), r'Sun \d\d:\d\d')

    # ------------------------------------------------------------ conditions
    def test_conditions_keeps_override(self):
        code, out, p = run('crag_conditions.py', '--crag', self.crag_path, '--axis', 'file',
                           '--axis-file', os.path.join(self.ex, 'axis.json'))
        self.assertEqual(code, 0, p.stderr)
        got = {str(s['n']): s['aspect_deg'] for s in out['sectors']}
        self.assertEqual(got, EXP['aspects_after_axis'])
        with open(self.crag_path, encoding='utf-8') as f:
            after = json.load(f)
        self.assertEqual(after['sectors'][3]['shade_override'],
                         self.crag['sectors'][3]['shade_override'])
        self.assertEqual(after['sectors'][1]['field_notes'], self.crag['sectors'][1]['field_notes'])
        self.assertIsNone(next(s for s in out['sectors'] if s['n'] == 3)['sun'])

    # ------------------------------------------------------------ images
    def test_attach_images_idempotent(self):
        code, out, _ = run('attach_images.py', '--crag', self.crag_path,
                           '--credit', 'web=Topo — community site (free view)')
        self.assertEqual(code, 0)
        self.assertEqual([(a['sector'], a['image']) for a in out['added']], [(3, 'topo/web_03.png')])
        code, out, _ = run('attach_images.py', '--crag', self.crag_path)
        self.assertEqual(out['added'], [])

    def test_photo_gps(self):
        code, out, _ = run('photo_gps.py', os.path.join(self.ex, 'img', 'photo_02a.jpg'))
        if not has('PIL'):
            self.assertEqual((code, out['missing']), (3, 'Pillow'))
            return
        ph = out['photos'][0]
        for k, v in EXP['photo_gps'].items():
            self.assertAlmostEqual(ph[k], v, places=4)
        self.assertIn('plates', out['privacy'])

    def test_make_maps(self):
        code, out, _ = run('make_maps.py', '--crag', self.crag_path, '--out',
                           os.path.join(self.tmp, 'maps'), '--context', 'none')
        if not has('matplotlib'):
            self.assertEqual((code, out['missing']), (3, 'matplotlib'))
            return
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out['maps'][0]['image']))
        self.assertEqual(out['maps'][0]['context'], 'none')

    def test_make_maps_osm_context(self):
        if not has('matplotlib'):
            self.skipTest('matplotlib not available')
        lat, lon = self.crag['sectors'][0]['lat'], self.crag['sectors'][0]['lon']
        g = lambda pts: [{'lat': lat + a, 'lon': lon + b} for a, b in pts]
        ctx = {'elements': [
            {'type': 'way', 'tags': {'highway': 'tertiary'}, 'geometry': g([(-.002, -.003), (-.002, .003)])},
            {'type': 'way', 'tags': {'highway': 'path'}, 'geometry': g([(-.002, 0), (0, 0)])},
            {'type': 'way', 'tags': {'natural': 'cliff'}, 'geometry': g([(.0002, -.001), (.0002, .001)])},
            {'type': 'way', 'tags': {'natural': 'water'},
             'geometry': g([(-.003, -.001), (-.003, 0), (-.0035, 0), (-.003, -.001)])},
            {'type': 'way', 'tags': {'building': 'yes'}, 'geometry': g([(.001, .001), (.001, .0012), (.0012, .0012)])},
            {'type': 'node', 'tags': {'amenity': 'parking'}, 'lat': lat - .0018, 'lon': lon},
            {'type': 'way', 'tags': {'highway': 'proposed'}, 'geometry': g([(0, 0), (.001, .001)])}]}
        cf = os.path.join(self.tmp, 'ctx.json')
        with open(cf, 'w', encoding='utf-8') as f:
            json.dump(ctx, f)
        code, out, p = run('make_maps.py', '--crag', self.crag_path, '--out',
                           os.path.join(self.tmp, 'maps'), '--context', 'file', '--context-file', cf)
        self.assertEqual(code, 0, p.stderr)
        m = out['maps'][0]
        self.assertEqual(m['context'], 'file')
        self.assertEqual(m['context_features'], {'water': 1, 'building': 1, 'cliff': 1, 'path': 1,
                                                 'minor': 1, 'pnode': 1})   # 'proposed' ignored
        self.assertTrue(any('OpenStreetMap' in n for n in out['notes']))
        # the cliff runs W→E just north of sector 1, so its down-slope (right) side faces S
        chk = {c['sector']: c for c in m['cliff_check']}
        self.assertEqual(chk[1]['osm_cliff_facing'], 180)
        self.assertEqual(chk[1]['agrees'],
                         abs((180 - self.crag['sectors'][0]['aspect_deg'] + 180) % 360 - 180) <= 90)

    def test_source_override_wording(self):
        sec = next(s for s in self.crag['sectors'] if s.get('shade_override'))
        sec['shade_override']['kind'] = 'source'
        with open(self.crag_path, 'w', encoding='utf-8') as f:
            json.dump(self.crag, f)
        out = self.build_html()
        with open(out['html'], encoding='utf-8') as f:
            doc = f.read()
        self.assertIn('Calculation, superseded by the source statement above', doc)
        self.assertIn('calc., superseded by source', doc)
        self.assertIn('<span class="small">(source)</span>', doc)
        self.assertNotIn('contradicted by the observation above', doc)

    # ------------------------------------------------------------ PDF + mode C round trip
    def test_pdf_round_trip(self):
        if not (has('weasyprint', PY_PDF) and has('fitz', PY_PDF)):
            self.skipTest('WeasyPrint + PyMuPDF not available (set CRAG_PDF_PYTHON)')
        pdf = os.path.join(self.tmp, 'guide.pdf')
        code, out, p = run('build_guide.py', '--crag', self.crag_path, '--out', pdf, py=PY_PDF)
        self.assertEqual((code, out['renderer']), (0, 'weasyprint'), p.stderr)
        code, v, _ = run('verify_guide.py', '--guide', pdf, '--crag', self.crag_path, py=PY_PDF)
        self.assertTrue(v['all_pass'], [c for c in v['checks'] if not c['pass']])
        code, g, _ = run('export_geo.py', '--crag', self.crag_path, '--out', self.tmp, '--slug', 't')
        rb = os.path.join(self.tmp, 'rb', 'crag.json')
        code, r, p = run('parse_guide_pdf.py', '--pdf', pdf, '--out', rb,
                         '--geo-csv', g['files']['csv'], py=PY_PDF)
        self.assertEqual(code, 0, p.stdout + p.stderr)
        self.assertEqual({str(k): v for k, v in r['routes_per_sector'].items()},
                         EXP['routes_per_sector'])
        with open(rb, encoding='utf-8') as f:
            back = json.load(f)
        for sa, sb in zip(self.crag['sectors'], back['sectors']):
            self.assertEqual(sa['name'], sb['name'])
            for ra, rb_ in zip(sa['routes'], sb['routes']):
                for k in ('name', 'grade', 'length', 'local_name', 'note', 'xref', 'field_note'):
                    self.assertEqual(ra.get(k), rb_.get(k), (sa['n'], ra['n'], k))
                if not gs.is_top_pick(ra):
                    self.assertEqual(ra.get('stars'), rb_.get('stars'), (sa['n'], ra['n']))
                self.assertEqual(gs.local_src(ra), rb_.get('local_src'))
            for k in ('intro', 'gear', 'approach', 'walk', 'warn', 'field_notes', 'bolt_severity'):
                self.assertEqual(sa.get(k), sb.get(k), (sa['n'], k))
        self.assertIn('shade_override', back['sectors'][3])
        self.assertNotIn('conditions_extra', back['sectors'][2])   # generated text dropped


# ---------------------------------------------------------------- fetch_topos (offline)
# A local http.server stands in for Overpass, the Commons API and the thumbnail host.
# All data is invented: an imaginary crag in the open South Atlantic, invented file
# names and authors.

def tiny_png(w=40, h=30):
    raw = b''.join(b'\x00' + b'\x90\x80\x70' * w for _ in range(h))

    def chunk(t, d):
        return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


OSM_ELEMENTS = [
    {'type': 'node', 'id': 101, 'lat': -30.0001, 'lon': -20.0011,
     'tags': {'climbing': 'crag', 'name': 'Invented Slab',
              'wikimedia_commons': 'File:Invented_Slab_topo.jpg',
              'wikimedia_commons:2': 'File:Invented Slab NC.jpg'}},
    {'type': 'node', 'id': 102, 'lat': -30.0001, 'lon': -20.0012,
     'tags': {'climbing': 'route_bottom', 'name': 'Phantom Arete',
              'climbing:grade:french': '6a',
              'wikimedia_commons': 'File:Invented Slab topo.jpg',
              'wikimedia_commons:path': '0.2,0.9|0.25,0.5B:|0.3,0.1A'}},
    {'type': 'way', 'id': 103, 'center': {'lat': -30.0002, 'lon': -20.0013},
     'tags': {'climbing': 'route', 'name': 'Mirage',
              'wikimedia_commons': 'File:Invented Slab topo.jpg',
              'wikimedia_commons:path': '0.6,0.95|0.7,0.2A'}},
    {'type': 'node', 'id': 104, 'lat': -30.5, 'lon': -20.5,
     'tags': {'climbing': 'crag', 'name': 'Far Away Reef'}},
]

COMMONS_FILES = {
    'File:Invented Slab topo.jpg': {
        'url': '/img/full.png', 'thumburl': '/img/slab.png', 'thumbwidth': 40,
        'thumbheight': 30, 'descriptionurl': 'https://commons.example.invalid/wiki/Invented',
        'extmetadata': {'LicenseShortName': {'value': 'CC BY-SA 4.0'},
                        'Artist': {'value': '<a href="//x.invalid/U">Ima Ginary</a> &amp; co'}}},
    'File:Invented Slab NC.jpg': {
        'url': '/img/nc.png', 'thumburl': '/img/nc.png', 'thumbwidth': 40, 'thumbheight': 30,
        'descriptionurl': 'https://commons.example.invalid/wiki/NC',
        'extmetadata': {'LicenseShortName': {'value': 'CC BY-NC 4.0'},
                        'Artist': {'value': 'N. O. Body'}}},
}


class FakeWeb(http.server.BaseHTTPRequestHandler):
    log = []
    block = set()
    overload = set()

    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.end_headers()
        self.wfile.write(body)

    def handle_any(self, body=b''):
        u = urllib.parse.urlparse(self.path)
        FakeWeb.log.append((u.path, self.headers.get('User-Agent'), body))
        root = u.path.split('/')[1]
        if root in FakeWeb.block:
            return self.reply(403, b'Forbidden', 'text/plain')
        if root in FakeWeb.overload:
            return self.reply(504, b'Gateway Timeout', 'text/plain')
        if u.path == '/overpass':
            return self.reply(200, json.dumps({'elements': OSM_ELEMENTS}).encode())
        if u.path == '/commons':
            q = urllib.parse.parse_qs(body.decode() or u.query)
            pages = []
            for t in q['titles'][0].split('|'):
                ii = dict(COMMONS_FILES[t])
                ii['thumburl'] = 'http://127.0.0.1:%d%s' % (self.server.server_port, ii['thumburl'])
                pages.append({'title': t, 'imageinfo': [ii]})
            return self.reply(200, json.dumps({'query': {'pages': pages}}).encode())
        if u.path.startswith('/img/'):
            return self.reply(200, tiny_png(), 'image/png')
        self.reply(404, b'{}')

    def do_GET(self):
        self.handle_any()

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        self.handle_any(self.rfile.read(n))


class FetchTopos(unittest.TestCase):
    tearDown = Fixture.tearDown

    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(('127.0.0.1', 0), FakeWeb)
        cls.base = 'http://127.0.0.1:%d' % cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Fixture.setUp(self)
        FakeWeb.log, FakeWeb.block, FakeWeb.overload = [], set(), set()

    def ft(self, *args):
        return run('fetch_topos.py', *(list(args) + ['--delay', '0', '--timeout', '5',
                                                     '--overpass-url', self.base + '/overpass',
                                                     '--commons-api', self.base + '/commons']))

    def find(self):
        code, out, p = self.ft('find', '--lat', '-30.0', '--lon', '-20.001', '--radius', '500')
        self.assertEqual(code, 0, p.stdout + p.stderr)
        path = os.path.join(self.tmp, 'osm.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(out, f)
        return out, path

    def test_help_names_subcommands(self):
        _, _, p = run('fetch_topos.py', '--help')
        self.assertIn('find', p.stdout)
        self.assertIn('fetch', p.stdout)

    def test_find(self):
        out, _ = self.find()
        self.assertEqual((out['status'], out['count'], out['with_images']), ('ok', 4, 3))
        self.assertIn('around:500,-30.000000,-20.001000', out['query'])
        self.assertIn('[bbox:-30.004499,', out['query'])        # 500 m / 111132 m per degree
        o = {x['osm']: x for x in out['objects']}
        self.assertEqual(o['node/101']['images'][0]['file'], 'File:Invented Slab topo.jpg')
        self.assertEqual(o['node/101']['images'][1]['key'], 'wikimedia_commons:2')
        self.assertEqual(o['node/102']['images'][0]['path'], '0.2,0.9|0.25,0.5B:|0.3,0.1A')
        self.assertEqual(o['node/102']['grade'], '6a')
        self.assertEqual((o['way/103']['lat'], o['way/103']['lon']), (-30.0002, -20.0013))
        self.assertEqual([x['osm'] for x in out['objects']][:2], ['node/101', 'node/104'])
        self.assertTrue(FakeWeb.log[0][1].startswith('crag-guidebook/1.2 ('))

    def test_fetch_entries_and_credits(self):
        _, osm = self.find()
        code, out, p = self.ft('fetch', '--objects', osm, '--crag', self.crag_path,
                               '--date', '2026-10-01')
        self.assertEqual(code, 0, p.stdout + p.stderr)
        self.assertEqual([(a['sector'], a['image'], a['lines']) for a in out['added']],
                         [(1, 'topo/osm_01a.png', 2)])
        self.assertEqual(out['skipped'][0]['licence'], 'CC BY-NC 4.0')   # NC needs consent
        self.assertEqual(out['unassigned'], [])                  # node/104 has no image
        with open(self.crag_path, encoding='utf-8') as f:
            t = json.load(f)['sectors'][0]['topos'][-1]
        self.assertEqual(t['caption'], 'Topo — Invented Slab · Ima Ginary & co · CC BY-SA 4.0 '
                                       '· Wikimedia Commons')
        self.assertEqual((t['credit'], t['licence'], t['retrieved'], t['size']),
                         ('Ima Ginary & co', 'CC BY-SA 4.0', '2026-10-01', [40, 30]))
        self.assertEqual(t['source'], 'Wikimedia Commons via OpenStreetMap (node/101)')
        self.assertEqual(t['source_url'], 'https://commons.example.invalid/wiki/Invented')
        pts = t['lines'][0]['points']
        self.assertEqual(pts[1], {'x': 0.25, 'y': 0.5, 'type': 'bolt'})
        self.assertEqual(pts[2], {'x': 0.3, 'y': 0.1, 'type': 'anchor', 'dotted_before': True})
        self.assertTrue(os.path.exists(os.path.join(self.ex, 'topo', 'osm_01a.png')))
        self.assertTrue(os.path.exists(os.path.join(self.ex, 'topo', 'osm_01a.lines.svg')))
        self.assertTrue(all(ua.startswith('crag-guidebook/1.2') for _, ua, _ in FakeWeb.log))
        # personal use only with consent
        code, out, _ = self.ft('fetch', '--objects', osm, '--crag', self.crag_path,
                               '--allow-personal-use', '--select', 'node/101')
        self.assertEqual([a['image'] for a in out['added']], ['topo/osm_01b.png'])
        self.assertEqual(out['skipped'][0]['reason'], 'already attached to sector 1')
        with open(self.crag_path, encoding='utf-8') as f:
            self.assertTrue(json.load(f)['sectors'][0]['topos'][-1]['caption']
                            .endswith('CC BY-NC 4.0 · Wikimedia Commons (personal use)'))
        # the built guide draws the lines and lists the credit; verify passes
        code, b, p = run('build_guide.py', '--crag', self.crag_path,
                         '--out', os.path.join(self.tmp, 'g.pdf'), '--force-html')
        self.assertEqual(code, 0, p.stdout)
        with open(b['html'], encoding='utf-8') as f:
            doc = f.read()
        self.assertIn('<svg class="tlines"', doc)
        self.assertIn('stroke-dasharray', doc)
        self.assertIn('Ima Ginary &amp; co · CC BY-SA 4.0', doc)
        self.assertIn('© OpenStreetMap contributors (ODbL)', doc)
        code, v, _ = run('verify_guide.py', '--guide', b['html'], '--crag', self.crag_path)
        self.assertTrue(v['all_pass'], [c for c in v['checks'] if not c['pass']])
        if has('weasyprint', PY_PDF) and has('fitz', PY_PDF):    # the overlay in the PDF
            pdf = os.path.join(self.tmp, 'o.pdf')
            code, b, p = run('build_guide.py', '--crag', self.crag_path, '--out', pdf, py=PY_PDF)
            self.assertEqual((code, b['renderer']), (0, 'weasyprint'), p.stdout + p.stderr)
            code, v, _ = run('verify_guide.py', '--guide', pdf, '--crag', self.crag_path, py=PY_PDF)
            self.assertTrue(v['all_pass'], [c for c in v['checks'] if not c['pass']])

    def test_unassigned_far_object(self):
        _, osm = self.find()
        OSM_ELEMENTS[3]['tags']['wikimedia_commons'] = 'File:Invented Slab topo.jpg'
        try:
            out, osm = self.find()
            code, out, _ = self.ft('fetch', '--objects', osm, '--crag', self.crag_path,
                                   '--select', 'node/104')
        finally:
            del OSM_ELEMENTS[3]['tags']['wikimedia_commons']
        self.assertEqual(code, 0)
        self.assertEqual(out['added'], [])
        self.assertEqual(out['unassigned'][0]['osm'], 'node/104')

    def test_blocked_stops(self):
        FakeWeb.block = {'overpass'}
        code, out, _ = self.ft('find', '--lat', '-30', '--lon', '-20')
        self.assertEqual((code, out['status'], out['detail']), (4, 'blocked', 'HTTP 403'))
        self.assertEqual(len(FakeWeb.log), 1)                    # no retries
        FakeWeb.block = set()
        _, osm = self.find()
        FakeWeb.block = {'commons'}
        FakeWeb.log = []
        with open(self.crag_path, encoding='utf-8') as f:
            before = f.read()
        code, out, _ = self.ft('fetch', '--objects', osm, '--crag', self.crag_path)
        self.assertEqual((code, out['status']), (4, 'blocked'))
        self.assertEqual(len(FakeWeb.log), 1)
        with open(self.crag_path, encoding='utf-8') as f:
            self.assertEqual(f.read(), before)

    def test_maps_blocked_stops(self):
        if not has('matplotlib'):
            self.skipTest('matplotlib not available')
        FakeWeb.block = {'overpass'}
        code, out, _ = run('make_maps.py', '--crag', self.crag_path, '--out',
                           os.path.join(self.tmp, 'maps'), '--split', '1-2,3-4',
                           '--overpass-url', self.base + '/overpass', '--delay', '0', '--timeout', '5')
        self.assertEqual(code, 0)
        self.assertEqual(out['context_stopped']['status'], 'blocked')
        self.assertEqual([m['context'] for m in out['maps']], ['unavailable', 'unavailable'])
        self.assertEqual(len(FakeWeb.log), 1)                    # no retry, no mirror after a block

    def test_maps_overload_continues(self):
        if not has('matplotlib'):
            self.skipTest('matplotlib not available')
        FakeWeb.overload = {'overpass'}
        code, out, _ = run('make_maps.py', '--crag', self.crag_path, '--out',
                           os.path.join(self.tmp, 'maps'), '--split', '1-2,3-4', '--no-mirrors',
                           '--overpass-url', self.base + '/overpass', '--delay', '0', '--timeout', '5')
        self.assertEqual(code, 0)
        self.assertIsNone(out['context_stopped'])                # a 5xx is not a block
        self.assertEqual(len(out['context_failed']), 2)          # each map tried, none skipped
        self.assertEqual(len(FakeWeb.log), 2)
        FakeWeb.overload = set()                                 # server recovers: rerun fetches
        code, out, _ = run('make_maps.py', '--crag', self.crag_path, '--out',
                           os.path.join(self.tmp, 'maps'), '--split', '1-2,3-4', '--no-mirrors',
                           '--overpass-url', self.base + '/overpass', '--delay', '0', '--timeout', '5')
        self.assertEqual([m['context'] for m in out['maps']], ['fetched', 'fetched'])

    def test_offline(self):
        code, out, _ = run('fetch_topos.py', 'find', '--lat', '-30', '--lon', '-20',
                           '--delay', '0', '--timeout', '2',
                           '--overpass-url', 'http://127.0.0.1:9/overpass')
        self.assertEqual((code, out['status']), (4, 'offline'))

    def test_parse_path(self):
        sys.path.insert(0, SCRIPTS)
        import fetch_topos as ft
        self.assertEqual(ft.parse_path('0.1,0.2|0.3,0.4S|bad|0.5,0.6U:|0.7,0.8'),
                         [{'x': 0.1, 'y': 0.2}, {'x': 0.3, 'y': 0.4, 'type': 'sling'},
                          {'x': 0.5, 'y': 0.6, 'type': 'unfinished'},
                          {'x': 0.7, 'y': 0.8, 'dotted_before': True}])
        self.assertEqual(ft.parse_path(None), [])
        self.assertTrue(ft.personal_use_only('CC BY-NC-SA 4.0'))
        self.assertTrue(ft.personal_use_only(''))
        self.assertFalse(ft.personal_use_only('CC BY-SA 4.0'))
        self.assertFalse(ft.personal_use_only('Public domain'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
