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
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

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
        'verify_guide.py', 'parse_guide_pdf.py', 'photo_gps.py', 'attach_images.py']


def run(script, *args, py=PY):
    p = subprocess.run([py, os.path.join(SCRIPTS, script)] + list(args),
                       capture_output=True, text=True)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = None
    return p.returncode, out, p


def has(mod, py=PY):
    if py == PY:
        return importlib.util.find_spec(mod) is not None
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
        i4 = next(c for c in v['checks'] if c['name'] == 'I4_local_names')
        self.assertIn(str(EXP['local_tally']).replace('"', "'"), i4['detail'])

    def test_verify_catches_errors(self):
        out = self.build_html()
        bad = json.loads(json.dumps(self.crag))
        bad['sectors'][2]['field_notes'] = ['invented']        # not in the built guide
        bad['crag']['spine_total'] = 13
        bp = os.path.join(self.tmp, 'bad.json')
        with open(bp, 'w', encoding='utf-8') as f:
            json.dump(bad, f)
        code, v, _ = run('verify_guide.py', '--guide', out['html'], '--crag', bp)
        self.assertEqual(code, 1)
        failed = {c['name'] for c in v['checks'] if not c['pass']}
        self.assertTrue({'I6_field_notes', 'I1_route_total'} <= failed, failed)

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
                           os.path.join(self.tmp, 'maps'))
        if not has('matplotlib'):
            self.assertEqual((code, out['missing']), (3, 'matplotlib'))
            return
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out['maps'][0]['image']))

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
