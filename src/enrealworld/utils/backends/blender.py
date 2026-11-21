"""Blender visual adapter, invoked with Blender --background --python.

Consumes the exact compiled world/resources and optional MuJoCo states. It does
not claim Bullet dynamics or infer physical success from rendered animation.
"""
from pathlib import Path
import argparse,hashlib,json


def main(build_dir,output,trajectory=None,reuse=None):
    import bpy
    from mathutils import Quaternion,Vector
    root=Path(build_dir).resolve();out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    desc=json.loads((root/'build.json').read_text());objects={};checks=[]
    if reuse:
        import shutil
        reuse=Path(reuse).resolve();bpy.ops.wm.open_mainfile(filepath=str(reuse/'scene.blend'))
        shutil.copy2(reuse/'preview.png',out/'preview.png')
    else:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    def mesh_obj(name,path):
        vertices=[];faces=[]
        for line in path.read_text().splitlines():
            x=line.split()
            if not x:continue
            if x[0]=='v':vertices.append(tuple(float(v) for v in x[1:4]))
            if x[0]=='f':faces.append(tuple(int(v.split('/')[0])-1 for v in x[1:]))
        mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],faces);mesh.update();obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);return obj
    for ent in desc['entities']:
        obj=bpy.data.objects[ent['id']] if reuse else mesh_obj(ent['id'],root/ent['visual']);obj.rotation_mode='QUATERNION';obj.location=ent['pose']['position_m'];obj.rotation_quaternion=ent['pose']['quaternion_wxyz']
        obj['asset_id']=ent['asset_id'];obj['asset_revision']=ent['asset_revision'];obj['template_id']=ent['template_ref']['id'];obj['template_version']=ent['template_ref']['version'];obj['physical_role']='visual_only';obj['authoritative_mass_kg']=ent['mass_kg'];obj['motion_mode']=ent['motion_mode']
        material=bpy.data.materials.new(ent['id']+'_preview');material.diffuse_color=(.35,.58,.78,1) if ent['motion_mode']=='dynamic' else (.5,.52,.55,1);obj.data.materials.append(material);objects[ent['id']]=obj
        checks.append({'entity':ent['id'],'vertices':len(obj.data.vertices),'faces':len(obj.data.polygons),'local_vertices_m':[list(v.co) for v in obj.data.vertices],'position_m':list(obj.location),'quaternion_wxyz':list(obj.rotation_quaternion),'visual_sha256':hashlib.sha256((root/ent['visual']).read_bytes()).hexdigest(),'linked_mass_kg':obj['authoritative_mass_kg'],'physics_executed':False})
    if not reuse:
        scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT';scene.render.resolution_x=640;scene.render.resolution_y=480;scene.render.resolution_percentage=100
        scene.world.color=(.15,.15,.15)
        bpy.ops.object.light_add(type='AREA',location=(1,-2,4));bpy.context.object.data.energy=500;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=4
        bpy.ops.object.camera_add(location=(1.6,-2,1.3));camera=bpy.context.object;direction=Vector((0,0,.2))-camera.location;camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=1.7;scene.camera=camera
        scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    # Replaying external physical states is presentation only; no Blender physics flag.
    replay_ref=None;frame_rows={};trajectory_samples=[]
    if trajectory:
        path=Path(trajectory);rows=json.loads(path.read_text());replay_ref={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kind':'external physics trajectory visualization only'}
        if not rows:raise ValueError('empty trajectory')
        for frame,row in enumerate(rows[::max(1,len(rows)//60)],start=1):
            frame_rows[frame]=row
            names={o['name'] for o in row['objects']}
            if names!=set(objects):raise ValueError('trajectory entity mapping mismatch')
            for value in row['objects']:
                o=objects[value['name']];o.location=value['pose'][:3];o.rotation_quaternion=value['pose'][3:];o.keyframe_insert('location',frame=frame);o.keyframe_insert('rotation_quaternion',frame=frame)
        scene.frame_end=frame;scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
    # Reload the saved native file and export actual mesh and matrix values.
    bpy.ops.wm.open_mainfile(filepath=str(out/'scene.blend'))
    if frame_rows:
        for frame in sorted({min(frame_rows),sorted(frame_rows)[len(frame_rows)//2],max(frame_rows)}):
            bpy.context.scene.frame_set(frame)
            values=[dict(name=n,pose=list(bpy.data.objects[n].location)+list(bpy.data.objects[n].rotation_quaternion)) for n in objects]
            trajectory_samples.append(dict(frame=frame,time_s=frame_rows[frame]['time_s'],objects=values))
            if frame!=min(frame_rows):
                bpy.context.scene.render.filepath=str(out/f'trajectory-{frame:04d}.png');bpy.ops.render.render(write_still=True)
        bpy.context.scene.frame_set(1)
    readback=[]
    for ent in desc['entities']:
        o=bpy.data.objects[ent['id']];readback.append(dict(entity=o.name,asset_id=o['asset_id'],asset_revision=o['asset_revision'],template_ref=dict(id=o['template_id'],version=o['template_version']),mass_metadata_kg=o['authoritative_mass_kg'],position_m=list(o.location),quaternion_wxyz=list(o.rotation_quaternion),vertices=[list(v.co) for v in o.data.vertices],faces=[list(p.vertices) for p in o.data.polygons]))
    report=dict(preview_reused_from=str(reuse) if reuse else None,backend='blender_visual',version=bpy.app.version_string,build_sha256=hashlib.sha256((root/'build.json').read_bytes()).hexdigest(),stages=dict(generated=True,loaded=True,ran=False,behavior_passed=None),visual_construction=True,rendered=True,native_reload=True,entities=checks,native_readback=readback,replay=replay_ref,trajectory_samples=trajectory_samples,limits=['visual geometry and linked physical metadata only; no Bullet dynamics','flat preview material, no photometric fidelity claim','sampled external animation is not physics validation'])
    (out/'visual.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    import sys
    p=argparse.ArgumentParser();p.add_argument('build');p.add_argument('output');p.add_argument('--trajectory');p.add_argument('--reuse');a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);main(a.build,a.output,a.trajectory,a.reuse)
