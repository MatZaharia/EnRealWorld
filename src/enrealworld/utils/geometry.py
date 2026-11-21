"""Finite geometry tools. Optional CPU dependencies; no in-place repair.

This module is a conversion/discretization layer, not another asset property tree.
All distances are SI, right-handed Z-up; resource coordinates are asset-local.
"""

from pathlib import Path
from typing import Literal
import hashlib
import importlib.metadata
import json
import time

from pydantic import Field
from enrealworld.validation_model import Model
from enrealworld.utils.files import digest


class CollisionConversion(Model):
    method: Literal["direct", "coacd", "vhacd", "convex_hull_negative"] = "direct"
    seed: int = Field(default=7, ge=0)
    parameters: dict[str, int | float | bool | str] = Field(default_factory=dict)


class GeometryConversionConfig(Model):
    """Tool configuration only. Authoritative mass/inertia remain in the asset."""

    schema_version: Literal["1"] = "1"
    units: Literal["m"] = "m"
    coordinate_system: Literal["right_handed_Z_up"] = "right_handed_Z_up"
    collisions: dict[str, CollisionConversion] = Field(default_factory=dict)


def versions():
    return {k: importlib.metadata.version(k) for k in ("trimesh", "numpy", "scipy")}


def arrays(path):
    """Restricted, index-preserving OBJ input; algorithms come from Trimesh.

    Reject non-triangle faces rather than silently triangulate or renumber pins.
    No normals, unit inference, welding, fill, winding repair or Scene flattening.
    """
    import numpy as np

    v, f, e = [], [], []
    for row in Path(path).read_text().splitlines():
        t = row.split("#", 1)[0].split()
        if not t:
            continue
        if t[0] == "v":
            if len(t) != 4:
                raise ValueError("only xyz vertices are supported")
            v.append([float(x) for x in t[1:]])
        elif t[0] in ("f", "l"):
            ids = [int(x.split("/")[0]) for x in t[1:]]
            if any(i == 0 for i in ids):
                raise ValueError("OBJ index zero is invalid")
            ids = [i - 1 if i > 0 else len(v) + i for i in ids]
            if t[0] == "f":
                if len(ids) != 3:
                    raise ValueError("triangle OBJ required; no implicit triangulation")
                f.append(ids)
            else:
                if len(ids) < 2:
                    raise ValueError("line needs two vertices")
                e.extend(zip(ids[:-1], ids[1:]))
        elif t[0] not in ("vt", "vn", "s", "o", "g", "usemtl", "mtllib"):
            raise ValueError("unsupported OBJ element: " + t[0])
    v = np.array(v, dtype=float).reshape(-1, 3)
    f = np.array(f, dtype=int).reshape(-1, 3)
    e = np.array(e, dtype=int).reshape(-1, 2)
    if len(v) == 0 or not np.isfinite(v).all():
        raise ValueError("empty or nonfinite vertices")
    for group in (f, e):
        if group.size and (group.min() < 0 or group.max() >= len(v)):
            raise ValueError("index outside resource")
    return v, f, e


