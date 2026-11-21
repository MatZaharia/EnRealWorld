"""Beauty-only material, edge and pixel treatments."""

from functools import lru_cache
import math

import numpy as np

import bpy


def emission(name, color):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    shader = nodes.new("ShaderNodeEmission")
    shader.inputs["Color"].default_value = color
    material.node_tree.links.new(shader.outputs[0], nodes.get("Material Output").inputs["Surface"])
    return material


def cel_material():
    material = emission("Cel shading", (1, 1, 1, 1))
    nodes = material.node_tree.nodes
    link = material.node_tree.links.new
    diffuse = nodes.new("ShaderNodeBsdfDiffuse")
    lighting = nodes.new("ShaderNodeShaderToRGB")
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "CONSTANT"
    for element, position, value in zip(ramp.color_ramp.elements, (0.0, 0.36), (0.32, 0.68)):
        element.position = position
        element.color = (value, value, value, 1)
    ramp.color_ramp.elements.new(0.70).color = (1, 1, 1, 1)
    tint = nodes.new("ShaderNodeMixRGB")
    tint.blend_type = "MULTIPLY"
    tint.inputs[0].default_value = 1
    info = nodes.new("ShaderNodeObjectInfo")
    link(diffuse.outputs[0], lighting.inputs[0])
    link(lighting.outputs[0], ramp.inputs[0])
    link(info.outputs["Color"], tint.inputs[1])
    link(ramp.outputs[0], tint.inputs[2])
    link(tint.outputs[0], nodes.get("Emission").inputs[0])
    return material


def base_color(obj):
    material = obj.active_material
    color = material.diffuse_color if material else (0.54, 0.58, 0.64, 1)
    if material and material.use_nodes:
        shader = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if shader is not None:
            color = shader.inputs["Base Color"].default_value
    return tuple(color)


def set_contours(scene, color, thickness):
    scene.render.use_freestyle = True
    scene.render.line_thickness = 1.0
    authored = []
    created = []
    for layer in scene.view_layers:
        linesets = layer.freestyle_settings.linesets
        for existing in linesets:
            authored.append((existing, existing.show_render))
            existing.show_render = False
        lines = linesets.new("Render contours")
        lines.linestyle.color = color
        lines.linestyle.thickness = thickness
        lines.select_silhouette = lines.select_border = lines.select_crease = True
        lines.select_external_contour = True
        created.append((linesets, lines))

    def restore():
        for linesets, lines in created:
            linesets.remove(lines)
        for lines, enabled in authored:
            lines.show_render = enabled

    return restore


def replace_materials(materials):
    added = {obj.data: material for obj, material in materials.items() if not obj.material_slots}
    for mesh, material in added.items():
        mesh.materials.append(material)
    previous = []
    for obj, material in materials.items():
        for slot in obj.material_slots:
            previous.append((slot, slot.link, slot.material))
            slot.link = "OBJECT"
            slot.material = material

    def restore():
        for slot, link, material in previous:
            if link == "OBJECT":
                slot.material = material
            slot.link = link
        for mesh in added:
            mesh.materials.pop()

    return restore


@lru_cache(maxsize=None)
def surface(name, color, roughness, metallic=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    return material


def wire_material():
    material = surface("Mesh edges", (0.28, 0.43, 0.5), 0.56)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    wire = nodes.new("ShaderNodeWireframe")
    wire.use_pixel_size = True
    wire.inputs["Size"].default_value = 0.42
    strength = nodes.new("ShaderNodeMath")
    strength.operation = "MULTIPLY"
    strength.inputs[1].default_value = 0.64
    ink = nodes.new("ShaderNodeEmission")
    ink.inputs["Color"].default_value = (0.016, 0.07, 0.10, 1)
    mix = nodes.new("ShaderNodeMixShader")
    links.new(wire.outputs[0], strength.inputs[0])
    links.new(strength.outputs[0], mix.inputs[0])
    links.new(nodes.get("Principled BSDF").outputs[0], mix.inputs[1])
    links.new(ink.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])
    return material


def transparent_material():
    material = surface("X-ray shell", (0.19, 0.52, 0.7), 0.34)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.17
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(nodes.get("Principled BSDF").outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])
    return material


def flat_shading(meshes):
    previous = {}
    for mesh in {obj.data for obj in meshes}:
        flags = np.empty(len(mesh.polygons), dtype=np.bool_)
        mesh.polygons.foreach_get("use_smooth", flags)
        previous[mesh] = flags
        mesh.polygons.foreach_set("use_smooth", np.zeros_like(flags))
        mesh.update()

    def restore():
        for mesh, flags in previous.items():
            mesh.polygons.foreach_set("use_smooth", flags)
            mesh.update()

    return restore


