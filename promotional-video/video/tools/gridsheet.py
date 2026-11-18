"""Gridded previews of screenshots (labels in original pixels) for picking camera focus points."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SRC = Path(__file__).resolve().parents[2] / "02-real-app-screenshots"
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
for rel in sys.argv[2:]:
    im = Image.open(SRC / rel).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im)
    step = 240 if w > 1000 else 100
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(255, 0, 80), width=2)
        d.text((x + 4, 4), str(x), fill=(255, 0, 80))
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(0, 120, 255), width=2)
        d.text((4, y + 4), str(y), fill=(0, 120, 255))
    scale = 1100 / w if w > 1000 else 1
    im = im.resize((int(w * scale), int(h * scale)))
    im.save(OUT / (rel.replace("/", "__")))
    print(OUT / (rel.replace("/", "__")))
