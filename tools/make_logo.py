"""Erzeugt das Logo der Integration: eine Batterie mit Jupiter-Baendern
und einem Planetenring. Eigenes Motiv, kein Herstellerlogo.

Ausgabe nach dem Schema des Home-Assistant-Brands-Repositories:
icon.png (256), icon@2x.png (512), logo.png, logo@2x.png sowie
dark_icon.png / dark_icon@2x.png fuer dunkle Oberflaechen.

Aufruf:
    pip install cairosvg
    python tools/make_logo.py custom_components/marstek_jupiter/brand

Mit --svg werden zusaetzlich die SVG-Quellen abgelegt.
"""

import os
import sys

import cairosvg

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = ARGS[0] if ARGS else "out"
WRITE_SVG = "--svg" in sys.argv
os.makedirs(OUT, exist_ok=True)

# Jupiter-Palette: Creme, Sand, Rost, dunkles Band, roter Fleck
CREAM = "#F6DEB6"
SAND = "#E3AE6C"
RUST = "#C8672E"
BELT = "#8E4524"
SPOT = "#B93A24"
RING = "#1FA7B8"


def svg(outline: str) -> str:
    # Batterie: Koerper 176..336 x 116..436, Kappe darueber.
    # Ring: Ellipse um (256, 300), um -18 Grad gekippt. Hinterer Bogen
    # vor der Batterie gezeichnet (wird verdeckt), vorderer danach.
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <clipPath id="body">
      <rect x="176" y="116" width="160" height="320" rx="38"/>
    </clipPath>
    <clipPath id="front">
      <rect x="-200" y="300" width="912" height="400"/>
    </clipPath>
  </defs>

  <!-- hinterer Ringbogen -->
  <g transform="rotate(-18 256 300)">
    <ellipse cx="256" cy="300" rx="228" ry="62" fill="none"
             stroke="{outline}" stroke-width="40"/>
    <ellipse cx="256" cy="300" rx="228" ry="62" fill="none"
             stroke="{RING}" stroke-width="22"/>
  </g>

  <!-- Kappe -->
  <rect x="222" y="80" width="68" height="46" rx="12"
        fill="{SAND}" stroke="{outline}" stroke-width="16"/>

  <!-- Koerper mit Baendern -->
  <g clip-path="url(#body)">
    <rect x="176" y="116" width="160" height="320" fill="{CREAM}"/>
    <rect x="176" y="150" width="160" height="42" fill="{SAND}"/>
    <rect x="176" y="214" width="160" height="30" fill="{RUST}"/>
    <rect x="176" y="262" width="160" height="56" fill="{SAND}"/>
    <rect x="176" y="334" width="160" height="40" fill="{BELT}"/>
    <rect x="176" y="392" width="160" height="44" fill="{RUST}"/>
    <ellipse cx="292" cy="290" rx="24" ry="14" fill="{SPOT}"/>
  </g>
  <rect x="176" y="116" width="160" height="320" rx="38"
        fill="none" stroke="{outline}" stroke-width="16"/>

  <!-- vorderer Ringbogen -->
  <g transform="rotate(-18 256 300)" clip-path="url(#front)">
    <ellipse cx="256" cy="300" rx="228" ry="62" fill="none"
             stroke="{outline}" stroke-width="40"/>
    <ellipse cx="256" cy="300" rx="228" ry="62" fill="none"
             stroke="{RING}" stroke-width="22"/>
  </g>
</svg>
"""


variants = {
    "": "#1F2430",       # helle Oberflaeche: dunkle Kontur
    "dark_": "#E9ECF2",  # dunkle Oberflaeche: helle Kontur
}

for prefix, outline in variants.items():
    source = svg(outline)
    if WRITE_SVG:
        with open(os.path.join(OUT, f"{prefix}icon.svg"), "w") as fh:
            fh.write(source)
    for name in ("icon", "logo"):
        if prefix and name == "logo":
            continue
        cairosvg.svg2png(bytestring=source.encode(), write_to=os.path.join(
            OUT, f"{prefix}{name}.png"), output_width=256, output_height=256)
        cairosvg.svg2png(bytestring=source.encode(), write_to=os.path.join(
            OUT, f"{prefix}{name}@2x.png"), output_width=512, output_height=512)

print(sorted(os.listdir(OUT)))
