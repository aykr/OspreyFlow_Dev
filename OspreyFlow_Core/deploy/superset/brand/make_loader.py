"""Writes loading.gif: the OspreyFlow mark (mesh cut, DESIGN.md §1) with its six facets lit in turn,
in the light theme's ink (#191b1c) over its faint neutral (#ced2d2, --n5). Replaces Superset's own
loading animation (Dockerfile). Re-run after changing the mark:

    uv run --no-project --with pillow python make_loader.py
"""

from PIL import Image, ImageDraw

FACES = [
    [(4.9, 6.7), (6.4, 17.2), (23.9, 11.1)],
    [(6.8, 17.9), (24.3, 19.9), (24.2, 11.7)],
    [(6.6, 18.6), (8, 29.1), (24.2, 20.7)],
    [(8.4, 30.1), (9.4, 41), (24.4, 21.2)],
    [(9.8, 41.2), (24.4, 30.2), (24.7, 21.5)],
    [(25.6, 11.9), (26.2, 29.2), (43.9, 25.7)],
]
SIZE, SCALE = 96, 2  # drawn at 2x and reduced, for clean edges
INK, FAINT = (0x19, 0x1B, 0x1C, 255), (0xCE, 0xD2, 0xD2, 255)


def frame(lit: int) -> Image.Image:
    big = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(big)
    k = SIZE * SCALE / 48
    for i, face in enumerate(FACES):
        on = (i - lit) % len(FACES) in (0, 1, 2)
        draw.polygon([(x * k, y * k) for x, y in face], fill=INK if on else FAINT)
    return big.resize((SIZE, SIZE), Image.LANCZOS)


frames = [frame(i) for i in range(len(FACES))]
frames[0].save("loading.gif", save_all=True, append_images=frames[1:], duration=140, loop=0,
               disposal=2, transparency=0, optimize=False)
print("wrote loading.gif")
