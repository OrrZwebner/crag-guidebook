#!/usr/bin/env python3
"""
attach_images.py — pick up topo and photo files by naming convention and add them to
each sector's `topos` list in crag.json. Idempotent: rerunning adds nothing twice.

Convention (relative to the crag folder):
    topo/<src>_<NN>[a|b|c].<ext>   a topo for sector NN from source <src>
    img/<src>_<NN>[a|b|c].<ext>    a photo of sector NN (added with "photo": true)
  e.g. topo/book_04.png, topo/web_03a.jpg, img/photo_02a.jpg
<src> is lower-case letters/digits; <ext> is jpg, jpeg, png, webp or gif.

So a topo found later (say, one that was blocked during collection) is dropped into
topo/ with the right name and appears on the next rebuild.

Usage
-----
  python3 scripts/attach_images.py --crag crag.json \\
      --credit "web=Topo — community site, freely viewable size; numbers match the table" \\
      --credit "book=Topo — from the printed guidebook (personal use)"
  python3 scripts/attach_images.py --crag crag.json --dry-run

Prints {"ok", "added": [...], "already_attached": n, "unmatched": [...]}.
"""

import argparse
import json
import os
import re
import sys

PAT = re.compile(r'^(?P<src>[a-z0-9]+)_(?P<nn>\d{1,3})(?P<suf>[a-c]?)\.(jpe?g|png|webp|gif)$', re.I)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True)
    ap.add_argument('--assets', help='crag folder (default: folder of --crag)')
    ap.add_argument('--credit', action='append', default=[], metavar='SRC=CAPTION',
                    help='caption for images from <src>; repeatable')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    base = os.path.abspath(args.assets or os.path.dirname(os.path.abspath(args.crag)))
    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    credits = dict(c.split('=', 1) for c in args.credit if '=' in c)
    by_n = {s.get('n'): s for s in crag['sectors']}

    added, unmatched, already = [], [], 0
    for folder, photo in (('topo', False), ('img', True)):
        d = os.path.join(base, folder)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = PAT.match(fn)
            if not m:
                continue
            n = int(m.group('nn'))
            rel = '%s/%s' % (folder, fn)
            s = by_n.get(n)
            if s is None:
                unmatched.append({'file': rel, 'reason': 'no sector %d' % n})
                continue
            have = {t.get('image') for t in (s.get('topos') or [])} | {s.get('topo')}
            if rel in have:
                already += 1
                continue
            src = m.group('src').lower()
            cap = credits.get(src) or ('%s — %s (%s)' % ('Photo' if photo else 'Topo',
                                                        s['name'], src))
            entry = {'image': rel, 'caption': cap}
            if photo:
                entry['photo'] = True
            s.setdefault('topos', []).append(entry)
            added.append({'sector': n, 'image': rel, 'caption': cap})

    for s in crag['sectors']:
        if s.get('topos'):
            s['topos'].sort(key=lambda t: (bool(t.get('photo')), t.get('image', '')))

    if added and not args.dry_run:
        with open(args.crag, 'w', encoding='utf-8') as f:
            json.dump(crag, f, ensure_ascii=False, indent=1)
    print(json.dumps({'ok': True, 'dry_run': args.dry_run, 'added': added,
                      'already_attached': already, 'unmatched': unmatched,
                      'next_step': 'Check every caption credits its source and says whether '
                                   'the route numbers match the table; then rebuild.'},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
