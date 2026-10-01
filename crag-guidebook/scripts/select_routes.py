#!/usr/bin/env python3
"""
select_routes.py — choose which routes a guide prints, by quality alone.

A guide that cannot print every route needs a rule for which ones it keeps. The rule
here is grade-neutral on purpose: it never looks at grades, so it does not tune the
guide to one climber, and it never ranks by logged ascents, because ascents pile up on
the easy grades and drag a selection down. It keeps every route the spine source rates
at --min-stars or better, on the spine's own star scale, whatever its grade.

  keep   every route with stars >= --min-stars (default 2 on a 0–3 scale: ★★ and ★★★)
  drop   everything else, including unrated routes (stars null) — "unrated" is not
         a quality signal either way
  empty  a sector where nothing qualifies keeps its highest-rated routes (all of them,
         if none is rated at all) and says so, so no sector prints with an empty table

It records what it left out, so the counts stay honest: per sector `routes_count`
(the total on the spine), `routes_omitted` (total − kept) and `selection_note`; crag-wide
`crag.selection` and `crag.spine_total` = Σ routes_count. verify_guide.py then checks
I1 as  Σ (kept + omitted) = spine_total.

Choosing the SECTORS is a separate step and should also be grade-neutral: by
popularity and quality, and never drop a sector for its season or aspect — print its
conditions instead (references/layout.md).

Usage
-----
  python3 scripts/select_routes.py --crag crag.json                  # ★★ and up, in place
  python3 scripts/select_routes.py --crag crag.json --min-stars 3    # ★★★ only
  python3 scripts/select_routes.py --crag crag.json --out selected.json

Input: each sector's `routes` holds the spine's COMPLETE list for that sector (run this
once, on the full lists; rerunning on an already-selected file is a no-op).
Prints a JSON summary on stdout.
"""

import argparse
import json
import sys


def stars_of(r):
    v = r.get('stars')
    return None if v is None else float(v)


def select(routes, min_stars=2.0):
    """-> (kept, note). Grade-neutral: only the spine's star rating decides."""
    kept = [r for r in routes if stars_of(r) is not None and stars_of(r) >= min_stars]
    if kept or not routes:
        return kept, None
    rated = [stars_of(r) for r in routes if stars_of(r) is not None]
    if rated:
        best = max(rated)
        kept = [r for r in routes if stars_of(r) == best]
        return kept, ('no route here is rated %s or better; showing the highest-rated (%s)'
                      % ('★' * int(min_stars), ('★' * int(best)) if best else 'rated 0'))
    return list(routes), 'no route here is rated; showing all routes'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--crag', required=True)
    ap.add_argument('--min-stars', type=float, default=2.0,
                    help="keep routes rated at least this on the spine's star scale (default 2)")
    ap.add_argument('--scale-max', type=float, default=3.0, help="top of the spine's star scale")
    ap.add_argument('--out', help='write here instead of back into --crag')
    args = ap.parse_args()
    if not 0 < args.min_stars <= args.scale_max:
        ap.error('--min-stars must be within the star scale (0, --scale-max]')

    with open(args.crag, encoding='utf-8') as f:
        crag = json.load(f)
    meta = crag.setdefault('crag', {})
    prev = meta.get('selection')
    if prev and prev.get('min_stars') == args.min_stars:
        print(json.dumps({'ok': True, 'unchanged': True, 'selection': prev}, ensure_ascii=False))
        return 0
    if prev:
        print(json.dumps({'ok': False, 'error': 'crag.json was already selected with min_stars=%s; '
                          'rebuild it from the full route lists first' % prev.get('min_stars')}))
        return 2

    total = shown = 0
    per, fallbacks = {}, []
    for s in crag.get('sectors', []):
        full = s.get('routes', [])
        n_total = int(s.get('routes_count') or len(full))
        if n_total < len(full):
            n_total = len(full)
        kept, note = select(full, args.min_stars)
        s['routes'] = kept
        s['routes_count'] = n_total
        s['routes_omitted'] = n_total - len(kept)
        if note:
            s['selection_note'] = note
            fallbacks.append(s.get('n'))
        elif s['routes_omitted']:
            s['selection_note'] = '%d of %d routes shown: every route rated %s or better' % (
                len(kept), n_total, '★' * int(args.min_stars))
        total += n_total
        shown += len(kept)
        per[str(s.get('n'))] = [len(kept), n_total]

    meta['selection'] = {'rule': 'quality', 'min_stars': args.min_stars,
                         'scale_max': args.scale_max, 'routes_total': total, 'routes_shown': shown,
                         'note': 'Routes rated %s or better on the spine’s 0–%g scale, at any grade; '
                                 'unrated routes are left out.' % ('★' * int(args.min_stars),
                                                                    args.scale_max)}
    meta['spine_total'] = total
    with open(args.out or args.crag, 'w', encoding='utf-8') as f:
        json.dump(crag, f, ensure_ascii=False, indent=1)
    print(json.dumps({'ok': True, 'routes_total': total, 'routes_shown': shown,
                      'per_sector_shown_of_total': per, 'fallback_sectors': fallbacks,
                      'next_step': 'Say on the About page that the guide shows a selection, and by '
                                   'which rule (crag.selection.note).'},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
