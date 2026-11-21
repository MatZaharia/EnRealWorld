"""Render stills, motion and data passes in Blender."""
from contextlib import ExitStack
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_passes import render_passes
from blender_styles import apply_style, pixel_finish
from presets import select_objects
from timeline import timestamps

# Offsets are expressed in scene radii, and light power scales with radius squared.
STYLES = {
    "studio": ((0.33, 0.41, 0.45), 0.4, (
        ("Key", (-1.3, -1.2, 1.8), 100, 1.6, (1, 0.88, 0.73)),
        ("Fill", (1.25, -0.5, 0.9), 48, 1.25, (0.74, 0.87, 1)),
        ("Rim", (0.2, 1.4, 1.4), 95, 1.0, (1, 0.92, 0.81)),
    )),
    "clay": ((0.55, 0.59, 0.66), 0.16, (
        ("Key", (-1.3, -0.8, 1.4), 85, 0.9, (1, 1, 1)),
        ("Fill", (1.25, -1, 0.85), 28, 1.1, (1, 1, 1)),
        ("Rim", (0.8, 1.2, 1.4), 55, 1.0, (1, 1, 1)),
    )),
    "dramatic": ((0.11, 0.19, 0.29), 0.15, (
        ("Amber key", (-1.1, -0.75, 1.05), 85, 0.65, (1, 0.41, 0.12)),
        ("Cyan rim", (1.0, 1.05, 1.35), 160, 0.8, (0.12, 0.62, 1)),
        ("Bounce", (0.8, -1.35, 0.85), 19, 1.2, (0.57, 0.78, 1)),
    )),
    "technical": ((0.66, 0.73, 0.83), 0.45, (
        ("Soft key", (-0.9, -1.0, 1.75), 110, 2.0, (1, 0.97, 0.92)),
        ("Soft fill", (1.25, 0.25, 0.9), 47, 1.65, (0.86, 0.94, 1)),
    )),
    "metal": ((0.075, 0.10, 0.15), 0.28, (
        ("Strip key", (-1.1, -1.15, 1.5), 180, 1.45, (1, 0.92, 0.8)),
        ("Strip fill", (1.35, -0.35, 0.65), 85, 1.05, (0.68, 0.84, 1)),
        ("Rim", (0.0, 1.5, 1.4), 155, 1.1, (1, 0.84, 0.64)),
    )),
    "lineart": ((1, 1, 1), 1, ()),
    "blueprint": ((0.008, 0.025, 0.077), 1, ()),
    "silhouette": ((0.88, 0.75, 0.57), 1, ()),
}


def aim(obj, target):
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def check_geometry(meshes, exported):
    if not exported:
        return {}
    by_name = {obj.name.removeprefix("Mesh_"): obj for obj in meshes}
    if by_name.keys() != exported.keys() or len(meshes) != len(exported):
        raise RuntimeError(f"Missing meshes: {exported.keys() - by_name.keys()}; "
                           f"unexpected meshes: {by_name.keys() - exported.keys()}")
    metrics = {}
    for name, geom in exported.items():
        obj = by_name[name]
        matrix = obj.matrix_world
        position = (matrix.translation - Vector(geom["position"])).length
        rotation = max(abs(matrix[r][c] - geom["rotation"][r][c])
                       for r in range(3) for c in range(3))
        if position > 1e-5 or rotation > 1e-5:
            raise RuntimeError(f"USD transform mismatch for {name}: {position}, {rotation}")
        dims = [max(point[i] for point in obj.bound_box) - min(point[i] for point in obj.bound_box)
                for i in range(3)]
        if geom["box_size"]:
            if max(abs(dim - 2 * half) for dim, half in zip(dims, geom["box_size"])) > 1e-5:
                raise RuntimeError(f"USD box size mismatch for {name}: {dims}")
            for polygon in obj.data.polygons:
                polygon.use_smooth = False
        metrics[name] = dict(position_error_m=position, rotation_error=rotation,
                             dimensions=dims, vertices=len(obj.data.vertices))
    return metrics


