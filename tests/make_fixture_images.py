#!/usr/bin/env python3
"""
Regenerate the tiny placeholder images of the synthetic example crag.

Needs Pillow. The images are committed, so this only has to run if they change.
The JPEG photo carries EXIF GPS at a synthetic open-ocean point, hand-checkable:
  30° 0' 9.0" S  = -30.0025      19° 59' 51.0" W = -19.9975      altitude 12 m
"""
import os

from PIL import Image, ImageDraw

EX = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'crag-guidebook', 'examples')


def card(size, bg, label, fg=(255, 255, 255)):
    im = Image.new('RGB', size, bg)
    d = ImageDraw.Draw(im)
    d.rectangle([2, 2, size[0] - 3, size[1] - 3], outline=fg)
    d.line([6, size[1] - 8, size[0] // 2, 8, size[0] - 6, size[1] - 8], fill=fg, width=2)
    d.text((6, 6), label, fill=fg)
    return im


def main():
    os.makedirs(os.path.join(EX, 'img'), exist_ok=True)
    os.makedirs(os.path.join(EX, 'topo'), exist_ok=True)
    card((120, 170), (40, 60, 45), 'COVER').save(os.path.join(EX, 'img', 'cover.png'))
    card((160, 120), (230, 225, 210), 'MAP', (60, 60, 60)).save(os.path.join(EX, 'img', 'map.png'))
    card((160, 110), (200, 190, 170), 'TOPO 1', (30, 30, 30)).save(os.path.join(EX, 'topo', 'book_01.png'))
    card((160, 110), (190, 200, 180), 'TOPO 4', (30, 30, 30)).save(os.path.join(EX, 'topo', 'book_04.png'))
    card((160, 110), (180, 190, 205), 'TOPO 3', (30, 30, 30)).save(os.path.join(EX, 'topo', 'web_03.png'))

    photo = card((160, 120), (90, 110, 130), 'PHOTO 2')
    exif = Image.Exif()
    exif[0x8825] = {
        1: 'S', 2: (30.0, 0.0, 9.0),
        3: 'W', 4: (19.0, 59.0, 51.0),
        5: b'\x00', 6: 12.0,
    }
    exif[0x0132] = '2026:06:01 09:45:00'
    photo.save(os.path.join(EX, 'img', 'photo_02a.jpg'), exif=exif, quality=80)
    print('ok')


if __name__ == '__main__':
    main()
