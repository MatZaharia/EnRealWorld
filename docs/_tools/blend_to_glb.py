"""Export a .blend scene to GLB with the bpy module, keeping the render camera.

The active camera is written to a JSON side file in three.js (Y-up) coordinates,
so the website can snap the interactive view to the painting's viewpoint.

Usage:
    python blend_to_glb.py scene.blend out.glb out.json [--max-texture 1024]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


def camera_info(scene: bpy.types.Scene) -> dict | None:
    cam = scene.camera
    if cam is None or cam.type != "CAMERA":
        return None
    y_up = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    m = y_up @ cam.matrix_world
    r = scene.render
    w = r.resolution_x * r.pixel_aspect_x
    h = r.resolution_y * r.pixel_aspect_y
    aspect = w / h
    data = cam.data
    if data.type == "ORTHO":
        fov_v = None
    else:
        fit = data.sensor_fit
        if fit == "AUTO":
            fit = "HORIZONTAL" if aspect >= 1 else "VERTICAL"
        if fit == "HORIZONTAL":
            fov_h = 2 * math.atan(data.sensor_width / (2 * data.lens))
            fov_v = 2 * math.atan(math.tan(fov_h / 2) / aspect)
        else:
            fov_v = 2 * math.atan(data.sensor_height / (2 * data.lens))
    pos = m.to_translation()
    fwd = m.to_3x3() @ Matrix.Identity(3).col[2] * -1
    up = m.to_3x3() @ Matrix.Identity(3).col[1]
    return {
        "position": [round(v, 4) for v in pos],
        "forward": [round(v, 5) for v in fwd],
        "up": [round(v, 5) for v in up],
        "fov_deg": round(math.degrees(fov_v), 3) if fov_v else None,
        "aspect": round(aspect, 5),
        "type": data.type,
        "ortho_scale": round(data.ortho_scale, 4) if data.type == "ORTHO" else None,
    }


def shrink_images(limit: int) -> None:
    for img in bpy.data.images:
        if img.size[0] == 0 or img.source not in {"FILE", "GENERATED"}:
            continue
        w, h = img.size
        s = limit / max(w, h)
        if s < 1:
            try:
                img.scale(max(1, int(w * s)), max(1, int(h * s)))
            except RuntimeError:
                pass


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("blend", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("meta", type=Path)
    ap.add_argument("--max-texture", type=int, default=1024)
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    scene = bpy.context.scene
    shrink_images(args.max_texture)

    meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get()]
    tris = 0
    deps = bpy.context.evaluated_depsgraph_get()
    for o in meshes:
        ev = o.evaluated_get(deps)
        try:
            me = ev.to_mesh()
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
            ev.to_mesh_clear()
        except RuntimeError:
            pass

    args.out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(args.out),
        export_format="GLB",
        use_visible=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
        export_image_format="JPEG",
        export_jpeg_quality=82,
        export_animations=False,
    )
    meta = {
        "source": args.blend.name,
        "blender": bpy.app.version_string,
        "objects": len(scene.objects),
        "mesh_objects": len(meshes),
        "triangles": tris,
        "materials": len([m for m in bpy.data.materials if m.users]),
        "camera": camera_info(scene),
        "render": [scene.render.resolution_x, scene.render.resolution_y],
    }
    args.meta.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