def inspect_obj(path, *, purpose, expected_sha256=None, unit="m", transform=None):
    """Read-only purpose-aware checks. Unchecked properties are never pass."""
    import numpy as np
    import trimesh

    started = time.perf_counter()
    path = Path(path)
    report = dict(
        resource=str(path),
        resource_sha256=None,
        purpose=purpose,
        units=unit,
        coordinate_system="right_handed_Z_up",
        checks={},
        metrics={},
        not_checked=["self_intersection", "nested_shell_interpretation", "OBJ_appearance_attributes"],
    )
    try:
        if purpose not in (
            "visual",
            "reference",
            "cloth",
            "rope",
            "solid_mass",
            "convex_collision",
        ):
            raise ValueError("unknown geometry purpose")
        if unit != "m":
            raise ValueError("explicit SI input required; no unit guessing")
        report["resource_sha256"] = digest(path)
        if expected_sha256 and expected_sha256 != report["resource_sha256"]:
            raise ValueError("resource identity mismatch")
        v, f, e = arrays(path)
        if transform is not None:
            T = np.array(transform, dtype=float)
            if (
                T.shape != (4, 4)
                or not np.isfinite(T).all()
                or not np.allclose(T[3], [0, 0, 0, 1])
            ):
                raise ValueError("invalid homogeneous transform")
            if not np.allclose(
                T[:3, :3].T @ T[:3, :3], np.eye(3), atol=1e-8
            ) or not np.isclose(np.linalg.det(T[:3, :3]), 1):
                raise ValueError(
                    "only rigid proper transforms; declare unit/scale changes separately"
                )
            v = trimesh.transform_points(v, T)
        report["transform"] = np.eye(4).tolist() if transform is None else T.tolist()
        report["metrics"].update(
            vertices=len(v),
            triangles=len(f),
            line_segments=len(e),
            bounds_m=[v.min(axis=0).tolist(), v.max(axis=0).tolist()],
            extents_m=np.ptp(v, axis=0).tolist(),
        )
        checks = report["checks"]
        checks.update(finite_and_indices=True, resource_identity=True)
        edges = (
            e
            if len(e)
            else (
                np.vstack((f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]))
                if len(f)
                else np.empty((0, 2), int)
            )
        )
        if not len(edges):
            raise ValueError("geometry has no edges or faces")
        lengths = np.linalg.norm(v[edges[:, 0]] - v[edges[:, 1]], axis=1)
        scale = float(np.ptp(v, axis=0).max())
        epsilon = max(scale * 1e-12, 1e-14)
        checks["no_zero_length_edges"] = bool(np.all(lengths > epsilon))
        report["metrics"].update(
            minimum_edge_m=float(lengths.min()), maximum_edge_m=float(lengths.max())
        )
        report["metrics"]["connected_components"] = len(
            trimesh.graph.connected_components(edges, nodes=np.arange(len(v)))
        )
        if len(f):
            m = trimesh.Trimesh(v, f, process=False, validate=False)
            areas = m.area_faces
            checks["nondegenerate_triangles"] = bool(np.all(areas > epsilon**2))
            unique, counts = np.unique(
                np.sort(edges, axis=1), axis=0, return_counts=True
            )
            checks["no_nonmanifold_edges"] = bool(np.all(counts <= 2))
            checks["consistent_winding"] = bool(m.is_winding_consistent)
            report["not_checked"].append("vertex_link_manifoldness")
            edge2 = np.sum((v[f[:, [1, 2, 0]]] - v[f]) ** 2, axis=2).sum(axis=1)
            q = np.divide(
                4 * np.sqrt(3) * areas, edge2, out=np.zeros_like(areas), where=edge2 > 0
            )
            report["metrics"].update(
                area_m2=float(m.area),
                minimum_area_m2=float(areas.min()),
                minimum_triangle_quality=float(q.min()),
                watertight=bool(m.is_watertight),
                signed_volume_m3=float(m.volume) if m.is_watertight else None,
                convex=bool(m.is_convex)
                if m.is_watertight and m.volume > epsilon**3
                else None,
            )
            if purpose in ("solid_mass", "convex_collision"):
                checks["watertight"] = bool(m.is_watertight)
                checks["positive_oriented_volume"] = bool(
                    m.is_watertight and m.volume > epsilon**3
                )
                checks["one_component"] = report["metrics"]["connected_components"] == 1
            if purpose == "convex_collision":
                checks["convex"] = bool(m.is_convex)
        elif purpose not in ("rope", "visual", "reference"):
            raise ValueError("triangles required for this purpose")
        if purpose == "rope":
            checks["line_geometry_only"] = bool(len(e) and not len(f))
            degree = np.bincount(e.flatten(), minlength=len(v))
            checks["single_open_polyline"] = bool(
                report["metrics"]["connected_components"] == 1
                and np.sum(degree == 1) == 2
                and np.all((degree == 1) | (degree == 2))
            )
            report["metrics"]["polyline_length_m"] = float(lengths.sum())
        elif len(e) and len(f):
            checks["no_uninterpreted_lines"] = False
        elif len(e):
            report["not_applicable"] = [
                "surface_normals",
                "triangle_area",
                "watertight_volume",
            ]
        report["passed"] = bool(checks) and all(checks.values())
    except (OSError, ValueError, IndexError) as exc:
        report.update(passed=False, error=str(exc))
    report["elapsed_s"] = time.perf_counter() - started
    return report


def require_geometry(report):
    if report.get("passed") is not True:
        raise ValueError("geometry rejected: " + json.dumps(report))


