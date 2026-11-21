"""Export MuJoCo geometry and sample recorded visual states."""
import json
from pathlib import Path
import sys

import mujoco
from mujoco.usd import exporter
import numpy as np
from PIL import Image
from pxr import Tf, Usd, UsdGeom

from timeline import timestamps


class IdentifierSafeExporter(exporter.USDExporter):
    def _get_geom_name(self, geom):
        return Tf.MakeValidIdentifier(super()._get_geom_name(geom))


def unit(vector):
    length = np.linalg.norm(vector)
    if not np.isfinite(length) or length < 1e-10:
        raise ValueError("Camera eye, target and up must define a valid orientation")
    return vector / length


def main(run_path):
    args = json.loads(run_path.read_text())["settings"]
    out = run_path.parent
    config = args["config"]
    width, height = args["size"]
    spec = mujoco.MjSpec.from_file(args["source"])
    frame = spec.worldbody
    camera = config.get("camera")
    if isinstance(camera, dict):
        eye, target = (np.asarray(camera[key], dtype=float) for key in ("eye", "target"))
        back = unit(eye - target)
        right = unit(np.cross(camera.get("up", [0, 0, 1]), back))
        up = np.cross(back, right)
        if camera.get("body"):
            frame = spec.body(camera["body"])
            if frame is None:
                raise ValueError(f"Unknown camera body {camera['body']!r}")
        camera_name = "_enrealworld_render_camera"
        frame.add_camera(name=camera_name, pos=eye, xyaxes=np.concatenate([right, up]),
                         fovy=camera.get("fovy", 40))
    else:
        camera_name = camera

    model = spec.compile()
    data = mujoco.MjData(model)
    index = None
    archive = {}
    missing = []
    samples = []
    sample_times = []
    fps = args["fps"] or 24
    if args["state"]:
        with np.load(args["state"], allow_pickle=False) as states:
            times = states["time_s"]
            if (times.ndim != 1 or not len(times) or not np.isfinite(times).all()
                    or np.any(np.diff(times) <= 0)):
                raise ValueError("Expected finite, strictly increasing time_s[N]")
            fields = {"qpos": (model.nq,), "qvel": (model.nv,), "act": (model.na,),
                      "ctrl": (model.nu,), "mocap_pos": (model.nmocap, 3),
                      "mocap_quat": (model.nmocap, 4), "eq_active": (model.neq,)}
            for field, shape in fields.items():
                if field in states:
                    values = states[field]
                    if values.shape != (len(times), *shape) or not np.isfinite(values).all():
                        raise ValueError(f"Invalid archived {field}, expected {(len(times), *shape)}")
                    archive[field] = values
                elif all(shape):
                    missing.append(field)
            if "qpos" not in archive:
                raise ValueError("Archive must contain qpos")
            if args["animate"] and model.nmocap and ({"mocap_pos", "mocap_quat"} & set(missing)):
                raise ValueError("Mocap bodies require archived mocap_pos and mocap_quat")
        sample_times = (timestamps(times[0], times[-1], args["start"], args["end"], fps)
                        if args["animate"] else [args["time"]])
        for time in sample_times:
            right = int(np.searchsorted(times, time))
            left = max(0, right - 1)
            right = min(right, len(times) - 1)
            samples.append(min((left, right), key=lambda i: abs(times[i] - time)))
        index = samples[0]

    def set_pose(i):
        if i is not None:
            for field, values in archive.items():
                getattr(data, field)[:] = values[i]
            data.time = float(times[i])
        mujoco.mj_forward(model, data)

    set_pose(index)
    if camera_name is None and model.ncam:
        camera_name = 0

    def camera_pose():
        if camera_name is None:
            return None
        cam = data.camera(camera_name)
        if bool(model.cam_orthographic[cam.id]):
            raise ValueError("Use a perspective MuJoCo camera")
        return dict(position=cam.xpos.tolist(), rotation=cam.xmat.reshape(3, 3).tolist(),
                    fovy=float(model.cam_fovy[cam.id]))

    camera_info = camera_pose()
    focus = config.get("focus")
    if camera_name is not None:
        cam = data.camera(camera_name)
        if bool(model.cam_orthographic[cam.id]):
            raise ValueError("Use a perspective MuJoCo camera")
        camera_info = {
            "position": cam.xpos.tolist(),
            "rotation": cam.xmat.reshape(3, 3).tolist(),
            "fovy": float(model.cam_fovy[cam.id]),
        }
    rig_rotation = np.eye(3)
    if isinstance(camera, dict):
        body = data.body(camera.get("body", "world"))
        rig_rotation = body.xmat.reshape(3, 3)
        if focus is None:
            focus = (body.xpos + rig_rotation @ target).tolist()

    options = mujoco.MjvOption()
    options.sitegroup[:] = 0
    options.geomgroup[:] = 0
    options.geomgroup[config.get("geom_groups", [0, 1, 2])] = 1
    model.vis.global_.offwidth = max(model.vis.global_.offwidth, width)
    model.vis.global_.offheight = max(model.vis.global_.offheight, height)
    exp = IdentifierSafeExporter(model=model, width=width, height=height,
                                 max_geom=max(10000, 2 * model.ngeom),
                                 output_directory="usd", output_directory_root=str(out))
    exp.update_scene(data, scene_option=options)
    UsdGeom.SetStageMetersPerUnit(exp.stage, 1.0)
    exp.save_scene(filetype="usdc")
    path = out / "usd/frames/frame_1.usdc"
    stage = Usd.Stage.Open(str(path))
    geometry = {}
    for geom in exp.scene.geoms[:exp.scene.ngeom]:
        name = exp._get_geom_name(geom)
        geometry[name] = {
            "mujoco_geom_id": (int(geom.objid)
                              if geom.objtype == mujoco.mjtObj.mjOBJ_GEOM else None),
            "mujoco_geom_name": (model.geom(geom.objid).name
                                 if geom.objtype == mujoco.mjtObj.mjOBJ_GEOM else None),
            "position": geom.pos.tolist(),
            "rotation": geom.mat.reshape(3, 3).tolist(),
            "box_size": geom.size.tolist() if geom.type == mujoco.mjtGeom.mjGEOM_BOX else None,
        }
    count = sum(prim.IsA(UsdGeom.Mesh) for prim in stage.Traverse())
    if not count or count != len(geometry):
        raise RuntimeError(f"USD contains {count} meshes for {len(geometry)} visual geoms")
    metadata = dict(mujoco=mujoco.__version__, usd=Usd.GetVersion(), pose_index=index,
                    time_s=data.time, mesh_count=count, model_geom_count=model.ngeom,
                    geometry=geometry, camera=camera_info, focus=focus,
                    rig_rotation=rig_rotation.tolist(), restored_fields=list(archive),
                    missing_fields=missing)
    (out / "export.json").write_text(json.dumps(metadata, indent=2))
    if config.get("mujoco_preview"):
        with mujoco.Renderer(model, height=height, width=width) as renderer:
            renderer.update_scene(data, camera=camera_name if camera_name is not None else -1,
                                  scene_option=options)
            Image.fromarray(renderer.render()).save(out / "mujoco.png")


    if args["animate"]:
        names = list(geometry)
        if any(geom["mujoco_geom_id"] is None for geom in geometry.values()):
            raise ValueError("Animated MJCF currently supports rigid geoms only (no tendons or decorations)")
        ids = [geometry[name]["mujoco_geom_id"] for name in names]
        # MjvGeom poses can differ from raw geom poses for viewer-adjusted geometry.
        # Record the same visual transforms that the USD exporter uses at frame one.
        frames = []
        for frame, (sample_time, i) in enumerate(zip(sample_times, samples), start=1):
            set_pose(i)
            exp._update_scene(data, scene_option=options)
            geoms = {exp._get_geom_name(g): g for g in exp.scene.geoms[:exp.scene.ngeom]}
            if geoms.keys() != geometry.keys():
                raise ValueError("Animated MJCF requires stable visual geometry across frames")
            frames.append(dict(frame=frame, requested_time_s=float(sample_time),
                               source_index=i, source_time_s=float(times[i]), camera=camera_pose(),
                               positions=[geoms[n].pos.tolist() for n in names],
                               rotations=[geoms[n].mat.reshape(3, 3).tolist() for n in names]))
        (out / "trajectory.json").write_text(json.dumps(
            dict(fps=fps, names=names, geom_ids=ids, frames=frames,
                 archive_range_s=[float(times[0]), float(times[-1])]), separators=(",", ":")))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
