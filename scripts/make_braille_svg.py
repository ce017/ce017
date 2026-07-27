"""Render Braille-block art (ascii-art.txt) as a self-typing terminal SVG.

Why not just put the characters in a <text> element: the Braille Patterns block
(U+2800-U+28FF) is missing from almost every monospace font -- on Windows,
Consolas / Courier New / Lucida Console all have 0 of the 256 glyphs, and only
Segoe UI Symbol carries them. A <text> version would therefore fall back
per-glyph to a proportional font on most machines and shear the art apart.

Instead we decode each character back into the 2x4 dot matrix it encodes and
emit vector rectangles, so the result is byte-identical for every viewer and
depends on no font at all.

Each Braille cell packs its 8 dots as bits, laid out:

    1 4      0x01 0x08
    2 5      0x02 0x10
    3 6      0x04 0x20
    7 8      0x40 0x80

Reveal: one left-to-right clip wipe per art row with a block cursor riding the
edge, staggered top to bottom, matching make_ascii_svg.py. SMIL inside an SVG
runs on GitHub (JavaScript does not). Plays once and freezes.

    python scripts/make_braille_svg.py [art.txt] [out.svg]
"""
import html
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "ascii-art.txt")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "ascii-portrait.svg")

HANDLE = os.environ.get("GH_PROFILE_USER", "ce017")
DISPLAY_NAME = os.environ.get("DISPLAY_NAME", HANDLE)
STATIC = bool(os.environ.get("STATIC"))  # frozen frame for local previews

DOT = int(os.environ.get("DOT", 5))       # pitch of one dot, px
# Size of the drawn dot. Equal to DOT (the default) means neighbouring dots merge
# into solid mass, which is how a full cell reads in a terminal and lets adjacent
# dots collapse into single wide rects -- far smaller output. Set below DOT for a
# visible halftone grid instead (this disables run merging).
DOT_SIZE = int(os.environ.get("DOT_SIZE", DOT))

# (bit, dot column, dot row) for the 8 dots of a cell
BITS = ((0x01, 0, 0), (0x02, 0, 1), (0x04, 0, 2), (0x40, 0, 3),
        (0x08, 1, 0), (0x10, 1, 1), (0x20, 1, 2), (0x80, 1, 3))

PAD = 20
TITLEBAR_H = 30
STATUS_H = 30

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"
CURSOR = "#c9d1d9"

ROW_DUR = 0.11
STAGGER = 0.11        # == ROW_DUR -> a single cursor sweeping down


def load_rows(path):
    with open(path, encoding="utf-8") as fh:
        rows = fh.read().rstrip("\n").split("\n")
    if not rows:
        raise SystemExit(f"{path} is empty")
    width = max(len(r) for r in rows)
    return [r.ljust(width, "⠀") for r in rows], width


rows_txt, COLS = load_rows(SRC)
ROWS = len(rows_txt)

ART_W = COLS * 2 * DOT
ART_H = ROWS * 4 * DOT
CANVAS_W = ART_W + PAD * 2
CANVAS_H = TITLEBAR_H + ART_H + STATUS_H + PAD
art_top = TITLEBAR_H + 7


def row_path(line, art_row):
    """Vector path for one art row's dots, merging horizontal runs when solid."""
    grid = [[False] * (COLS * 2) for _ in range(4)]
    for cx, ch in enumerate(line):
        cell = ord(ch) - 0x2800
        if not 0 <= cell <= 0xFF:
            continue  # not a Braille character; skip rather than corrupt the art
        for bit, dx, dy in BITS:
            if cell & bit:
                grid[dy][cx * 2 + dx] = True

    merge = DOT_SIZE == DOT
    segs = []
    for dy in range(4):
        y = art_top + (art_row * 4 + dy) * DOT
        x = 0
        while x < COLS * 2:
            if not grid[dy][x]:
                x += 1
                continue
            run = 1
            if merge:
                while x + run < COLS * 2 and grid[dy][x + run]:
                    run += 1
            w = DOT_SIZE + (run - 1) * DOT
            segs.append(f"M{PAD + x * DOT} {y}h{w}v{DOT_SIZE}h-{w}z")
            x += run
    return "".join(segs)


parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
    f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" role="img" '
    f'aria-label="{html.escape(DISPLAY_NAME)} - Braille art portrait" '
    f'font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">',
    '<defs>'
    f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
    f'</linearGradient></defs>',
    f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>',
    f'<rect x="0.5" y="0.5" width="{CANVAS_W-1}" height="{CANVAS_H-1}" rx="12" '
    f'fill="none" stroke="{FRAME}" stroke-width="1"/>',
    f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
]
for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
    parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
parts.append(f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
             f'text-anchor="middle">{HANDLE}@github: ~$ ./portrait.sh</text>')

ROW_H = 4 * DOT
for ry, line in enumerate(rows_txt):
    d = row_path(line, ry)
    if not d:
        continue  # blank row -- nothing to reveal
    row_y = art_top + ry * ROW_H
    delay = ry * STAGGER
    path = f'<path d="{d}" fill="{INK}"/>'

    if STATIC:
        parts.append(path)
        continue

    parts.append(
        f'<clipPath id="r{ry}"><rect x="{PAD}" y="{row_y}" height="{ROW_H}" width="0">'
        f'<animate attributeName="width" from="0" to="{ART_W}" begin="{delay:.3f}s" '
        f'dur="{ROW_DUR:.2f}s" fill="freeze"/></rect></clipPath>'
    )
    parts.append(f'<g clip-path="url(#r{ry})">{path}</g>')
    parts.append(
        f'<rect y="{row_y+1}" width="{DOT*2}" height="{ROW_H-2}" fill="{CURSOR}" opacity="0">'
        f'<animate attributeName="x" from="{PAD}" to="{PAD+ART_W}" begin="{delay:.3f}s" '
        f'dur="{ROW_DUR:.2f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0.85" begin="{delay:.3f}s"/>'
        f'<set attributeName="opacity" to="0" begin="{delay+ROW_DUR:.3f}s"/></rect>'
    )

# status bar with a steady blinking cursor
status_line_y = TITLEBAR_H + ART_H + PAD * 0.35
status_y = status_line_y + 19
status_prefix = f"{HANDLE}:~$ whoami "
caret_x = PAD + (len(status_prefix) + len(DISPLAY_NAME)) * 13 * 0.6 + 4
parts.append(f'<line x1="0" y1="{status_line_y:.1f}" x2="{CANVAS_W}" y2="{status_line_y:.1f}" stroke="{FRAME}"/>')
parts.append(f'<text x="{PAD}" y="{status_y:.1f}" fill="{TITLE_TEXT}" font-size="13">'
             f'{html.escape(status_prefix)}<tspan fill="{INK}">{html.escape(DISPLAY_NAME)}</tspan></text>')
parts.append(f'<rect x="{caret_x:.1f}" y="{status_y-12:.1f}" width="8" height="14" fill="{INK}">'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
             f'dur="1s" repeatCount="indefinite"/></rect>')

parts.append("</svg>")
svg = "".join(parts)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"wrote {OUT}  {len(svg)/1024:.1f} KB; {CANVAS_W} x {CANVAS_H}; "
      f"{COLS}x{ROWS} cells -> {COLS*2}x{ROWS*4} dots"
      f"{'  [static]' if STATIC else ''}")
