"""Generate the AFKSwitch pixel-art logo: the Claude Code switch itself, a bordered box with
'AFK' in orange (5x7 pixel font) and the away cells ■□, on a 40x40 grid. Writes
assets/logo-{light,dark}.svg (square, with background, used as the plugin icon) and
assets/wordmark-{light,dark}.svg (transparent, for the README)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLYPHS = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
}
ORANGE = "#F28C28"
SIZE = 40
BOX = (1, 13, 38, 25)       # border: left, top, right, bottom (inclusive)
TEXT = (4, 16)              # top-left of 'AFK'; 7 rows tall
CELLS = (24, 30)            # left x of the filled cell ■ and the hollow cell □, 5x5 each
CELL_TOP = 17               # cells sit centred on the text band


def pixels(ink: str) -> dict:
    grid = {}
    left, top, right, bottom = BOX
    for x in range(left, right + 1):
        grid[(x, top)] = grid[(x, bottom)] = ink
    for y in range(top, bottom + 1):
        grid[(left, y)] = grid[(right, y)] = ink
    for i, letter in enumerate("AFK"):
        for dy, row in enumerate(GLYPHS[letter]):
            for dx, cell in enumerate(row):
                if cell == "#":
                    grid[(TEXT[0] + i * 6 + dx, TEXT[1] + dy)] = ORANGE
    for n, x0 in enumerate(CELLS):
        for x in range(x0, x0 + 5):
            for y in range(CELL_TOP, CELL_TOP + 5):
                edge = x in (x0, x0 + 4) or y in (CELL_TOP, CELL_TOP + 4)
                if n == 0 or edge:   # ■ filled, □ outline
                    grid[(x, y)] = ink
    return grid


def svg(ink: str, bg: str | None) -> str:
    """Square logo with background; without one, a wordmark cropped to the box."""
    back = f'<rect width="{SIZE}" height="{SIZE}" fill="{bg}"/>' if bg else ""
    box = f'viewBox="0 0 {SIZE} {SIZE}" width="512" height="512"' if bg else \
        f'viewBox="0 {BOX[1] - 1} {SIZE} {BOX[3] - BOX[1] + 3}" width="400" height="150"'
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{c}"/>'
                    for (x, y), c in sorted(pixels(ink).items()))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" {box} '
            f'shape-rendering="crispEdges">{back}{rects}</svg>\n')


if __name__ == "__main__":
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    (out / "logo-light.svg").write_text(svg("#262626", "#FFFFFF"), encoding="utf-8")
    (out / "logo-dark.svg").write_text(svg("#EDEDED", "#1C1C1C"), encoding="utf-8")
    (out / "wordmark-light.svg").write_text(svg("#262626", None), encoding="utf-8")
    (out / "wordmark-dark.svg").write_text(svg("#EDEDED", None), encoding="utf-8")
    # Claude Code reads the plugin icon from .claude-plugin/icon.svg (square, >= 128 px).
    (ROOT / ".claude-plugin" / "icon.svg").write_text(svg("#262626", "#FFFFFF"), encoding="utf-8")
    # Everything stays inside the border, and the cells sit inside the text band.
    grid = pixels("#000")
    assert all(BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3] for x, y in grid)
    assert TEXT[1] <= CELL_TOP and CELL_TOP + 4 <= TEXT[1] + 6
    print(out)
