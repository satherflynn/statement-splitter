#!/usr/bin/env python3
"""Generate the Statement Splitter app icon.

A teal rounded square with a stack of white pages fanning out to the right —
one packet becoming several files. Writes appicon.png (1024 preview),
appicon_128.png (shown inside the window) and appicon.icns (the Mac app icon)
via Apple's `iconutil`.

Run:  python make_icon.py
"""
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

S = 1024
TEAL = (15, 118, 110)
TEAL_DK = (9, 78, 73)
PAPER = (255, 255, 255)
LINE = (170, 200, 196)
SHADOW = (0, 0, 0, 70)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background():
    img = Image.new("RGB", (S, S))
    px = img.load()
    for y in range(S):
        c = lerp(TEAL, TEAL_DK, y / (S - 1))
        for x in range(S):
            px[x, y] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((60, 60, S - 60, S - 60), radius=220, fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def page(w, h, rot, lines=True):
    """A white sheet with faint text lines, rotated, on its own transparent canvas."""
    pad = 80
    sheet = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(sheet)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=28, fill=PAPER)
    if lines:
        y = pad + 70
        for i in range(6):
            width = w - 110 if i % 3 != 2 else w - 220
            d.rounded_rectangle((pad + 55, y, pad + 55 + width, y + 18), radius=9, fill=LINE)
            y += 52
    return sheet.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)


def main():
    img = background()
    # Three sheets fanned out; each with a soft drop shadow.
    specs = [(-14, (250, 300)), (-4, (330, 270)), (7, (415, 245))]
    for rot, (x, y) in specs:
        sheet = page(400, 500, rot)
        shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
        shadow.paste(Image.new("RGBA", sheet.size, SHADOW), (0, 0), sheet.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(22))
        img.alpha_composite(shadow, (x + 6, y + 18))
        img.alpha_composite(sheet, (x, y))

    img.save("appicon.png")
    img.resize((128, 128), Image.Resampling.LANCZOS).save("appicon_128.png")

    iconset = Path("appicon.iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}" + ("@2x" if scale == 2 else "") + ".png"
            img.resize((px, px), Image.Resampling.LANCZOS).save(iconset / name)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", "appicon.icns"], check=True)
    shutil.rmtree(iconset)
    print("wrote appicon.png, appicon_128.png, appicon.icns")


if __name__ == "__main__":
    main()
