from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "springpaper.ico"


def rounded_rectangle(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def make_icon(size):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = size / 256

    rounded_rectangle(draw, [16 * scale, 16 * scale, 240 * scale, 240 * scale], 42 * scale, "#FDF8F3")
    rounded_rectangle(draw, [44 * scale, 32 * scale, 212 * scale, 224 * scale], 22 * scale, "#FFFDF8")
    draw.polygon(
        [
            (172 * scale, 32 * scale),
            (212 * scale, 32 * scale),
            (212 * scale, 72 * scale),
        ],
        fill="#F6D6C8",
    )
    rounded_rectangle(draw, [48 * scale, 128 * scale, 208 * scale, 158 * scale], 15 * scale, "#B9DEC9")
    draw.ellipse([74 * scale, 70 * scale, 106 * scale, 102 * scale], fill="#F8C8DC")
    draw.ellipse([96 * scale, 70 * scale, 128 * scale, 102 * scale], fill="#F8C8DC")
    draw.ellipse([84 * scale, 92 * scale, 116 * scale, 124 * scale], fill="#F8C8DC")
    draw.ellipse([62 * scale, 92 * scale, 94 * scale, 124 * scale], fill="#F8C8DC")
    draw.ellipse([90 * scale, 86 * scale, 100 * scale, 96 * scale], fill="#D8A6B7")
    return image


images = [make_icon(size) for size in (256, 128, 64, 48, 32, 16)]
OUT.parent.mkdir(parents=True, exist_ok=True)
images[0].save(OUT, sizes=[(img.width, img.height) for img in images], append_images=images[1:])
print(OUT)
