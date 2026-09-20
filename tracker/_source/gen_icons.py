#!/usr/bin/env python3
"""
Generate the PWA icons (a gold nib on dark) as PNGs using only the stdlib.
Run once:  python tracker/_source/gen_icons.py
"""
import os
import struct
import zlib

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

BG   = (23, 26, 33)     # app panel color
GOLD = (212, 175, 55)
DARK = (15, 17, 21)     # slit / breather


def make_icon(size, path):
    rows = bytearray()
    for y in range(size):
        row = bytearray()
        ny = y / size
        for x in range(size):
            nx = (x - size / 2) / size
            c = BG
            # Nib silhouette: shoulders at the top tapering to a point.
            if 0.16 <= ny <= 0.84:
                t = (ny - 0.16) / 0.68          # 0 at shoulders -> 1 at tip
                half = 0.285 * (1 - t ** 1.6) + 0.012
                if abs(nx) <= half:
                    c = GOLD
                    if abs(nx) <= 0.013 and ny > 0.44:          # slit
                        c = DARK
                    if (nx * nx + (ny - 0.42) ** 2) ** 0.5 < 0.045:  # breather hole
                        c = DARK
            row += bytes(c)
        rows += b'\x00' + row                    # filter byte 0 per scanline

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
           chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)
    print(f'wrote {path} ({size}x{size}, {len(png)} bytes)')


if __name__ == '__main__':
    for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png'),
                       (180, 'apple-touch-icon.png')]:
        make_icon(size, os.path.join(OUT_DIR, name))
