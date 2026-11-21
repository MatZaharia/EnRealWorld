"""Names and object selection shared by the CLI and Blender."""

from fnmatch import fnmatchcase

STYLE_NAMES = (
    "studio", "clay", "dramatic", "lineart", "toon", "technical", "colored-clay",
    "flat", "blueprint", "wireframe", "xray", "metal", "silhouette", "pixel",
)


def object_patterns(config, key):
    patterns = config.get(key)
    if not isinstance(patterns, list) or not patterns or any(
        not isinstance(pattern, str) or not pattern.strip() for pattern in patterns
    ):
        raise ValueError(f"Set {key} to a non-empty JSON list of object names or glob patterns")
    return patterns


def select_objects(objects, geometry, config, key):
    selected = set()
    for pattern in object_patterns(config, key):
        matches = set()
        for obj in objects:
            source = geometry.get(obj.name.removeprefix("Mesh_"), {}).get("mujoco_geom_name")
            if not obj.hide_render and (fnmatchcase(obj.name, pattern)
                                       or (source and fnmatchcase(source, pattern))):
                matches.add(obj)
        if not matches:
            raise ValueError(f"{key}: {pattern!r} matches no renderable mesh")
        selected.update(matches)
    return selected
