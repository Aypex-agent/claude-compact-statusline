#!/usr/bin/env python3
"""Draw the five context-band sprites of a fan-made orange Claude mascot and emit:

  assets/<band>.png        24x16 sprite upscaled x8 (nearest), for Ghostty/kitty `Image`
  assets/<band>-phone.png  12x8 sprite upscaled x16, for looking at
  assets/preview.png       all ten side by side
  hooks/sprites.ts         base64 PNGs + half-block Raster cells (12 cols x 4 rows)

Standard library only. Edit the drawing functions, or replace assets/*.png with your
own art and re-run with --from-png to rebuild sprites.ts from them.
"""
import base64
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANDS = ["sharp", "coasting", "foggy", "cooked", "dumb"]

PAL = {
    "O": (0xD9, 0x77, 0x57),  # body orange
    "o": (0xB0, 0x5A, 0x3E),  # body shade
    "h": (0xF0, 0xA0, 0x80),  # highlight
    "c": (0x9A, 0x48, 0x30),  # cooked body
    "K": (0x1A, 0x12, 0x10),  # eyes / mouth
    "W": (0xF4, 0xF1, 0xEA),  # white
    "Y": (0xF2, 0xD2, 0x30),  # sparkle
    "G": (0x8A, 0x8E, 0x99),  # fog / steam
    "g": (0xC2, 0xC5, 0xCE),  # light fog
    "B": (0x7F, 0xC8, 0xF0),  # drool
    "R": (0xE0, 0x50, 0x50),  # blush / hot
}


class Grid:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = [[None] * w for _ in range(h)]

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = c

    def rect(self, x0, y0, x1, y1, c):  # inclusive
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, c)

    def dots(self, pts, c):
        for x, y in pts:
            self.set(x, y, c)


# ---------------------------------------------------------------- 24 x 16 (Ghostty)

def body24(g, main="O"):
    g.rect(4, 2, 19, 11, main)           # body
    g.rect(4, 2, 19, 2, "h")             # top highlight
    g.rect(4, 11, 19, 11, "o")           # bottom shade
    g.rect(19, 3, 19, 10, "o")           # right shade
    g.rect(2, 6, 3, 8, main)             # arms
    g.rect(20, 6, 21, 8, main)
    g.rect(2, 8, 3, 8, "o")
    g.rect(20, 8, 21, 8, "o")
    for x in (5, 9, 13, 17):             # legs
        g.rect(x, 12, x + 1, 14, main)
        g.rect(x + 1, 12, x + 1, 14, "o")


def sharp24(g):
    body24(g)
    for x0 in (7, 14):                   # happy ^ eyes
        g.dots([(x0 + 1, 5), (x0, 6), (x0 + 2, 6)], "K")
    g.rect(10, 9, 13, 9, "K")            # smile
    g.dots([(9, 8), (14, 8)], "K")
    g.dots([(6, 8), (17, 8)], "R")       # cheeks
    g.dots([(22, 0), (21, 1), (22, 1), (23, 1), (22, 2)], "Y")  # sparkle


def coasting24(g):
    body24(g)
    g.rect(8, 5, 9, 7, "K")              # calm eyes
    g.rect(14, 5, 15, 7, "K")
    g.dots([(8, 5), (14, 5)], "W")       # glints
    g.rect(11, 9, 12, 9, "K")            # small smile
    g.dots([(10, 8), (13, 8)], "K")


def foggy24(g):
    body24(g)
    g.rect(8, 5, 9, 5, "o")              # heavy lids
    g.rect(14, 5, 15, 5, "o")
    g.rect(8, 6, 9, 7, "K")
    g.rect(14, 6, 15, 7, "K")
    g.rect(10, 9, 13, 9, "K")            # flat mouth
    g.rect(0, 1, 7, 2, "g")              # fog bank drifting over the head
    g.rect(2, 0, 5, 0, "g")
    g.rect(1, 3, 3, 3, "G")
    g.dots([(6, 3), (9, 1)], "G")


def cooked24(g):
    body24(g, main="c")
    for x0 in (7, 14):                   # x_x
        g.dots([(x0, 4), (x0 + 2, 4), (x0 + 1, 5), (x0, 6), (x0 + 2, 6)], "K")
    g.rect(10, 9, 13, 9, "K")
    g.dots([(9, 10), (14, 10)], "K")     # grimace corners
    for x, d in ((7, 0), (12, 1), (17, 0)):  # steam wisps
        g.dots([(x, 1 - d), (x + 1, 0 + d)], "G")
    g.dots([(5, 3), (18, 3)], "R")


def dumb24(g):
    body24(g)
    for x0 in (7, 14):                   # hollow ° eyes, mismatched
        g.rect(x0, 4, x0 + 2, 6, "W")
    g.set(8, 5, "K")
    g.set(16, 6, "K")
    g.rect(10, 9, 12, 10, "K")           # open mouth
    g.rect(11, 11, 11, 13, "B")          # drool
    g.set(12, 14, "B")
    g.set(11, 15, "B")
    g.dots([(20, 1), (21, 0), (22, 1)], "G")  # little "?" cloud of nothing


# ---------------------------------------------------------------- 12 x 8 (foot, half-block)

