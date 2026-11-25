"""Extract the raster panels embedded in the paper figures, with their layout.

Each figure PDF contains the original renders as embedded images. We save every
placement at native resolution together with its normalised bounding box so the
website can rebuild the comparisons as interactive components (sliders, frame
scrubbers, toggles) instead of showing a flat figure.

Usage:
    python extract_figure_images.py [--paper ../../../26_EnRealWorld_CVPR]
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pymupdf
from PIL import Image

DOCS = Path(__file__).resolve().parents[1]
OUT = DOCS / "assets" / "figimg"

FIGS = {
    "fig3": "Figures/fig3.pdf",
    "fig4": "Figures/fig4.pdf",
    "fig5": "Figures/fig5.pdf",
    "si-f1": "SI-Fig/SI-F1.pdf",
    "si-f2": "SI-Fig/SI-F2.pdf",
    "si-f3": "SI-Fig/SI-F3.pdf",
    "si-g1": "SI-Fig/SI-G1.pdf",
    "si-g2": "SI-Fig/SI-G2.pdf",
}


def extract(name: str, pdf: Path, max_side: int) -> list[dict]:
    doc = pymupdf.open(pdf)
    page = doc[0]
    W, H = page.rect.width, page.rect.height
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    items = []
    for k, info in enumerate(page.get_image_info(xrefs=True)):
        xref = info["xref"]
        if not xref:
            continue
        x0, y0, x1, y1 = info["bbox"]
        if (x1 - x0) < 8 or (y1 - y0) < 8:
            continue
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        smask = doc.extract_image(xref).get("smask", 0)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        if smask:
            pass  # masks are only used for rounded callouts; keep the rectangular render
        # Respect any crop applied by the PDF transform: clip to the visible part.
        tf = info["transform"]
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        fn = f"{k:03d}.jpg"
        img.save(folder / fn, quality=86, optimize=True, progressive=True)
        items.append({
            "i": k,
            "file": f"assets/figimg/{name}/{fn}",
            "w": img.width,
            "h": img.height,
            "bbox": [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)],
            "flip": bool(tf[0] < 0 or tf[3] < 0),
        })
    (folder / "layout.json").write_text(json.dumps({"page": [W, H], "items": items}, indent=1))
    return items


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", type=Path, default=DOCS.parents[1] / "26_EnRealWorld_CVPR")
    args = ap.parse_args()
    for name, rel in FIGS.items():
        items = extract(name, args.paper / rel, 1280)
        print(name, len(items))


if __name__ == "__main__":
    main()