def camera_for(scene, config, snapshot, focus, radius):
    camera_config = config.get("camera")
    pose = snapshot.get("camera")
    if pose is None and isinstance(camera_config, str):
        scene.camera = scene.objects.get(camera_config)
        if scene.camera is None or scene.camera.type != "CAMERA":
            raise ValueError(f"Unknown camera {camera_config!r}")
    if pose is None and not isinstance(camera_config, dict):
        if scene.camera is None:
            scene.camera = next((obj for obj in scene.objects if obj.type == "CAMERA"), None)
        if scene.camera:
            return scene.camera
    data = bpy.data.cameras.new("Render Camera")
    data.sensor_fit = "VERTICAL"
    data.clip_start = max(0.0001, radius * 0.002)
    data.clip_end = max(100, radius * 100)
    camera = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(camera)
    if pose:
        data.angle_y = math.radians(pose["fovy"])
        camera.matrix_world = Matrix(pose["rotation"]).to_4x4()
        camera.location = pose["position"]
    else:
        settings = camera_config or {}
        data.angle_y = math.radians(settings.get("fovy", 40))
        camera.location = settings.get("eye", focus + radius * Vector((1.8, -2.7, 1.8)))
        aim(camera, Vector(settings.get("target", focus)))
    scene.camera = camera
    return camera


def set_frame(scene, frame):
    whole = math.floor(frame)
    scene.frame_set(whole, subframe=frame - whole)


def key_pose(obj, frame, position, rotation):
    quat = Matrix(rotation).to_quaternion()
    if obj.rotation_quaternion.dot(quat) < 0:
        quat.negate()
    obj.location = position
    obj.rotation_quaternion = quat
    obj.keyframe_insert("location", frame=frame)
    obj.keyframe_insert("rotation_quaternion", frame=frame)


def animation_plan(scene, meshes, camera, args, out, kind, usd_rate):
    if kind == ".xml":
        track = json.loads((out / "trajectory.json").read_text())
        by_name = {obj.name.removeprefix("Mesh_"): obj for obj in meshes}
        animated = [by_name[name] for name in track["names"]]
        for obj in [*animated, camera]:
            world = obj.matrix_world.copy()
            obj.parent = None
            obj.animation_data_clear()
            obj.rotation_mode = "QUATERNION"
            obj.matrix_world = world
        for pose in track["frames"]:
            frame = pose["frame"]
            for obj, position, rotation in zip(animated, pose["positions"], pose["rotations"]):
                key_pose(obj, frame, position, rotation)
            if pose["camera"]:
                key_pose(camera, frame, pose["camera"]["position"], pose["camera"]["rotation"])
        scene.frame_start, scene.frame_end = 1, len(track["frames"])
        scene.render.fps, scene.render.fps_base = track["fps"], 1
        fps = track["fps"]
        rows = [{key: pose[key] for key in ("frame", "requested_time_s", "source_index", "source_time_s")}
                for pose in track["frames"]]
    else:
        native_fps = usd_rate or scene.render.fps / scene.render.fps_base
        fps = args["fps"] or native_fps
        first = scene.frame_start
        end = (scene.frame_end - first) / native_fps
        times = timestamps(0.0, end, args["start"], args["end"], fps)
        rows = [dict(frame=first + t * native_fps, source_time_s=t) for t in times]
    for output_index, row in enumerate(rows, 1):
        row["output_frame"] = output_index
        row["video_time_s"] = (output_index - 1) / fps
    (out / "frames.json").write_text(json.dumps(dict(fps=fps, frames=rows), indent=2))
    return [row["frame"] for row in rows], fps


def encode_video(folder, fps, destination):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
                    "-framerate", str(fps), "-start_number", "0",
                    "-i", str(Path(folder) / "%04d.png"), "-c:v", "libx264",
                    "-crf", "19", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(destination)], check=True)


def render_still(scene, style, path):
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if style == "pixel":
        pixel_finish(path, scene.render.resolution_x, scene.render.resolution_y)


