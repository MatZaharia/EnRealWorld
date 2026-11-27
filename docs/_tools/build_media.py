"""Build web-ready media for the EnRealWorld project page.

Reads the curated `Resources-for-website` folder and the paper sources, then
writes compressed videos, posters, thumbnails, images and figure renders into
`docs/assets`. Everything is re-runnable; existing outputs are skipped unless
`--force` is given.

Usage:
    python build_media.py [--res ../../../Resources-for-website] [--paper ../../../26_EnRealWorld_CVPR]
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

DOCS = Path(__file__).resolve().parents[1]
ASSETS = DOCS / "assets"
FORCE = False

MODEL_DIRS = {
    "GPT-6.1 Sol": ("gpt", "gpt-6.1-sol"),
    "DeepSeek-V4.1-Flash-1017": ("deepseek", "deepseek-flash"),
    "Kimi-3.1 Pro": ("kimi", "k3.1-pro"),
}

CASE_ACTIONS = {
    "02_dexycb-lift-bimanual": "Lift a box with both hands",
    "11_inhouse-point-origin-pick-and-hold": "Pick up and hold a small object",
    "17_inhouse-provider-cracker": "Lift a box of crackers",
    "20_inhouse-wallet-initially-held-insert": "Put a wallet into a handbag",
    "24_robodojo-task-x5-r1": "Stack blocks",
    "30_cabinet-top": "Fit the cabinet top",
    "31_chair-nut": "Fasten a chair nut",
    "33_rope-route": "Route a rope around a guide",
    "36_leg-insert": "Insert a table leg",
    "37_hood-place": "Place the lamp shade",
    "39_round-table-base": "Assemble the round table base",
}

# (source relative to Resources-for-website, output name, max width, keep audio)
VIDEOS = [
    ("02-One-sentence-three-worlds/Media/Three-worlds-assembly.mp4", "three-worlds-assembly", 1600, False),
    ("02-One-sentence-three-worlds/Media/Laboratory-robot-pick-and-place-silent.mp4", "laboratory-robots", 1280, False),
    ("02-One-sentence-three-worlds/Media/Warehouse.mp4", "warehouse", 1280, False),
    ("02-One-sentence-three-worlds/Media/Home.mp4", "home", 1280, False),
    ("04-Architectural-drawings/Media/Three-buildings-assembly-1080p60.mp4", "three-buildings-assembly", 1600, False),
    ("04-Architectural-drawings/Media/Drawings-floor-by-floor.mp4", "drawings-floor-by-floor", 1280, False),
    ("04-Architectural-drawings/yates/Media/EnRealWorld-walkthrough.mp4", "yates-walkthrough", 960, False),
    ("03-Paintings/studio/Video/ours-Studio-A-daylight.mp4", "studio-daylight", 1280, False),
    ("03-Paintings/railroad/Video/Claude-Fable-5.2/Railroad-House-two-reviews.mp4", "railroad-two-reviews", 1280, False),
    ("03-Paintings/railroad/Video/Claude-Fable-5.2/Railroad-House-component-flight.mp4", "railroad-component-flight", 1280, False),
    ("03-Paintings/railroad/Video/Claude-Fable-5.2/Railroad-House-porch-review-v2.mp4", "railroad-porch-review", 1280, False),
    ("05-Scene-interventions/Case-media/factory/02-rack-domino/ours-Three-worlds-C-factory-domino.mp4", "factory-rack-domino", 1280, False),
    ("05-Scene-interventions/Case-media/factory/03-rack-spill/ours-rack-spill-motion-check.mp4", "factory-rack-spill", 864, False),
    ("05-Scene-interventions/Case-media/home/02-pillow-release/ours-Three-worlds-interaction-walk.mp4", "home-pillow-release", 1280, False),
    ("05-Scene-interventions/Case-media/laboratory/02-chair-release/ours-Three-worlds-unseen-force.mp4", "laboratory-unseen-force", 1280, False),
    ("05-Scene-interventions/Case-media/laboratory/03-walkthrough/ours-Three-worlds-C-interior-finale.mp4", "laboratory-interior", 1280, False),
    ("05-Scene-interventions/Case-media/physcodegym-lemon/01-preview/ref-reference.mp4", "lemon-reference", 640, False),
    ("05-Scene-interventions/Case-media/physcodegym-lemon/01-preview/base-generated.mp4", "lemon-base", 640, False),
    ("05-Scene-interventions/Case-media/physcodegym-lemon/01-preview/ours-candidate.mp4", "lemon-ours", 640, False),
    ("05-Scene-interventions/Case-media/yates/03-accepted-native/barrier-true.gif", "yates-barrier-on", 1000, False),
    ("05-Scene-interventions/Case-media/yates/03-accepted-native/barrier-false.gif", "yates-barrier-off", 1000, False),
    ("01-Video2World/16-case-wall/Video2World-wall-v12.mp4", "v2w-wall", 1920, False),
    ("01-Video2World/Pilot-demos/DexYCB-144814-pilot/Media/ref-video.mp4", "dexycb-pilot-ref", 640, False),
    ("01-Video2World/Pilot-demos/DexYCB-144814-pilot/Media/base-A.mp4", "dexycb-pilot-base", 1280, False),
    ("01-Video2World/Pilot-demos/DexYCB-144814-pilot/Media/ours-Ours_v5.mp4", "dexycb-pilot-ours", 1280, False),
    ("01-Video2World/Pilot-demos/Push-T-v53-pilot/Media/ref-push-t-twin_pusht_demo_0-input.mp4", "pusht-ref", 480, False),
    ("01-Video2World/Pilot-demos/Push-T-v53-pilot/Media/ours-saved-state-h264.mp4", "pusht-ours", 1280, False),
]

IMAGES = [
    ("03-Paintings/studio/Reference/Original-painting.png", "img/painting-studio.jpg", 1800),
    ("03-Paintings/railroad/Reference/Original-painting.png", "img/painting-railroad.jpg", 1800),
    ("03-Paintings/railroad/Preview-only/EnRealWorld-GPT-6.2-Astra.png", "img/railroad-ours-gpt-6-2-astra-preview.jpg", 1600),
]

FIGURES = {
    "Figures/fig1.pdf": "fig1",
    "Figures/fig2.pdf": "fig2",
    "Figures/fig3.pdf": "fig3",
    "Figures/fig4.pdf": "fig4",
    "Figures/fig5.pdf": "fig5",
    "Figures/fig7.pdf": "fig7",
    "Figures/fig8.pdf": "fig8",
    "SI-Fig/SI-F1.pdf": "si-f1",
    "SI-Fig/SI-F2.pdf": "si-f2",
    "SI-Fig/SI-F3.pdf": "si-f3",
    "SI-Fig/SI-G1.pdf": "si-g1",
    "SI-Fig/SI-G2.pdf": "si-g2",
    "SI-Fig/Video2World-aligned.pdf": "v2w-aligned",
}


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fresh(out: Path) -> bool:
    return FORCE or not out.exists()


def probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = (int(x) for x in s["r_frame_rate"].split("/"))
    return {"w": s["width"], "h": s["height"], "fps": num / den if den else 0,
            "duration": float(j["format"].get("duration", 0) or 0)}


def transcode(src: Path, out: Path, max_w: int, crf: int = 26) -> None:
    if not fresh(out):
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    vf = [f"scale='min({max_w},iw)':-2:flags=lanczos"]
    if info["fps"] > 31:
        vf.append("fps=30")
    vf.append("format=yuv420p")
    run(["ffmpeg", "-y", "-i", str(src), "-vf", ",".join(vf), "-c:v", "libx264",
         "-preset", "slow", "-crf", str(crf), "-profile:v", "high", "-movflags", "+faststart",
         "-an", str(out)])


def frame(src: Path, out: Path, at: float, width: int) -> None:
    if not fresh(out):
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1",
         "-vf", f"scale='min({width},iw)':-2:flags=lanczos", "-q:v", "3", str(out)])


def video_job(res: Path, rel: str, name: str, max_w: int) -> dict:
    src = res / rel
    out = ASSETS / "video" / f"{name}.mp4"
    transcode(src, out, max_w)
    info = probe(out)
    frame(out, ASSETS / "video" / f"{name}.jpg", min(1.0, info["duration"] * 0.25), max_w)
    return {"name": name, **info, "bytes": out.stat().st_size}


def v2w_job(res: Path, row: dict, wall: dict) -> dict:
    short, folder = MODEL_DIRS[row["model"]]
    case = row["case"]
    base = res / "01-Video2World" / "51-accepted-media" / folder / case
    out = ASSETS / "v2w" / short / case
    transcode(base / "source.mp4", out / "src.mp4", 640, 27)
    transcode(base / "result-display.mp4", out / "ours.mp4", 640, 27)
    si, oi = probe(out / "src.mp4"), probe(out / "ours.mp4")
    frame(out / "src.mp4", out / "src.jpg", 0.0, 640)
    frame(out / "ours.mp4", out / "ours.jpg", 0.0, 640)
    thumb = out / "thumb.jpg"
    if fresh(thumb):
        at = min(si["duration"], oi["duration"]) * 0.55
        run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(out / "src.mp4"), "-ss", f"{at:.2f}",
             "-i", str(out / "ours.mp4"), "-filter_complex",
             "[0:v]scale=-2:150,crop=min(iw\\,200):150[a];[1:v]scale=-2:150,crop=min(iw\\,200):150[b];[a][b]hstack",
             "-frames:v", "1", "-q:v", "4", str(thumb)])
    slug = case.split("_", 1)[1]
    prefix = row["episode"].split("/")[1].split("_")[0]
    source = {"dexycb": "DexYCB", "droid": "DROID", "inhouse": "In-house",
              "robodojo": "RoboDojo"}.get(prefix, "Other")
    return {
        "id": f"{short}/{case}",
        "model": row["model"],
        "modelKey": short,
        "case": case,
        "num": int(case.split("_")[0]),
        "task": slug.replace("-", " "),
        "source": source,
        "episode": row["episode"],
        "alignment": row["alignment"],
        "action": wall.get(case) or CASE_ACTIONS.get(case, ""),
        "srcDuration": round(si["duration"], 2),
        "oursDuration": round(oi["duration"], 2),
        "aspect": round(si["w"] / si["h"], 4),
        "path": f"assets/v2w/{short}/{case}",
    }


def image_job(src: Path, out: Path, max_side: int, quality: int = 86) -> None:
    if not fresh(out):
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    im.save(out, quality=quality, optimize=True, progressive=True)


def figures(paper: Path) -> list[dict]:
    import pymupdf

    out = []
    for rel, name in FIGURES.items():
        pdf = paper / rel
        if not pdf.exists():
            continue
        page = pymupdf.open(pdf)[0]
        target = ASSETS / "fig" / f"{name}.webp"
        width = 2600 if page.rect.width > 600 else 1600
        zoom = width / page.rect.width
        if fresh(target):
            target.parent.mkdir(parents=True, exist_ok=True)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img.save(target, "WEBP", quality=88, method=6)
        out.append({"name": name, "w": int(page.rect.width * zoom), "h": int(page.rect.height * zoom)})
    return out


def main() -> None:
    global FORCE
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=Path, default=DOCS.parents[1] / "Resources-for-website")
    ap.add_argument("--paper", type=Path, default=DOCS.parents[1] / "26_EnRealWorld_CVPR")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    FORCE = args.force
    res = args.res

    wall = {}
    with open(res / "01-Video2World/16-case-wall/WALL-CASES.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            wall[r["folder"]] = r["action"]
    with open(res / "01-Video2World/CASE-INDEX.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    with ThreadPoolExecutor(max_workers=6) as pool:
        cases = list(pool.map(lambda r: v2w_job(res, r, wall), rows))
        vids = list(pool.map(lambda v: video_job(res, v[0], v[1], v[2]), VIDEOS))

    cases.sort(key=lambda c: (["gpt", "deepseek", "kimi"].index(c["modelKey"]), c["num"]))
    (ASSETS / "v2w" / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False))
    (ASSETS / "video" / "videos.json").write_text(json.dumps(vids, indent=1))

    for rel, out, side in IMAGES:
        image_job(res / rel, ASSETS / out, side)
    for b in ("yates", "ranch", "lighthouse"):
        for p in sorted((res / "04-Architectural-drawings" / b / "Original-HABS-sheets").glob("*.jpg")):
            image_job(p, ASSETS / "img" / "habs" / b / p.name, 2000, 84)
    for p in sorted((res / "05-Scene-interventions" / "Image-only").rglob("*")):
        if p.suffix.lower() in {".jpg", ".png"}:
            rel = p.relative_to(res / "05-Scene-interventions" / "Image-only")
            image_job(p, ASSETS / "img" / "probes" / rel.with_suffix(".jpg"), 1800, 86)

    figs = figures(args.paper)
    (ASSETS / "fig" / "figures.json").write_text(json.dumps(figs, indent=1))
    print(f"cases={len(cases)} videos={len(vids)} figures={len(figs)}")


if __name__ == "__main__":
    main()
