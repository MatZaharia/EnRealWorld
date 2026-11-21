"""Write raw Cycles passes and independent display previews."""

import json
from pathlib import Path
import tempfile

import bpy
import numpy as np


def exr_pixels(path, width, height):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        return pixels.reshape(height, width, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(image)


def preview(path, rgb):
    height, width, _ = rgb.shape
    image = bpy.data.images.new(path.stem, width, height)
    try:
        image.colorspace_settings.name = "Non-Color"
        rgba = np.ones((height, width, 4), dtype=np.float32)
        rgba[:, :, :3] = rgb[::-1]
        image.pixels.foreach_set(rgba.ravel())
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)


def render_passes(scene, meshes, geometry, frames, requested, out, set_frame, meters_per_unit):
    out.mkdir()
    if len(scene.view_layers) != 1:
        raise ValueError("Pass export requires exactly one view layer")
    if any(obj.type not in {"MESH", "EMPTY", "LIGHT", "CAMERA"} and not obj.hide_render
           for obj in scene.objects):
        raise ValueError("Pass export requires mesh geometry")
    if len(meshes) > 32767 or any(obj.instance_type != "NONE" for obj in scene.objects):
        raise ValueError("Pass export requires individual mesh objects (maximum 32767)")
    layer = scene.view_layers[0]
    layer.material_override = None
    old_passes = (layer.use_pass_object_index, layer.use_pass_position, layer.use_pass_normal)
    old_threshold = layer.pass_alpha_threshold
    layer.use_pass_object_index = True
    layer.use_pass_position = "depth" in requested
    layer.use_pass_normal = "normal" in requested
    layer.pass_alpha_threshold = 0.5
    instances = {}
    for index, obj in enumerate(sorted(meshes, key=lambda o: o.name), 1):
        obj.pass_index = index
        source = geometry.get(obj.name.removeprefix("Mesh_"), {})
        instances[index] = dict(object=obj.name, mujoco_geom_id=source.get("mujoco_geom_id"),
                                mujoco_geom_name=source.get("mujoco_geom_name"))
    (out / "instances.json").write_text(json.dumps(instances, indent=2))
    (out / "format.json").write_text(json.dumps({
        "array_origin": "top left; indices [row, col]",
        "depth": "float32, meters along camera forward axis; background NaN",
        "normal": "float32 XYZ, Blender world axes, Cycles shading normals; background [0,0,0]",
        "segmentation": "uint16 object ID, 0 is background; see instances.json",
        "alpha_threshold": 0.5,
        "meters_per_blender_unit": meters_per_unit,
        "previews": "PNG; depth uses the first frame's 2–98% display range",
    }, indent=2))
    width, height = scene.render.resolution_x, scene.render.resolution_y
    old_samples = scene.cycles.samples
    old_denoise = scene.cycles.use_denoising
    old_use_nodes = scene.use_nodes
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.use_compositing = scene.use_nodes = True
    tree = scene.node_tree
    # Data exports use only this compositor graph. Remove authored output nodes
    # from the in-memory copy so they cannot write outside the run directory.
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    output = tree.nodes.new("CompositorNodeOutputFile")
    output.format.file_format = "OPEN_EXR"
    output.format.color_depth = "32"
    output.format.color_mode = "RGB"
    output.file_slots.remove(output.inputs[0])
    sockets = {"index": "IndexOB"}
    if "depth" in requested:
        sockets["position"] = "Position"
    if "normal" in requested:
        sockets["normal"] = "Normal"
    for key, name in sockets.items():
        socket = output.file_slots.new(key)
        tree.links.new(layers.outputs[name], socket)
    colors = np.random.default_rng(0).uniform(0.2, 1, (len(meshes) + 1, 3))
    colors[0] = 0
    depth_range = None
    with tempfile.TemporaryDirectory(dir=out) as temp:
        output.base_path = temp
        for i, frame in enumerate(frames, 1):
            set_frame(frame)
            bpy.ops.render.render()
            raw = {key: exr_pixels(next(Path(temp).glob(f"{key}*.exr")), width, height)
                   for key in sockets}
            for file in Path(temp).glob("*.exr"):
                file.unlink()
            index = raw["index"][:, :, 0]
            if not np.isfinite(index).all() or np.any(index != np.rint(index)) or np.any(
                    (index < 0) | (index > len(meshes))):
                raise RuntimeError("Invalid object index pass")
            ids = index.astype(np.uint16)
            valid = ids != 0
            arrays = {}
            if "segmentation" in requested:
                arrays["segmentation"] = ids
                preview(out / f"segmentation-{i:05d}.png", colors[ids])
            if "depth" in requested:
                camera = scene.camera.evaluated_get(bpy.context.evaluated_depsgraph_get())
                matrix = camera.matrix_world
                eye = np.array(matrix.translation)
                forward = -np.array(matrix.to_quaternion().to_matrix().col[2])
                depth = ((raw["position"][:, :, :3] - eye) @ forward * meters_per_unit).astype(np.float32)
                depth[~valid] = np.nan
                arrays["depth"] = depth
                if depth_range is None and np.any(valid):
                    depth_range = np.percentile(depth[valid], [2, 98]).tolist()
                lo, hi = depth_range or (0.0, 1.0)
                shade = np.zeros_like(depth)
                shade[valid] = np.clip(1 - (depth[valid] - lo) / max(hi - lo, 1e-6), 0.1, 1)
                preview(out / f"depth-{i:05d}.png", np.repeat(shade[:, :, None], 3, axis=2))
            if "normal" in requested:
                normal = raw["normal"][:, :, :3].copy()
                normal[~valid] = 0
                arrays["normal"] = normal
                preview(out / f"normal-{i:05d}.png", np.where(valid[:, :, None], normal * 0.5 + 0.5, 0))
            np.savez_compressed(out / f"{i:05d}.npz", **arrays)
    tree.nodes.remove(output)
    tree.nodes.remove(layers)
    layer.use_pass_object_index, layer.use_pass_position, layer.use_pass_normal = old_passes
    layer.pass_alpha_threshold = old_threshold
    scene.use_nodes = old_use_nodes
    scene.render.use_compositing = False
    scene.cycles.samples = old_samples
    scene.cycles.use_denoising = old_denoise
