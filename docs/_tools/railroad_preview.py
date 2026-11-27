"""Build the Claude Fable railroad diorama. Run in Blender with the source open.

blender -b Claude-Fable-5.2.blend -P railroad_preview.py -- preview.glb
"""
import sys

import bmesh
import bpy
from mathutils import Vector

scene = bpy.context.scene
bpy.ops.object.select_all(action="DESELECT")

# Keep the part of the kilometre-long railway that belongs in the house view.
for obj in list(scene.objects):
    if obj.name.startswith(("Terrain_FarPlain", "Loose_SpareTie_", "Site_FarTrees")):
        bpy.data.objects.remove(obj, do_unlink=True)
        continue
    if not obj.name.startswith(("Rail_", "Terrain_Ground")):
        continue
    mesh = bmesh.new()
    mesh.from_mesh(obj.data)
    mesh.transform(obj.matrix_world)
    for axis, lower, upper in [(0, -20, 20), (1, -23, 13)]:
        for limit, sign in [(lower, -1), (upper, 1)]:
            point = Vector((0, 0, 0))
            normal = point.copy()
            point[axis], normal[axis] = limit, sign
            bmesh.ops.bisect_plane(mesh, geom=list(mesh.verts) + list(mesh.edges) + list(mesh.faces),
                                   plane_co=point, plane_no=normal, clear_outer=True, dist=1e-5)
    mesh.transform(obj.matrix_world.inverted())
    mesh.to_mesh(obj.data)
    mesh.free()

# Bake Blender's procedural colours onto one shared UV atlas. Keep the
# original glass, roughness, and metal shaders on the exported geometry.
objects = [o for o in scene.objects if o.type == "MESH" and o.visible_get() and not o.hide_render]
architecture = [o for o in objects if o.name.startswith(("House_", "Porch_"))]
atlas = bpy.data.images.new("Railroad exterior", width=2048, height=2048, alpha=False)
for obj in architecture:
    obj.select_set(True)
    obj.data.uv_layers.new(name="ExteriorAtlas")
    obj.data.uv_layers.active = obj.data.uv_layers["ExteriorAtlas"]
bpy.context.view_layer.objects.active = architecture[0]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(island_margin=0.003)
bpy.ops.object.mode_set(mode="OBJECT")
shaders = []
for material in {m for o in architecture for m in o.data.materials if m}:
    if not material.use_nodes:
        continue
    tree = material.node_tree
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = atlas
    tree.nodes.active = node
    principled = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if principled and principled.inputs["Base Color"].is_linked:
        shaders.append((tree, node, principled))
scene.render.engine = "CYCLES"
scene.cycles.samples = 1
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=4, uv_layer="ExteriorAtlas")
for tree, node, shader in shaders:
    uv = tree.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "ExteriorAtlas"
    tree.links.new(uv.outputs["UV"], node.inputs["Vector"])
    tree.links.new(node.outputs["Color"], shader.inputs["Base Color"])

# Unsupported procedural shaders outside the atlas use the artist's swatch.
for material in bpy.data.materials:
    if not material.use_nodes:
        continue
    for node in material.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        color = node.inputs["Base Color"]
        if color.is_linked and color.links[0].from_node.type != "TEX_IMAGE":
            material.node_tree.links.remove(color.links[0])
            color.default_value = material.diffuse_color
# Blender's dedicated glass node has no direct base colour in the export.
glass = bpy.data.materials["window_glass"]
tree = glass.node_tree
output = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
window = tree.nodes.new("ShaderNodeBsdfPrincipled")
window.inputs["Base Color"].default_value = glass.diffuse_color
window.inputs["Roughness"].default_value = 0.22
tree.links.new(window.outputs["BSDF"], output.inputs["Surface"])
for obj in objects:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=sys.argv[-1], export_format="GLB", use_selection=True,
                          export_current_frame=True, export_apply=True, export_animations=False,
                          export_image_format="JPEG", export_jpeg_quality=88)