def render_motion(scene, frames, fps, style, out):
    with tempfile.TemporaryDirectory(dir=out) as temp:
        for index, frame in enumerate(frames):
            set_frame(scene, frame)
            frame_path = Path(temp) / f"{index:04d}.png"
            render_still(scene, style, frame_path)
            if index == 0:
                (out / f"{style}.png").write_bytes(frame_path.read_bytes())
        encode_video(temp, fps, out / f"{style}.mp4")


def render_orbit(scene, camera, focus, axis, args, out):
    # A separate camera avoids modifying source animation or relying on its drivers.
    orbit = bpy.data.objects.new("Orbit Camera", camera.data.copy())
    scene.collection.objects.link(orbit)
    scene.camera = orbit
    offset = camera.matrix_world.translation - focus
    orientation = camera.matrix_world.to_quaternion()
    orbit.rotation_mode = "QUATERNION"
    if offset.length < 1e-8:
        raise ValueError("Orbit target coincides with the camera")
    scene.render.resolution_x, scene.render.resolution_y = args["orbit_size"]
    scene.cycles.samples = args["orbit_samples"]
    frames = args["orbit_frames"]
    with tempfile.TemporaryDirectory(dir=out) as temp:
        for frame in range(frames):
            t = frame / (frames - 1)
            angle = math.radians(-21 * math.cos(math.pi * t))
            yaw = Quaternion(axis, angle)
            orbit.location = focus + yaw @ offset
            orbit.rotation_quaternion = yaw @ orientation
            scene.render.filepath = str(Path(temp) / f"{frame:04d}.png")
            bpy.ops.render.render(write_still=True)
        encode_video(temp, args["orbit_fps"], out / "studio-orbit.mp4")
    bpy.data.objects.remove(orbit, do_unlink=True)
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = args["size"]
    scene.cycles.samples = args["samples"]