def body12(g, main="O"):
    g.rect(2, 1, 9, 5, main)
    g.rect(2, 1, 9, 1, "h")
    g.rect(9, 2, 9, 5, "o")
    g.set(1, 3, main)
    g.set(10, 3, main)
    for x in (3, 5, 6, 8):
        g.set(x, 6, main if x in (3, 6) else "o")


def sharp12(g):
    body12(g)
    g.dots([(4, 2), (7, 2)], "K")
    g.rect(5, 4, 6, 4, "K")
    g.dots([(11, 0)], "Y")


def coasting12(g):
    body12(g)
    g.rect(4, 2, 4, 3, "K")
    g.rect(7, 2, 7, 3, "K")


def foggy12(g):
    body12(g)
    g.dots([(4, 3), (7, 3)], "K")
    g.dots([(4, 2), (7, 2)], "o")
    g.rect(5, 4, 6, 4, "o")
    g.rect(0, 0, 4, 0, "g")


def cooked12(g):
    body12(g, main="c")
    g.dots([(4, 3), (7, 3)], "K")
    g.dots([(4, 2), (7, 2)], "R")
    g.dots([(4, 0), (7, 0)], "G")


def dumb12(g):
    body12(g)
    g.dots([(4, 2), (7, 3)], "W")
    g.set(5, 4, "K")
    g.rect(6, 5, 6, 7, "B")


DRAW24 = {"sharp": sharp24, "coasting": coasting24, "foggy": foggy24, "cooked": cooked24, "dumb": dumb24}
DRAW12 = {"sharp": sharp12, "coasting": coasting12, "foggy": foggy12, "cooked": cooked12, "dumb": dumb12}


# ---------------------------------------------------------------- encoders

def png_bytes(rows):
    """rows: list of list of (r,g,b,a)."""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\0" + bytes(v for px in row for v in px) for row in rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def rgba_rows(g, scale):
    out = []
    for y in range(g.h):
        row = [(0, 0, 0, 0) if c is None else (*PAL[c], 255) for c in g.px[y] for _ in range(scale)]
        out += [row] * scale
    return out


DEFAULT = 0x01000000


def raster_cells(g):
    """Half-block cells: each cell is a top and bottom pixel. Returns base64 of u32 LE triplets."""
    words = []
    for cy in range(g.h // 2):
        for x in range(g.w):
            top, bot = g.px[2 * cy][x], g.px[2 * cy + 1][x]
            rgb = lambda c: (PAL[c][0] << 16) | (PAL[c][1] << 8) | PAL[c][2]
            if top is None and bot is None:
                words += [0x20, DEFAULT, DEFAULT]
            elif bot is None:
                words += [0x2580, rgb(top), DEFAULT]          # ▀
            elif top is None:
                words += [0x2584, rgb(bot), DEFAULT]          # ▄
            else:
                words += [0x2580, rgb(top), rgb(bot)]
    return base64.b64encode(struct.pack(f"<{len(words)}I", *words)).decode()


def main():
    (ROOT / "assets").mkdir(exist_ok=True)
    grids24, grids12, ts = {}, {}, []
    for b in BANDS:
        g24, g12 = Grid(24, 16), Grid(12, 8)
        DRAW24[b](g24)
        DRAW12[b](g12)
        grids24[b], grids12[b] = g24, g12
        big = png_bytes(rgba_rows(g24, 8))
        (ROOT / "assets" / f"{b}.png").write_bytes(big)
        (ROOT / "assets" / f"{b}-phone.png").write_bytes(png_bytes(rgba_rows(g12, 16)))
        ts.append(f"  {b}: {{\n    png: '{base64.b64encode(big).decode()}',\n"
                  f"    cells: '{raster_cells(g12)}',\n  }},")

    # preview: top row 24x16 x8, bottom row 12x8 x16, on a dark backdrop
    bg = (0x05, 0x07, 0x0D, 255)
    pad, cw = 16, 192
    W = pad + len(BANDS) * (cw + pad)
    H = pad + 128 + pad + 128 + pad
    canvas = [[bg] * W for _ in range(H)]
    for i, b in enumerate(BANDS):
        for (g, sc, y0) in ((grids24[b], 8, pad), (grids12[b], 16, pad * 2 + 128)):
            for y, row in enumerate(rgba_rows(g, sc)):
                for x, px in enumerate(row):
                    if px[3]:
                        canvas[y0 + y][pad + i * (cw + pad) + x] = px
    (ROOT / "assets" / "preview.png").write_bytes(png_bytes(canvas))

    header = ("// Generated by tools/make_sprites.py; edit that and re-run, not this file.\n"
              "// png: 24x16 sprite upscaled x8 (192x128). cells: 12x8 sprite as 12x4 half-block Raster cells.\n")
    body = ("export const BANDS = ['sharp', 'coasting', 'foggy', 'cooked', 'dumb'] as const\n"
            "export type Band = (typeof BANDS)[number]\n"
            "export const SPRITES: Record<Band, { png: string; cells: string }> = {\n" + "\n".join(ts) + "\n}\n")
    (ROOT / "hooks" / "sprites.ts").write_text(header + body)
    print("wrote", len(BANDS), "sprites;", (ROOT / "hooks" / "sprites.ts").stat().st_size, "bytes of sprites.ts")


if __name__ == "__main__":
    sys.exit(main())
