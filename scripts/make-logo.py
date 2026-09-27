"""Generate the AFKSwitch pixel-art logo: 'AFK' in a 5x7 pixel font, then an orange switch
of the same height, on a 24x24 grid. Writes assets/logo-{light,dark}.svg (square, with
background, used as the plugin icon) and assets/wordmark-{light,dark}.svg (transparent, for the README)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLYPHS = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
}
ORANGE = "#F28C28"
TOP = 8  # first row of the 7-row band shared by the text and the switch


def pixels(ink: str) -> dict:
    grid = {}
    for i, letter in enumerate("AFK"):
        for dy, row in enumerate(GLYPHS[letter]):
            for dx, cell in enumerate(row):
                if cell == "#":
                    grid[(1 + i * 6 + dx, TOP + dy)] = ink
    for x in range(19, 23):                 # switch: 4 wide, 7 tall, same band as the text
        for y in range(TOP, TOP + 7):
            grid[(x, y)] = ORANGE
    for x in range(20, 22):                 # white window at the top
        for y in range(TOP + 1, TOP + 4):
            grid[(x, y)] = "#FFFFFF"
    return grid


def svg(ink: str, bg: str | None) -> str:
    """Square logo with background; without one, a wordmark cropped to the text band."""
    back = f'<rect width="24" height="24" fill="{bg}"/>' if bg else ""
    box = 'viewBox="0 0 24 24" width="512" height="512"' if bg else \
        f'viewBox="0 {TOP - 1} 24 9" width="240" height="90"'
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
    # The switch and the word share exactly the same rows.
    rows = {y for (x, y) in pixels("#000") if x >= 19}
    assert rows == {y for (x, y) in pixels("#000") if x < 18} == set(range(TOP, TOP + 7))
    print(out)