def solid_mass(path, density, *, assume_no_self_intersection=False):
    """Single oriented closed solid only. Explicit assumption, not verification."""
    import trimesh
    import math

    if not math.isfinite(density) or density <= 0 or not assume_no_self_intersection:
        raise ValueError(
            "positive density and explicit no-self-intersection assumption required"
        )
    audit = inspect_obj(path, purpose="solid_mass")
    require_geometry(audit)
    v, f, _ = arrays(path)
    m = trimesh.Trimesh(v, f, process=False)
    m.density = density
    return {
        "mass_kg": float(m.mass),
        "center_of_mass_m": m.center_mass.tolist(),
        "tensor_kg_m2": m.moment_inertia.tolist(),
        "density_kg_m3": density,
        "source": {"resource_sha256": digest(path), "purpose": "reference_solid"},
        "assumptions": [
            "uniform volume density",
            "single closed oriented solid",
            "no self-intersections (caller assumption, NOT independently checked)",
        ],
        "algorithm": "Trimesh polyhedral volume integration; floating-point, not exact arithmetic",
    }


def write_obj(path, vertices, faces=(), edges=()):
    """New resource only, or byte-identical reuse. Never overwrite another mesh."""
    rows = ["# EnRealWorld derived resource; SI, right-handed Z-up"]
    rows += ["v " + " ".join(f"{x:.17g}" for x in row) for row in vertices]
    rows += ["f " + " ".join(str(int(x) + 1) for x in row) for row in faces]
    rows += ["l " + " ".join(str(int(x) + 1) for x in row) for row in edges]
    raw = ("\n".join(rows) + "\n").encode()
    path = Path(path)
    if path.exists() and path.read_bytes() != raw:
        raise ValueError("refuse to overwrite different resource")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest(path)


def regular_cloth(width_m, height_m, nx, ny, path):
    import numpy as np

    if (
        not np.isfinite([width_m, height_m]).all()
        or min(width_m, height_m) <= 0
        or min(nx, ny) < 1
        or not all(isinstance(n, int) for n in (nx, ny))
    ):
        raise ValueError("positive dimensions/integer subdivisions required")
    v = [
        [x, y, 0.0]
        for y in np.linspace(0, -height_m, ny + 1)
        for x in np.linspace(-width_m / 2, width_m / 2, nx + 1)
    ]
    f = []
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            b = a + 1
            c = a + nx + 1
            d = c + 1
            f.extend([[a, c, b], [b, c, d]])
    sha = write_obj(path, v, f)
    return dict(
        algorithm="regular_rectangle_v1",
        parameters=dict(width_m=width_m, height_m=height_m, nx=nx, ny=ny),
        resource_sha256=sha,
        boundary_selections={"top_left": [0], "top_right": [nx]},
        selection_semantics="rebuilt from this generator topology; no transfer of old indices",
    )


def regular_rope(length_m, segments, path):
    import numpy as np

    if (
        not np.isfinite(length_m)
        or length_m <= 0
        or not isinstance(segments, int)
        or segments < 1
    ):
        raise ValueError("positive length/integer segment count required")
    v = [[float(x), 0.0, 0.0] for x in np.linspace(0, length_m, segments + 1)]
    e = [[i, i + 1] for i in range(segments)]
    sha = write_obj(path, v, edges=e)
    return dict(
        algorithm="regular_polyline_v1",
        parameters=dict(length_m=length_m, segments=segments),
        resource_sha256=sha,
        boundary_selections={"start": [0]},
        selection_semantics="rebuilt from this generator topology; no arbitrary remeshing map",
    )


COACD_PARAMETERS = dict(
    threshold=0.008,
    real_metric=True,
    preprocess_mode="off",
    preprocess_resolution=50,
    resolution=2000,
    mcts_nodes=10,
    mcts_iterations=40,
    mcts_max_depth=3,
    pca=False,
    merge=True,
    decimate=False,
    max_ch_vertex=256,
    extrude=False,
    extrude_margin=0.01,
    apx_mode="ch",
    max_convex_hull=64,
)
VHACD_PARAMETERS = dict(
    maxConvexHulls=32,
    resolution=100000,
    minimumVolumePercentErrorAllowed=1.0,
    maxRecursionDepth=10,
    shrinkWrap=True,
    fillMode="flood",
    maxNumVerticesPerCH=64,
    asyncACD=False,
    minEdgeLength=2,
    findBestPlane=False,
)