# Sorted source colors retain material groupings while using a distinct clay palette.
CLAY_PALETTE = (
    (0.11, 0.37, 0.32), (0.48, 0.15, 0.23), (0.87, 0.42, 0.24),
    (0.28, 0.50, 0.73), (0.76, 0.58, 0.25), (0.76, 0.53, 0.41),
    (0.44, 0.42, 0.68), (0.80, 0.68, 0.48),
)


def apply_style(scene, style, meshes, selected, cleanup):
    """Apply to the working copy; register object and line changes for restoration."""
    contours = {
        "lineart": ((0.012, 0.016, 0.022), 1.4),
        "toon": ((0.012, 0.016, 0.022), 1.4),
        "technical": ((0.07, 0.12, 0.17), 0.8),
        "blueprint": ((0.42, 0.85, 1), 1.4),
    }
    if style in contours:
        cleanup.callback(set_contours(scene, *contours[style]))
    if style in {"lineart", "toon", "blueprint", "silhouette"}:
        scene.view_settings.view_transform = "Standard"

    if style == "flat":
        cleanup.callback(flat_shading(meshes))
    elif style in {"lineart", "blueprint", "silhouette", "clay"}:
        if style == "silhouette" and selected is not None:
            for obj in meshes:
                if obj not in selected and not obj.hide_render:
                    obj.hide_render = True
                    cleanup.callback(setattr, obj, "hide_render", False)
        material = {
            "lineart": lambda: emission("Paper", (1, 1, 1, 1)),
            "blueprint": lambda: emission("Blueprint blue", (0.009, 0.027, 0.088, 1)),
            "silhouette": lambda: emission("Silhouette ink", (0.007, 0.01, 0.02, 1)),
            "clay": lambda: surface("Clay", (0.73, 0.73, 0.73), 0.78),
        }[style]()
        for layer in scene.view_layers:
            layer.material_override = material
    elif style == "toon":
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        for obj in meshes:
            cleanup.callback(setattr, obj, "color", tuple(obj.color))
            obj.color = (*[min(0.94, max(0.06, c * 1.12 + 0.04)) for c in base_color(obj)[:3]], 1)
        material = cel_material()
        cleanup.callback(replace_materials(dict.fromkeys(meshes, material)))
    elif style == "technical":
        materials = {obj: surface("Technical pastel", tuple(0.25 + c * 0.50 for c in base_color(obj)[:3]), 0.65)
                     for obj in meshes}
        cleanup.callback(replace_materials(materials))
    elif style == "colored-clay":
        colors = {obj: tuple(round(c, 3) for c in base_color(obj)[:3]) for obj in meshes}
        palette = {color: CLAY_PALETTE[i % len(CLAY_PALETTE)]
                   for i, color in enumerate(sorted(set(colors.values())))}
        cleanup.callback(replace_materials(
            {obj: surface("Colored clay", palette[color], 0.82) for obj, color in colors.items()}))
    elif style == "wireframe":
        cleanup.callback(replace_materials(dict.fromkeys(meshes, wire_material())))
    elif style == "xray":
        cleanup.callback(replace_materials(dict.fromkeys(selected, transparent_material())))
    elif style == "metal":
        for layer in scene.view_layers:
            layer.material_override = surface("Satin bronze", (0.46, 0.23, 0.09), 0.34, metallic=0.93)
    elif style == "pixel":
        scene.render.resolution_percentage = max(
            1, min(100, math.ceil(100 * 128 / max(scene.render.resolution_x, scene.render.resolution_y))))


PIXEL_PALETTE = (
    "18202d", "293944", "3d4d4a", "4e6159", "617668", "829381", "a3ac90", "c3c4aa",
    "eff0de", "f9f7eb", "403532", "664e45", "90694e", "b78c61", "d2aa7c", "ebc99d",
    "6e414c", "a66063", "d78379", "3d536f", "587a98", "779cb6", "aec0d1", "cbd3d9",
)


def pixel_finish(path, width, height):
    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        image.colorspace_settings.name = "Non-Color"
        small_width, small_height = image.size
        pixels = np.empty(small_width * small_height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        rgb = pixels.reshape(small_height, small_width, 4)[:, :, :3]
        palette = np.array([[int(color[i:i+2], 16) for i in (0, 2, 4)]
                            for color in PIXEL_PALETTE], dtype=np.float32) / 255
        distance = np.sum((rgb[:, :, None, :] - palette) ** 2, axis=-1)
        indexed = palette[np.argmin(distance, axis=2)]
        rows = np.arange(height) * small_height // height
        cols = np.arange(width) * small_width // width
        rgba = np.ones((height, width, 4), dtype=np.float32)
        rgba[:, :, :3] = indexed[rows[:, None], cols]
    finally:
        bpy.data.images.remove(image)
    final = bpy.data.images.new("Pixel render", width, height)
    try:
        final.colorspace_settings.name = "Non-Color"
        final.pixels.foreach_set(rgba.ravel())
        final.filepath_raw = str(path)
        final.file_format = "PNG"
        final.save()
    finally:
        bpy.data.images.remove(final)
