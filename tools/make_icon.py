"""Build the Windows ICO and sized PNG pack from the Nasolt XP master artwork."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "assets" / "app_icons"
SOURCE = ICON_DIR / "nasolt-vault-xp-master.png"
PNG_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512, 1024)
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def main() -> None:
    with Image.open(SOURCE) as source:
        if source.width != source.height:
            raise ValueError("The app icon master must be square")
        master = source.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
    for size in PNG_SIZES:
        image = master if size == 1024 else master.resize((size, size), Image.Resampling.LANCZOS)
        image.save(ICON_DIR / f"nasolt-vault-{size}.png", optimize=True)
    master.resize((256, 256), Image.Resampling.LANCZOS).save(ROOT / "assets" / "app.png")
    master.save(ROOT / "assets" / "app.ico", sizes=[(size, size) for size in ICO_SIZES])
    print("Generated Nasolt Vault XP icon pack in assets/app_icons")


if __name__ == "__main__":
    main()
