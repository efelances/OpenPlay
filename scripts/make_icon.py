"""Generate assets/icon.ico (256px forest-green rounded square with white 'OP')."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = ROOT / "assets" / "icon.ico"


def main() -> int:
    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded square in forest green (#245C46)
    draw.rounded_rectangle(
        [(12, 12), (size - 12, size - 12)],
        radius=52,
        fill=(36, 92, 70, 255),
        outline=(247, 245, 240, 255),
        width=8,
    )

    text = "OP"
    font = None
    for candidate in ("segoeuib.ttf", "arialbd.ttf", "SegoeUI-Bold.ttf"):
        try:
            font = ImageFont.truetype(candidate, 118)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = (size - th) / 2 - bbox[1]
    draw.text((tx, ty), text, fill=(247, 245, 240, 255), font=font)

    img.save(
        ICON_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated icon: {ICON_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