def main(run_path):
    args = json.loads(run_path.read_text())["settings"]
    config = args["config"]
    out = run_path.parent
    source = Path(args["source"])
    kind = source.suffix.lower()
    snapshot = {}
    usd_rate = None
    scene = bpy.context.scene
    if kind != ".blend":
        for obj in list(scene.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        if kind == ".xml":
            snapshot = json.loads((out / "export.json").read_text())
            source = out / "usd/frames/frame_1.usdc"
        elif args["animate"]:
            from pxr import Usd

            stage = Usd.Stage.Open(str(source))
            usd_rate = stage.GetTimeCodesPerSecond()
            if not math.isfinite(usd_rate) or not 0 < usd_rate <= 32767:
                raise ValueError(f"Unsupported USD timeCodesPerSecond: {usd_rate}")
            # Blender imports time samples as frame numbers, leaving scene FPS unchanged.
            scene.render.fps = max(1, round(usd_rate))
            scene.render.fps_base = scene.render.fps / usd_rate
        result = bpy.ops.wm.usd_import(filepath=str(source), import_cameras=kind != ".xml",
                                      import_lights=False, import_materials=True, read_mesh_uvs=True,
                                      import_all_materials=False, apply_unit_conversion_scale=True,
                                      set_frame_range=args["animate"] and kind != ".xml")
        if result != {"FINISHED"}:
            raise RuntimeError(f"USD import failed: {result}")
        scene.unit_settings.system = "METRIC"
    initial_frame = scene.frame_start if args["animate"] and kind != ".xml" else scene.frame_current
    if kind == ".xml":
        initial_frame = 1
    set_frame(scene, args["frame"] if args["frame"] is not None else initial_frame)
    bpy.context.view_layer.update()
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Scene has no mesh objects")
    metrics = check_geometry(meshes, snapshot.get("geometry"))
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = [obj.matrix_world @ Vector(point) for mesh in meshes if not mesh.hide_render
              for obj in [mesh.evaluated_get(depsgraph)] for point in obj.bound_box]
    if not points:
        raise ValueError("Scene has no renderable mesh bounds")
    low = Vector(min(point[i] for point in points) for i in range(3))
    high = Vector(max(point[i] for point in points) for i in range(3))
    focus = Vector(snapshot.get("focus") or config.get("focus") or (low + high) / 2)
    radius = float(config.get("light_radius", (high - low).length / 2))
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Scene needs a positive light radius")
    rig = Matrix(snapshot["rig_rotation"]) if "rig_rotation" in snapshot else Matrix.Identity(3)
    camera = camera_for(scene, config, snapshot, focus, radius)
    bpy.context.view_layer.update()

    for obj in scene.objects:
        if obj.type == "LIGHT":
            obj.hide_render = True
    scene.render.engine = "CYCLES"
    scene.render.use_freestyle = False
    scene.render.use_motion_blur = False
    scene.cycles.samples = args["samples"]
    scene.cycles.use_denoising = True
    scene.render.resolution_x, scene.render.resolution_y = args["size"]
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    scene.render.use_border = False
    scene.render.use_compositing = scene.render.use_sequencer = False
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"

    scene.world = bpy.data.worlds.new("Render Ambient")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    frames, fps = (animation_plan(scene, meshes, camera, args, out, kind, usd_rate)
                   if args["animate"] else ([scene.frame_current + scene.frame_subframe], None))
    selection = {}
    for style in ("xray", "silhouette"):
        key = f"{style}_objects"
        if style in args["styles"] and (style == "xray" or key in config):
            selection[style] = select_objects(meshes, snapshot.get("geometry", {}), config, key)
    if args["passes"]:
        meters_per_unit = float(config.get("meters_per_unit", scene.unit_settings.scale_length))
        if not math.isfinite(meters_per_unit) or meters_per_unit <= 0:
            raise ValueError("meters_per_unit must be positive")
        render_passes(scene, meshes, snapshot.get("geometry", {}), frames, args["passes"],
                      out / "passes", lambda frame: set_frame(scene, frame), meters_per_unit)
    for style in args["styles"]:
        scene.render.engine = "CYCLES"
        scene.render.use_freestyle = False
        scene.render.resolution_percentage = 100
        scene.view_settings.view_transform = "AgX"
        color, strength, lamps = STYLES.get(style, STYLES["studio"])
        background.inputs["Color"].default_value = (*color, 1)
        background.inputs["Strength"].default_value = strength
        for layer in scene.view_layers:
            layer.material_override = None
        lights = []
        for name, offset, power, size, tint in lamps:
            data = bpy.data.lights.new(name, "AREA")
            data.energy, data.size, data.color = power * radius ** 2, size * radius, tint
            light = bpy.data.objects.new(name, data)
            scene.collection.objects.link(light)
            light.location = focus + radius * (rig @ Vector(offset))
            aim(light, focus)
            lights.append(light)
        with ExitStack() as cleanup:
            set_frame(scene, frames[0])
            apply_style(scene, style, meshes, selection.get(style), cleanup)
            if args["animate"]:
                render_motion(scene, frames, fps, style, out)
            else:
                render_still(scene, style, out / f"{style}.png")
            if style == "studio" and args["orbit"]:
                render_orbit(scene, camera, focus, rig.col[2], args, out)
            if style == args["styles"][-1]:
                set_frame(scene, frames[0])
                bpy.context.preferences.filepaths.save_version = 0
                scene.render.filepath = f"//{style}.png"
                bpy.ops.file.pack_all()
                bpy.ops.wm.save_as_mainfile(filepath=str(out / "render.blend"), relative_remap=True)
        for light in lights:
            bpy.data.objects.remove(light, do_unlink=True)
    audit = dict(blender=bpy.app.version_string, frame=scene.frame_current, mesh_count=len(meshes),
                 camera=camera.name, camera_matrix=[list(row) for row in camera.matrix_world],
                 bounds=[list(low), list(high)], geometry=metrics, focus=list(focus),
                 light_radius=radius, orbit_axis=list(rig.col[2]), saved_style=args["styles"][-1],
                 rendered_frames=len(frames), fps=fps,
                 selected_objects={style: sorted(obj.name for obj in objects)
                                   for style, objects in selection.items()})
    (out / "blender.json").write_text(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--") + 1]))
