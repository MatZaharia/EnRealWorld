"""Convert a MuJoCo MJCF scene into a compact GLB for the project website.

The scene is compiled with MuJoCo, posed at its initial configuration, and every
visible geom is baked into world space. Geoms that share a colour are merged so
the browser draws a few dozen meshes instead of thousands.

Usage:
    python mjcf_to_glb.py scene.xml out.glb [--stats out.json]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import mujoco
import numpy as np
import trimesh

Z_UP_TO_Y_UP = np.array(
    [[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float
)


def primitive(model: mujoco.MjModel, gid: int) -> trimesh.Trimesh | None:
    gtype = model.geom_type[gid]
    size = model.geom_size[gid]
    T = mujoco.mjtGeom
    if gtype == T.mjGEOM_BOX:
        return trimesh.creation.box(extents=2 * size)
    if gtype == T.mjGEOM_SPHERE:
        return trimesh.creation.icosphere(subdivisions=2, radius=size[0])
    if gtype == T.mjGEOM_CAPSULE:
        return trimesh.creation.capsule(height=2 * size[1], radius=size[0], count=[12, 12])
    if gtype == T.mjGEOM_CYLINDER:
        return trimesh.creation.cylinder(radius=size[0], height=2 * size[1], sections=20)
    if gtype == T.mjGEOM_ELLIPSOID:
        m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        m.apply_scale(size)
        return m
    if gtype == T.mjGEOM_PLANE:
        sx = size[0] if size[0] > 0 else 30.0
        sy = size[1] if size[1] > 0 else 30.0
        return trimesh.creation.box(extents=[2 * sx, 2 * sy, 0.002])
    if gtype == T.mjGEOM_MESH:
        mid = model.geom_dataid[gid]
        va, vn = model.mesh_vertadr[mid], model.mesh_vertnum[mid]
        fa, fn = model.mesh_faceadr[mid], model.mesh_facenum[mid]
        verts = np.array(model.mesh_vert[va : va + vn], dtype=float)
        faces = np.array(model.mesh_face[fa : fa + fn], dtype=np.int64)
        return trimesh.Trimesh(verts, faces, process=False)
    return None


def colour(model: mujoco.MjModel, gid: int) -> tuple[float, float, float, float]:
    mat = model.geom_matid[gid]
    rgba = model.mat_rgba[mat] if mat >= 0 else model.geom_rgba[gid]
    return tuple(round(float(c), 3) for c in rgba)


def convert(xml: Path, out: Path, max_group: int = 2) -> dict:
    model = mujoco.MjModel.from_xml_path(str(xml))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    buckets: dict[tuple, list[trimesh.Trimesh]] = defaultdict(list)
    used = skipped = 0
    for gid in range(model.ngeom):
        rgba = colour(model, gid)
        if model.geom_type[gid] == mujoco.mjtGeom.mjGEOM_PLANE:
            skipped += 1  # the viewer draws its own ground
            continue
        if rgba[3] <= 0.01 or model.geom_group[gid] > max_group:
            skipped += 1
            continue
        mesh = primitive(model, gid)
        if mesh is None or len(mesh.faces) == 0:
            skipped += 1
            continue
        T = np.eye(4)
        T[:3, :3] = data.geom_xmat[gid].reshape(3, 3)
        T[:3, 3] = data.geom_xpos[gid]
        mesh.apply_transform(Z_UP_TO_Y_UP @ T)
        buckets[rgba].append(mesh)
        used += 1

    scene = trimesh.Scene()
    tris = 0
    for i, (rgba, parts) in enumerate(sorted(buckets.items())):
        merged = trimesh.util.concatenate(parts)
        merged.merge_vertices()
        tris += len(merged.faces)
        material = trimesh.visual.material.PBRMaterial(
            baseColorFactor=[int(255 * c) for c in rgba],
            metallicFactor=0.0,
            roughnessFactor=0.82,
            alphaMode="BLEND" if rgba[3] < 0.99 else "OPAQUE",
            doubleSided=True,
        )
        merged.visual = trimesh.visual.TextureVisuals(material=material)
        scene.add_geometry(merged, node_name=f"mat_{i:03d}", geom_name=f"mat_{i:03d}")

    out.parent.mkdir(parents=True, exist_ok=True)
    scene.export(out)
    lo, hi = scene.bounds
    stats = {
        "source": xml.name,
        "bodies": int(model.nbody),
        "geoms": int(model.ngeom),
        "visible_geoms": used,
        "joints": int(model.njnt),
        "actuators": int(model.nu),
        "meshes": int(model.nmesh),
        "materials": len(buckets),
        "triangles": int(tris),
        "extent_m": [round(float(v), 2) for v in (hi - lo)],
        "bounds": [[round(float(v), 3) for v in lo], [round(float(v), 3) for v in hi]],
    }
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("xml", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--stats", type=Path)
    args = ap.parse_args()
    stats = convert(args.xml, args.out)
    print(json.dumps(stats))
    if args.stats:
        args.stats.write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
