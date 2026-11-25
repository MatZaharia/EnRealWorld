"""Use source diffuse colours for unsupported procedural glTF materials.

Blender procedural shader nodes do not automatically export to glTF. If an
exported material has neither a base-colour texture nor a base-colour factor,
use its source material's diffuse colour instead of glTF's implicit white.
Geometry, textures, and compressed binary buffers are left unchanged.

Usage: python patch_glb_materials.py source.blend preview.glb
"""
import argparse
import json
import struct
from pathlib import Path

import bpy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blend', type=Path)
    parser.add_argument('glb', type=Path)
    args = parser.parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    data = args.glb.read_bytes()
    magic, version, total = struct.unpack_from('<III', data)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise ValueError('Invalid GLB container')
    length, kind = struct.unpack_from('<II', data, 12)
    if kind != 0x4E4F534A:
        raise ValueError('GLB JSON chunk missing')
    doc = json.loads(data[20:20 + length])
    changed = 0
    for material in doc.get('materials', []):
        pbr = material.setdefault('pbrMetallicRoughness', {})
        if 'baseColorFactor' in pbr or 'baseColorTexture' in pbr:
            continue
        source = bpy.data.materials.get(material.get('name', ''))
        if source is None:
            continue
        pbr['baseColorFactor'] = [round(float(v), 6) for v in source.diffuse_color]
        changed += 1
    encoded = json.dumps(doc, separators=(',', ':')).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    tail = data[20 + length:]
    size = 20 + len(encoded) + len(tail)
    args.glb.write_bytes(struct.pack('<III', magic, version, size) + struct.pack('<II', len(encoded), kind) + encoded + tail)
    print(json.dumps({'file': args.glb.name, 'procedural_materials_approximated': changed}))


if __name__ == '__main__':
    main()
