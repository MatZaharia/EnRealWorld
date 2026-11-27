"""Apply a force pulse to row 1 and measure the resulting rack motion."""

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess

import mujoco
import numpy as np


SCENE = Path(__file__).with_name("scene.xml")
ROW_COUNT = 7
DURATION_S = 8.0
PUSH_START_S = 0.5
PUSH_DURATION_S = 0.25
FPS = 25
WIDTH, HEIGHT = 960, 540


def replay(model, force_n, write_frame=None):
    data = mujoco.MjData(model)
    racks = [model.body(f"rack-{row}").id for row in range(ROW_COUNT)]
    push_site = model.site("push-0").id
    # Replication appends the rack row index to each rack and pallet name.
    body_rows = {
        body: int(model.body(body).name.rsplit("-", 1)[1])
        for body in range(1, model.nbody)
    }
    geom_rows = [body_rows.get(body) for body in model.geom_bodyid]
    rows = [
        {
            "row": row + 1,
            "first_5deg_s": None,
            "first_45deg_s": None,
            "peak_tilt_deg": 0.0,
            "first_contact_from_previous_s": None,
        }
        for row in range(ROW_COUNT)
    ]
    dt = model.opt.timestep
    push_start = round(PUSH_START_S / dt)
    push_end = round((PUSH_START_S + PUSH_DURATION_S) / dt)
    steps_per_frame = round(1 / (FPS * dt))
    contact_wrench = np.zeros(6)
    world_force = np.array([force_n, 0.0, 0.0])
    direct_impulse = np.zeros(ROW_COUNT)

    for step in range(round(DURATION_S / dt)):
        time_s = round(step * dt, 6)
        # Read poses and resolve contacts at this sample before integrating.
        mujoco.mj_step1(model, data)
        data.xfrc_applied.fill(0)
        if push_start <= step < push_end:
            lever = data.site_xpos[push_site] - data.xipos[racks[0]]
            data.xfrc_applied[racks[0], :3] = world_force
            data.xfrc_applied[racks[0], 3:] = np.cross(lever, world_force)
        direct_impulse += data.xfrc_applied[racks, 0] * dt

        for body, row in zip(racks, rows):
            tilt = math.degrees(math.acos(np.clip(data.xmat[body, 8], -1.0, 1.0)))
            row["peak_tilt_deg"] = max(row["peak_tilt_deg"], tilt)
            if tilt >= 5 and row["first_5deg_s"] is None:
                row["first_5deg_s"] = time_s
            if tilt >= 45 and row["first_45deg_s"] is None:
                row["first_45deg_s"] = time_s

        if write_frame is not None and step % steps_per_frame == 0:
            write_frame(data)

        mujoco.mj_step2(model, data)
        if data.warning[mujoco.mjtWarning.mjWARN_BADQACC].number:
            raise RuntimeError(f"Unstable simulation at {time_s:g} s")
        for i in range(data.ncon):
            contact = data.contact[i]
            a, b = (geom_rows[geom] for geom in contact.geom)
            if a is None or b is None or abs(a - b) != 1 or contact.efc_address < 0:
                continue
            downstream = rows[max(a, b)]
            if downstream["first_contact_from_previous_s"] is None:
                mujoco.mj_contactForce(model, data, i, contact_wrench)
                if contact_wrench[0] > 0:
                    downstream["first_contact_from_previous_s"] = time_s

    for row, impulse in zip(rows, direct_impulse):
        row["peak_tilt_deg"] = round(row["peak_tilt_deg"], 3)
        row["direct_impulse_ns"] = round(float(impulse), 6)

    return {
        "mujoco_version": mujoco.__version__,
        "timestep_s": dt,
        "duration_s": DURATION_S,
        "push": {
            "row": 1,
            "direction": "+X",
            "force_n": force_n,
            "start_s": PUSH_START_S,
            "duration_s": PUSH_DURATION_S,
        },
        "rows_at_45deg": sum(row["first_45deg_s"] is not None for row in rows),
        "rows": rows,
    }


def record_video(model, force_n, path, ffmpeg):
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-n",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-f", "mp4",
        str(path),
    ]
    with mujoco.Renderer(model, height=HEIGHT, width=WIDTH) as renderer:
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            def write_frame(data):
                renderer.update_scene(data, camera="overview")
                encoder.stdin.write(renderer.render().tobytes())

            result = replay(model, force_n, write_frame)
            encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError("FFmpeg could not encode the replay")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", required=True, type=float, help="force in newtons (>= 0)")
    parser.add_argument("--video", type=Path, help="write an MP4 replay with FFmpeg")
    args = parser.parse_args()
    if not math.isfinite(args.force) or args.force < 0:
        parser.error("--force must be finite and nonnegative")
    if args.video is not None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            parser.error("--video requires ffmpeg on PATH")
        if args.video.exists():
            parser.error("--video path already exists")
        if not args.video.parent.is_dir():
            parser.error("--video parent directory must exist")

    model = mujoco.MjModel.from_xml_path(str(SCENE))
    if args.video is None:
        result = replay(model, args.force)
    else:
        result = record_video(model, args.force, args.video, ffmpeg)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
