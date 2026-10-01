#!/usr/bin/env python3
"""
photo_gps.py — read GPS position and time from photo EXIF (JPEG, HEIC), e.g. to pin
a parking spot from a visitor's parking photo; optionally convert photos to JPEG.

EXIF GPS (EXIF 2.3, GPS IFD 0x8825): latitude/longitude are three rationals
(degrees, minutes, seconds) plus a hemisphere ref:
    decimal = sign × (deg + min/60 + sec/3600),  sign = −1 for S or W
A metadata tool of the operating system may return nothing for HEIC; Pillow (+
pillow-heif for HEIC) reads it reliably.

Usage
-----
  python3 scripts/photo_gps.py IMG_0001.jpg IMG_0002.heic
  python3 scripts/photo_gps.py photos/*.heic --to-jpg img/

Needs Pillow; HEIC also needs pillow-heif. Without them the result says what is
missing (on macOS, `sips -s format jpeg in.heic --out out.jpg` converts HEIC).

Prints {"ok", "photos": [{"file", "lat", "lon", "altitude_m", "time", "jpg", "error"}],
"privacy": "..."}. Exit 0, or 3 if Pillow is missing.
"""

import argparse
import json
import os
import sys

PRIVACY = ('Photos carry the exact position and time they were taken, and may show licence '
           'plates or faces. Before sharing the guide, review every photo and strip or blur '
           'as the user decides; list any concerns in HANDOVER.md.')


def dms(v, ref):
    d, m, s = (float(x) for x in v)
    dec = d + m / 60.0 + s / 3600.0
    return round(-dec if ref in ('S', 'W') else dec, 6)


def read(path, Image, heif_ok):
    rec = {'file': path}
    if path.lower().endswith(('.heic', '.heif')) and not heif_ok:
        rec['error'] = 'pillow-heif not installed: cannot open HEIC'
        return rec, None
    im = Image.open(path)
    ex = im.getexif()
    gps = ex.get_ifd(0x8825) if ex else {}
    if gps and 2 in gps and 4 in gps:
        rec['lat'] = dms(gps[2], gps.get(1, 'N'))
        rec['lon'] = dms(gps[4], gps.get(3, 'E'))
        if 6 in gps:
            alt = float(gps[6])
            below = gps.get(5) in (b'\x01', 1)
            rec['altitude_m'] = round(-alt if below else alt, 1)
    else:
        rec['error'] = 'no GPS in EXIF'
    exif_ifd = ex.get_ifd(0x8769) if ex else {}
    rec['time'] = exif_ifd.get(36867) or ex.get(0x0132) if ex else None
    return rec, im


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('photos', nargs='+')
    ap.add_argument('--to-jpg', metavar='DIR', help='also save a JPEG copy of each photo here')
    args = ap.parse_args()

    try:
        from PIL import Image
    except Exception as exc:                                       # noqa: BLE001
        print(json.dumps({'ok': False, 'missing': 'Pillow', 'error': str(exc),
                          'degraded': 'Cannot read EXIF. Ask the user for the parking '
                                      'coordinates, or ask before installing Pillow.'}))
        return 3
    heif_ok = False
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        heif_ok = True
    except Exception:                                              # noqa: BLE001
        pass

    out = []
    for p in args.photos:
        try:
            rec, im = read(p, Image, heif_ok)
            if im is not None and args.to_jpg:
                os.makedirs(args.to_jpg, exist_ok=True)
                dst = os.path.join(args.to_jpg, os.path.splitext(os.path.basename(p))[0] + '.jpg')
                im.convert('RGB').save(dst, quality=88)
                rec['jpg'] = dst
        except Exception as exc:                                   # noqa: BLE001
            rec = {'file': p, 'error': '%s: %s' % (type(exc).__name__, exc)}
        out.append(rec)
    print(json.dumps({'ok': True, 'photos': out, 'heic_supported': heif_ok,
                      'privacy': PRIVACY}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
