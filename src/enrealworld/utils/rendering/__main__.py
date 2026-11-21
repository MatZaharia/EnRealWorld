"""Command-line entry point. Optional dependencies live in child processes."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

if __package__:
    from .presets import STYLE_NAMES, object_patterns
else:
    from presets import STYLE_NAMES, object_patterns

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        sha = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
        return sha.hexdigest()


def run(command, log):
    with log.open("w") as stream:
        try:
            subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stream,
                           stderr=subprocess.STDOUT, check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            print(error, file=stream)
            raise RuntimeError(f"See {log}") from error


def render(args, out, _manifest):
    source = args.source
    blend_args = ["--background", "--factory-startup", "--disable-autoexec"]
    if source.suffix.lower() == ".xml":
        run([args.mujoco_python, str(HERE / "mujoco_export.py"), str(out / "run.json")],
            out / "export.log")
    elif source.suffix.lower() == ".blend":
        blend_args.append(str(source))
    run([args.blender, *blend_args, "--python-exit-code", "1", "--threads", str(args.threads),
         "--python", str(HERE / "blender_render.py"), "--", str(out / "run.json")],
        out / "blender.log")


def enhance(args, out, manifest):
    output = out / "enhanced.mp4"
    run([args.backend, str(args.source), str(output)], out / "backend.log")
    run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output),
         "-map", "0:v:0", "-f", "null", "-"], out / "decode.log")
    manifest["output_sha256"] = digest(output)


def main():
    parser = argparse.ArgumentParser(description="Render scenes in Blender with the render command.")
    commands = parser.add_subparsers(dest="mode", required=True)
    traditional = commands.add_parser("render", help="Render a snapshot or animation in Blender")
    traditional.add_argument("source", type=lambda value: Path(value).resolve(strict=True))
    traditional.add_argument("--config", type=Path, help="Camera, focus and light rig JSON")
    traditional.add_argument("--state", type=lambda value: Path(value).resolve(strict=True),
                             help="MuJoCo NPZ with qpos and time_s arrays")
    traditional.add_argument("--time", type=float, help="Select the nearest NPZ timestamp")
    traditional.add_argument("--frame", type=int, help="Frame for USD or Blender snapshot")
    traditional.add_argument("--animate", action="store_true", help="Render the recorded timeline")
    traditional.add_argument("--start", type=float, help="Animation start in seconds")
    traditional.add_argument("--end", type=float, help="Animation end in seconds")
    traditional.add_argument("--fps", type=int, help="Animation output FPS (default 24 for MJCF)")
    traditional.add_argument("--passes", nargs="+", choices=("depth", "normal", "segmentation"),
                             default=[], help="Export numerical NPZ arrays and preview PNGs")
    traditional.add_argument("--styles", nargs="+", choices=(*STYLE_NAMES, "all"), default=["studio"],
                             help="Select styles (default: studio); all includes xray and needs xray_objects")
    traditional.add_argument("--size", nargs=2, type=int, default=[960, 720],
                             metavar=("WIDTH", "HEIGHT"))
    traditional.add_argument("--samples", type=int, default=32)
    traditional.add_argument("--threads", type=int, default=8)
    traditional.add_argument("--orbit", action="store_true", help="Studio camera arc around a fixed pose")
    traditional.add_argument("--orbit-size", nargs=2, type=int, default=[576, 432])
    traditional.add_argument("--orbit-frames", type=int, default=72)
    traditional.add_argument("--orbit-fps", type=int, default=24)
    traditional.add_argument("--orbit-samples", type=int, default=12)
    traditional.add_argument("--blender", default=os.environ.get("BLENDER_BIN", "blender"))
    traditional.add_argument("--mujoco-python", default=os.environ.get("MUJOCO_PYTHON", sys.executable))
    model = commands.add_parser(
        "enhance", help="Run an explicitly supplied video backend",
        description="Optional extension. No video backend is bundled or selected by default.",
    )
    model.add_argument("source", type=lambda value: Path(value).resolve(strict=True))
    model.add_argument("--backend", required=True,
                       help="Executable called with INPUT_VIDEO and OUTPUT_MP4 as positional arguments")
    for command in (traditional, model):
        command.add_argument("--out", type=Path, required=True, help="New output directory")

    args = parser.parse_args()
    if args.mode == "render":
        suffix = args.source.suffix.lower()
        if suffix not in {".xml", ".usd", ".usda", ".usdc", ".usdz", ".blend"}:
            parser.error("Expected MJCF, USD or .blend")
        if args.state and suffix != ".xml":
            parser.error("--state is for MJCF only")
        if args.animate:
            if args.time is not None or args.frame is not None or args.orbit:
                parser.error("--animate cannot be combined with --time, --frame or --orbit")
            if suffix == ".xml" and not args.state:
                parser.error("MJCF animation requires --state")
            if any(n < 2 or n % 2 for n in args.size):
                parser.error("Animation needs positive even dimensions")
        elif (args.state is None) != (args.time is None) or any(
            value is not None for value in (args.start, args.end, args.fps)
        ):
            parser.error("Use --state with --time for a still, or --animate for a timeline")
        if any(value is not None and not math.isfinite(value)
               for value in (args.time, args.start, args.end)):
            parser.error("Times must be finite")
        if args.fps is not None and not 1 <= args.fps <= 240:
            parser.error("Animation FPS must be between 1 and 240")
        args.passes = list(dict.fromkeys(args.passes))
        if args.frame is not None and suffix == ".xml":
            parser.error("--frame is for USD and Blender inputs")
        if "all" in args.styles and args.styles != ["all"]:
            parser.error("Use --styles all on its own")
        args.styles = list(STYLE_NAMES) if args.styles == ["all"] else list(dict.fromkeys(args.styles))
        if args.orbit and "studio" not in args.styles:
            parser.error("--orbit requires studio")
        if min(*args.size, args.samples, args.threads, args.orbit_samples, args.orbit_fps) < 1:
            parser.error("Render sizes, samples, threads and FPS must be positive")
        if args.orbit and (args.orbit_frames < 2 or any(n < 2 or n % 2 for n in args.orbit_size)):
            parser.error("Orbit needs at least two frames and positive even dimensions")

    out = args.out.resolve()
    settings = vars(args).copy()
    if args.mode == "render":
        settings["config"] = json.loads(args.config.read_text()) if args.config else {}
        if not isinstance(settings["config"], dict):
            parser.error("Expected a JSON object for --config")
        try:
            if "xray" in args.styles:
                object_patterns(settings["config"], "xray_objects")
            if "silhouette" in args.styles and "silhouette_objects" in settings["config"]:
                object_patterns(settings["config"], "silhouette_objects")
        except ValueError as error:
            parser.error(str(error))
    inputs = [args.source]
    if args.mode == "render" and args.state:
        inputs.append(args.state)
    hashes = {str(path): digest(path) for path in inputs}
    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error(f"Output directory already exists: {out}")
    manifest = {"settings": settings, "input_sha256": hashes, "status": "running"}
    manifest_path = out / "run.json"

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")

    save()
    start = time.monotonic()
    try:
        operation = render if args.mode == "render" else enhance
        operation(args, out, manifest)
        manifest["status"] = "complete"
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest["elapsed_seconds"] = round(time.monotonic() - start, 3)
        manifest["inputs_unchanged"] = all(digest(Path(path)) == sha for path, sha in hashes.items())
        save()
    if not manifest["inputs_unchanged"]:
        raise RuntimeError(f"Input changed during the run. See {manifest_path}")


if __name__ == "__main__":
    main()