def collision_parts(path, policy, cache):
    """Generic convex path; never substitutes known components after a failure."""
    import numpy as np
    import trimesh

    policy = CollisionConversion.model_validate(policy)
    audit = inspect_obj(path, purpose="solid_mass")
    require_geometry(audit)
    v, f, _ = arrays(path)
    mesh = trimesh.Trimesh(v, f, process=False)
    method = policy.method
    if method == "direct" and not mesh.is_convex:
        raise ValueError(
            "concave input cannot be directly imported as a convex collider"
        )
    package = {"coacd": "coacd", "vhacd": "vhacdx"}.get(method, "trimesh")
    tool_version = importlib.metadata.version(package)
    parameters = dict(
        COACD_PARAMETERS
        if method == "coacd"
        else VHACD_PARAMETERS
        if method == "vhacd"
        else {}
    )
    if set(policy.parameters) - set(parameters):
        raise ValueError("unreviewed decomposition option")
    parameters.update(policy.parameters)
    if method == "coacd" and (
        parameters["preprocess_mode"] != "off"
        or parameters["extrude"]
        or parameters["decimate"]
    ):
        raise ValueError("repair/extrusion/decimation is outside the reviewed path")
    spec = dict(
        input_sha256=digest(path),
        method=method,
        package=package,
        version=tool_version,
        parameters=parameters,
        seed=policy.seed if method == "coacd" else None,
        dependencies=versions(),
        units="m",
        coordinates="asset_local_right_handed_Z_up",
        implementation="geometry_conversion_v1",
        implementation_sha256=digest(__file__),
    )
    key = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    folder = Path(cache) / key
    record_path = folder / "conversion.json"
    if record_path.exists():
        record = json.loads(record_path.read_text())
        if record["specification"] != spec:
            raise ValueError("cache key mismatch")
        for p in record["parts"]:
            if digest(folder / p["file"]) != p["sha256"]:
                raise ValueError("corrupt collision cache")
        return dict(record, cache_hit=True, cache_directory=str(folder))
    if folder.exists():
        raise ValueError(
            "incomplete/failed cache retained; use a new cache root rather than overwrite evidence"
        )
    folder.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    if method == "coacd":
        import coacd

        coacd.set_log_level("warn")
        result = coacd.run_coacd(coacd.Mesh(v, f), seed=policy.seed, **parameters)
    elif method == "vhacd":
        import vhacdx

        result = vhacdx.compute_vhacd(
            v.astype(np.float64), f.astype(np.uint32).flatten(), **parameters
        )
    elif method == "convex_hull_negative":
        h = mesh.convex_hull
        result = [(h.vertices, h.faces)]
    else:
        result = [(v, f)]
    elapsed = time.perf_counter() - start
    if not result:
        raise ValueError("empty decomposition")
    parts = []
    for i, (pv, pf) in enumerate(result):
        filename = f"part_{i:03d}.obj"
        sha = write_obj(folder / filename, pv, pf)
        check = inspect_obj(
            folder / filename, purpose="convex_collision", expected_sha256=sha
        )
        require_geometry(check)
        parts.append(
            dict(
                file=filename,
                sha256=sha,
                vertices=len(pv),
                triangles=len(pf),
                inspection=check,
            )
        )
    record = dict(
        specification=spec,
        input_inspection=audit,
        parts=parts,
        algorithm_elapsed_s=elapsed,
        approximation=method not in ("direct",),
        seed_semantics="explicit CoACD seed; V-HACD exposes no seed and runs asyncACD=False",
        changes="derived convex collision parts only; original resource and asset mass/inertia untouched",
        not_checked=[
            "self_intersection",
            "nested_shell_interpretation",
            "arbitrary direction passage",
            "continuous surface distance",
        ],
        cache_key=key,
    )
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    return dict(record, cache_hit=False, cache_directory=str(folder))


def free_space_samples(parts, points):
    """Read-only functional admission shared by adapters and finite examples.

    Explicit asset-local centerline points only. No swept-volume, finite probe
    radius, arbitrary-direction clearance, or dynamic success is inferred.
    """
    import numpy as np
    from scipy.spatial import ConvexHull
    p = np.asarray(points, float)
    if not parts or p.ndim != 2 or p.shape[1:] != (3,) or not len(p) or not np.isfinite(p).all():
        raise ValueError("functional admission needs nonempty parts and finite xyz samples")
    inside = np.zeros(len(p), bool)
    for vertices in parts:
        eq = ConvexHull(np.asarray(vertices, float)).equations
        inside |= np.max(p @ eq[:, :3].T + eq[:, 3], axis=1) < -1e-7
    return dict(sample_count=len(p), points_asset_local_m=p.tolist(),
                intruding_sample_count=int(inside.sum()), passed=not bool(inside.any()),
                scope="declared point samples only; no finite-radius/swept-volume or dynamic guarantee")
