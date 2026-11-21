"""Replay the studio bowl release in a fresh Blender process."""

import argparse
import json
import sys

import bpy


def world_vertices(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [evaluated.matrix_world @ vertex.co for vertex in evaluated.data.vertices]


def replay(placement):
    scene = bpy.context.scene
    scene.frame_set(1)
    bowl = bpy.data.objects["Bowl | wheel-thrown stoneware with hollow interior and foot"]
    table_vertices = world_vertices(bpy.data.objects["Console | solid oak top"])
    support_height = max(vertex.z for vertex in table_vertices)
    if placement == "floor":
        bowl_vertices = world_vertices(bowl)
        bowl_center_y = sum(vertex.y for vertex in bowl_vertices) / len(bowl_vertices)
        bowl.location.y += min(vertex.y for vertex in table_vertices) - 0.23 - bowl_center_y
        support_height = max(vertex.z for vertex in world_vertices(bpy.data.objects["Floor contact slab"]))

    bowl.location.z += 0.18
    bowl.rigid_body.use_deactivation = False
    bowl.rigid_body.use_start_deactivated = False
    bpy.context.view_layer.update()

    heights = {}
    for frame in range(1, 81):
        scene.frame_set(frame)
        if frame in (1, 10, 40, 80):
            heights[frame] = min(vertex.z for vertex in world_vertices(bowl))

    print(json.dumps({
        "placement": placement,
        "blender_version": bpy.app.version_string,
        "support_height_m": support_height,
        "bowl_bottom_m": heights,
    }, indent=2))
    if abs(heights[80] - support_height) > 0.01 or abs(heights[80] - heights[40]) > 0.005:
        raise RuntimeError(f"The bowl did not settle on the {placement}.")
    if heights[1] - support_height < 0.15:
        raise RuntimeError(f"The bowl did not start above the {placement}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("placement", choices=("table", "floor"))
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    replay(args.placement)
