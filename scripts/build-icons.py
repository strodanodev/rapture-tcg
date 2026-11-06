"""PWA icons from the boot screen's emblem (the ring, two cards and the gem in web/index.html) -> web/assets/brand/*.png.

    python scripts/build-icons.py

The SVG is rasterised by headless Chrome (no SVG library needed), then laid on the obsidian ground with Pillow:

icon-192 / icon-512: the emblem on the ground (Android home screen, Chrome install dialog).
icon-maskable-512:   the emblem inside the 80% safe zone, so adaptive-icon masks never clip it.
apple-touch-icon:    180 px, opaque (iOS squares the corners itself and paints transparency black).
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

WEB = Path(__file__).resolve().parent.parent / 'web'
OUT = WEB / 'assets' / 'brand'
BG = (5, 4, 9, 255)  # the site's background, #050409
CHROME = next((p for p in (
    os.environ.get('CHROME'),
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    shutil.which('google-chrome'), shutil.which('chromium'), shutil.which('chrome'),
) if p and Path(p).exists()), None)


def emblem_svg() -> str:
    """The emblem from the boot screen's markup (its second <svg>), in the boot screen's gold."""
    html = (WEB / 'index.html').read_text(encoding='utf-8')
    m = re.search(r'<svg viewBox="0 0 120 120" fill="none" stroke="currentColor" stroke-linejoin="round">.*?</svg>', html, re.S)
    if not m:
        raise SystemExit('emblem <svg> not found in web/index.html')
    return m.group(0).replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" color="#ffc95e" ', 1)


def render_emblem(px: int) -> Image.Image:
    """The emblem at px x px on a transparent ground."""
    if not CHROME:
        raise SystemExit('Chrome not found: set CHROME to its path')
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / 'emblem.html'
        shot = Path(tmp) / 'emblem.png'
        svg = emblem_svg().replace('<svg ', f'<svg width="{px}" height="{px}" ', 1)
        page.write_text(f'<!doctype html><style>html,body{{margin:0;background:transparent}}svg{{display:block}}</style>{svg}', encoding='utf-8')
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--default-background-color=00000000',
                        f'--window-size={px},{px}', f'--screenshot={shot}', page.as_uri()], check=True, capture_output=True)
        return Image.open(shot).convert('RGBA').crop((0, 0, px, px))


def icon(emblem: Image.Image, size: int, fill: float, name: str) -> None:
    side = round(size * fill)
    mark = emblem.resize((side, side), Image.LANCZOS)
    out = Image.new('RGBA', (size, size), BG)
    out.alpha_composite(mark, ((size - side) // 2, (size - side) // 2))
    out.save(OUT / name, optimize=True)
    print(name, out.size)


OUT.mkdir(parents=True, exist_ok=True)
emblem = render_emblem(1024)
icon(emblem, 192, 0.86, 'icon-192.png')
icon(emblem, 512, 0.86, 'icon-512.png')
icon(emblem, 512, 0.66, 'icon-maskable-512.png')
icon(emblem, 180, 0.8, 'apple-touch-icon.png')
