"""MuJoCo 3.3.2: entity-addressed rigid/joint conversion and persistent raw capture.

No benchmark, robot controller, task-success flags, animations or grasp welds.
"""
from pathlib import Path
import json, time, uuid
import xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation
from enrealworld.utils.files import save, digest


def vec(x):
    return ' '.join(format(float(v), '.17g') for v in np.asarray(x).ravel())


def build(build_dir, config):
    """Numerical settings are explicit; physical properties come only from build.json."""
    import mujoco
    if mujoco.__version__.split('.')[0] != '3':
        raise ValueError('unsupported MuJoCo major version; native conversion audit required')
    required={'timestep_s','integrator','iterations','contact_solref','contact_solimp'}
    if set(config)-{'backend','diagnostic_fallback','fallback_reason'}!=required:
        raise ValueError('explicit numerical config keys required: '+str(sorted(required)))
    if config['timestep_s']<=0 or config['iterations']<1:
        raise ValueError('positive timestep and iterations required')
    path=Path(build_dir);desc=json.loads((path/'build.json').read_text())
    if not desc['backend_ready'] or desc['backend']!='mujoco':
        raise ValueError('refusing unsupported or not-ready build')
    if (path/'scene.xml').exists():
        raise ValueError('native output already exists; use a new build')
    r=E.Element('mujoco',model='structured_world')
    # Keep declared inertias authoritative and retain body identities for readback.
    E.SubElement(r,'compiler',angle='radian',inertiafromgeom='false',fusestatic='false')
    opt=E.SubElement(r,'option',timestep=str(config['timestep_s']),integrator=config['integrator'],iterations=str(config['iterations']),gravity=vec(desc['environment']['gravity_m_s2']))
    E.SubElement(opt,'flag',filterparent='disable')
    default=E.SubElement(r,'default');E.SubElement(default,'geom',condim='3',solref=vec(config['contact_solref']),solimp=vec(config['contact_solimp']))
    a=E.SubElement(r,'asset');w=E.SubElement(r,'worldbody');bodies={};entities={e['id']:e for e in desc['entities']}
    joints={}
    for rel in desc['relations']:
        if rel['type']!='joint':continue
        child=rel['child']['node']
        if child in joints:raise ValueError('multiple incoming joints/closed chains not implemented: '+child)
        if rel['parent'].get('interface') or rel['child'].get('interface'):
            raise ValueError('joint interface-frame conversion not implemented; use explicit asset-frame endpoints')
        if entities[child]['motion_mode']!='dynamic':raise ValueError('joint child must remain dynamic')
        # Validate both declared endpoint frames against initial layout and joint state.
        def T(p):
            x=np.eye(4);x[:3,:3]=Rotation.from_quat(p['quaternion_wxyz'],scalar_first=True).as_matrix();x[:3,3]=p['position_m'];return x
        j=rel['joint']
        if not j['parent_frame'] or not j['child_frame']:raise ValueError('explicit joint endpoint frames required')
        P=T(entities[rel['parent']['node']]['pose'])@T(j['parent_frame']);C=T(entities[child]['pose'])@T(j['child_frame'])
        predicted=P.copy()
        if j['type']!='fixed':
            axis=T(entities[rel['parent']['node']]['pose'])[:3,:3]@j['axis_in_parent'];position=rel['initial_state']['position']
            if j['type']=='prismatic':predicted[:3,3]+=axis*position
            else:predicted[:3,:3]=Rotation.from_rotvec(axis*position).as_matrix()@P[:3,:3]
        from enrealworld.utils.validation.feedback import close, rotation_error, TOLERANCES
        if not close(predicted[:3,3],C[:3,3],'position_m') or rotation_error(Rotation.from_matrix(predicted[:3,:3]).as_quat(scalar_first=True),Rotation.from_matrix(C[:3,:3]).as_quat(scalar_first=True))>TOLERANCES['angle_rad'][0]:raise ValueError('joint endpoint frames conflict with initial layout/state: '+rel['id'])
        joints[child]=rel
    def matrix(p):
        t=np.eye(4);t[:3,:3]=Rotation.from_quat(p['quaternion_wxyz'],scalar_first=True).as_matrix();t[:3,3]=p['position_m'];return t
    # MJCF uses a body tree. Construct parents first and transform child poses
    # from world coordinates into their joint parent's frame.
    def body(nid,chain=()):
        if nid in bodies:return bodies[nid]
        if nid in chain:raise ValueError('joint cycle not supported')
        ent=entities[nid];T=matrix(ent['pose']);parent=w
        if nid in joints:
            parentid=joints[nid]['parent']['node'];parent=body(parentid,chain+(nid,));T=np.linalg.inv(matrix(entities[parentid]['pose']))@T
        b=E.SubElement(parent,'body',name=nid,pos=vec(T[:3,3]),quat=vec(Rotation.from_matrix(T[:3,:3]).as_quat(scalar_first=True)));bodies[nid]=b
        if nid in joints:
            rel=joints[nid];j=rel['joint']
            if j['type']!='fixed':
                pR=matrix(entities[rel['parent']['node']]['pose'])[:3,:3];cR=matrix(ent['pose'])[:3,:3];axis=cR.T@pR@j['axis_in_parent']
                E.SubElement(b,'joint',name=rel['id'],type={'prismatic':'slide','revolute':'hinge'}[j['type']],pos=vec(j['child_frame']['position_m']),axis=vec(axis),limited='true',range=vec(j['limits']),ref=str(rel['initial_state']['position']),damping=str(j['damping']))
        elif ent['motion_mode']=='dynamic':E.SubElement(b,'freejoint',name='free_'+nid)
        if ent['motion_mode']=='dynamic':
            I=np.asarray(ent['inertia_tensor_kg_m2']);E.SubElement(b,'inertial',pos=vec(ent['center_of_mass_m']),mass=str(ent['mass_kg']),fullinertia=vec([I[0,0],I[1,1],I[2,2],I[0,1],I[0,2],I[1,2]]))
        for i,part in enumerate(ent['collision_parts']):
            name=nid+'_collision_'+str(i)
            shapes=ent.get('native_collision_shapes')
            if shapes:
                shape=shapes[i];attributes=dict(type='box',size=vec(np.asarray(shape['geometry']['size_m'])/2),pos=vec(shape['pose']['position_m']),quat=vec(shape['pose']['quaternion_wxyz']))
            else:
                E.SubElement(a,'mesh',name=name,file=part);attributes=dict(type='mesh',mesh=name)
            E.SubElement(b,'geom',name=name,**attributes,friction=vec([ent['contact']['dynamic_friction'],0,0]),group='3',density='0')
        mesh=nid+'_visual';E.SubElement(a,'mesh',name=mesh,file=ent['visual']);E.SubElement(b,'geom',name=mesh,type='mesh',mesh=mesh,contype='0',conaffinity='0',density='0',group='1',rgba='.45 .65 .8 1')
        return b
    for nid in desc['assembly_plan']['build_order']:body(nid)
    E.indent(r);E.ElementTree(r).write(path/'scene.xml',encoding='unicode');save(path/'backend-config.json',config)
    model=mujoco.MjModel.from_xml_path(str(path/'scene.xml'));data=mujoco.MjData(model)
    for nid,ent in entities.items():
        init=ent['initial_state']
        if nid in joints:
            j=joints[nid]
            if j['joint']['type']!='fixed':data.qvel[model.joint(j['id']).dofadr[0]]=j['initial_state']['velocity']
            if np.any(init['linear_velocity_m_s']) or np.any(init['angular_velocity_rad_s']):raise ValueError('jointed body bulk velocity must be zero; specify joint initial velocity')
        elif ent['motion_mode']=='dynamic':
            joint=model.joint('free_'+nid);idx=joint.dofadr[0];R=Rotation.from_quat(ent['pose']['quaternion_wxyz'],scalar_first=True)
            # Schema velocity is at COM; free-joint translation is at body origin.
            omega=np.asarray(init['angular_velocity_rad_s']);lever=R.apply(ent['center_of_mass_m'])
            data.qvel[idx:idx+3]=np.asarray(init['linear_velocity_m_s'])-np.cross(omega,lever)
            data.qvel[idx+3:idx+6]=R.inv().apply(omega)
    np.savez(path/'initial-state.npz',qpos=data.qpos,qvel=data.qvel)
    return {'generated':True,'loaded':True,'ran':False,'behavior_passed':None,'model':str(path/'scene.xml')}


class Session:
    """One world state across actions. Only bounded forces/joint efforts/wait are exposed."""
    def __init__(self, build_dir, output):
        import mujoco
        if mujoco.__version__.split('.')[0]!='3':raise ValueError('unsupported MuJoCo major version')
        self.root=Path(build_dir);self.output=Path(output);self.output.mkdir(parents=True,exist_ok=False)
        self.description=json.loads((self.root/'build.json').read_text())
        if not self.description['backend_ready']:raise ValueError('world not ready')
        self.model=mujoco.MjModel.from_xml_path(str(self.root/'scene.xml'));self.data=mujoco.MjData(self.model)
        init=np.load(self.root/'initial-state.npz');self.data.qpos[:]=init['qpos'];self.data.qvel[:]=init['qvel'];mujoco.mj_forward(self.model,self.data)
        self.steps=0;self.rows=[];self.contacts=[];self.operations=[];self.id=uuid.uuid4().hex;self.started=time.monotonic();self.finished=False
        resources=sorted({e[k] for e in self.description['entities'] for k in ('reference','visual')}|{p for e in self.description['entities'] for p in e['collision_parts']})
        self.binding={'build_sha256':digest(self.root/'build.json'),'resources':{n:digest(self.root/n) for n in resources},'world_to_session':np.eye(4).tolist()}
        self.programs={n:digest(self.root/n) for n in ('scene.xml','backend-config.json','initial-state.npz')}
        self.native=self.read_native();self.joints_readback=self.native_joints()
        self.record('initial')
        self.checkpoint_partial()
    def checkpoint_partial(self):
        for name,value in [('native.json',self.native),('states.json',self.rows),('contacts.json',self.contacts),('operations.json',self.operations)]:
            save(self.output/'partial'/name,value)
        save(self.output/'partial/session.json',dict(session_ref=self.id,steps=self.steps,incomplete=True,acceptance_eligible=False,reason='action-boundary checkpoint; finalization required'))
    def read_native(self):
        import mujoco
        m,d=self.model,self.data;result={}
        for ent in self.description['entities']:
            name=ent['id'];bid=m.body(name).id;R=Rotation.from_quat(m.body_iquat[bid],scalar_first=True).as_matrix();shapes=[]
            for gid in np.where(m.geom_bodyid==bid)[0]:
                if not m.geom_contype[gid]:continue
                if m.geom_type[gid]==mujoco.mjtGeom.mjGEOM_BOX:
                    from itertools import product
                    v=np.array(list(product([-1,1],repeat=3)))*m.geom_size[gid]
                else:
                    mid=m.geom_dataid[gid];v=m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid]+m.mesh_vertnum[mid]].astype(float)
                # MuJoCo recenters mesh vertices; actual geom frame already includes that transform.
                shapes.append(dict(primitive_type="box" if m.geom_type[gid]==mujoco.mjtGeom.mjGEOM_BOX else "mesh",vertices=v.tolist(),scale=[1,1,1],local_position_m=m.geom_pos[gid].tolist(),local_quaternion_wxyz=m.geom_quat[gid].tolist(),dynamic_friction=float(m.geom_friction[gid,0]),static_friction=None,restitution=None,source_geom_id=int(gid)))
            result[name]=dict(motion_mode='dynamic' if np.any(m.dof_bodyid==bid) or m.body_weldid[bid]!=0 else 'static',declared_motion_mode=ent['motion_mode'],native_free_joint=any(m.jnt_type[j]==mujoco.mjtJoint.mjJNT_FREE for j in range(m.njnt) if m.jnt_bodyid[j]==bid),native_joint_count=int(m.body_jntnum[bid]),native_weld_id=int(m.body_weldid[bid]),native_equality_constraints=int(m.neq),mass_kg=float(m.body_mass[bid]),center_of_mass_m=m.body_ipos[bid].tolist(),inertia_tensor_kg_m2=(R@np.diag(m.body_inertia[bid])@R.T).tolist(),collision_shapes=shapes)
        return result
    def native_joints(self):
        m,d=self.model,self.data;result={}
        for r in self.description['relations']:
            if r['type']!='joint' or r['joint']['type']=='fixed':continue
            j=m.joint(r['id']);bid=int(m.jnt_bodyid[j.id]);axis=d.xmat[bid].reshape(3,3)@m.jnt_axis[j.id]
            result[r['id']]=dict(axis_world=axis.tolist(),limits=m.jnt_range[j.id].tolist(),damping=float(m.dof_damping[j.dofadr[0]]),initial_position=float(d.qpos[j.qposadr[0]]),initial_velocity=float(d.qvel[j.dofadr[0]]))
        return result
    def record(self,phase):
        import mujoco
        m,d=self.model,self.data;objects=[]
        for ent in self.description['entities']:
            b=m.body(ent['id']).id;vel=np.zeros(6);mujoco.mj_objectVelocity(m,d,mujoco.mjtObj.mjOBJ_BODY,b,vel,0)
            objects.append(dict(name=ent['id'],pose=np.r_[d.xpos[b],d.xquat[b]].tolist(),center_of_mass_world_m=d.xipos[b].tolist(),linear_velocity_m_s=vel[3:].tolist(),angular_velocity_rad_s=vel[:3].tolist()))
        self.rows.append(dict(time_s=self.steps*m.opt.timestep,phase=phase,objects=objects,joints={r['id']:dict(position=float(d.qpos[m.joint(r['id']).qposadr[0]]),velocity=float(d.qvel[m.joint(r['id']).dofadr[0]])) for r in self.description['relations'] if r['type']=='joint' and r['joint']['type']!='fixed'}))
        for i,c in enumerate(d.contact):
            force=np.zeros(6);mujoco.mj_contactForce(m,d,i,force)
            self.contacts.append(dict(time_s=self.steps*m.opt.timestep,phase=phase,body0=m.body(m.geom_bodyid[c.geom1]).name,body1=m.body(m.geom_bodyid[c.geom2]).name,position_m=c.pos.tolist(),normal=c.frame[:3].tolist(),separation_m=float(c.dist),impulse_N_s=(force[:3]*m.opt.timestep).tolist(),force_contact_frame_N=force[:3].tolist(),force_on_body1_world_N=(c.frame.reshape(3,3).T@force[:3]).tolist()))
    def advance(self,action):
        import mujoco
        if self.finished:raise ValueError('session already finalized')
        allowed={'type','entity','relation','force_N','torque_Nm','effort','duration_s','phase'}
        if set(action)-allowed:raise ValueError('unknown action fields')
        kind=action['type'];duration=action['duration_s'];dt=self.model.opt.timestep;count=round(duration/dt)
        if count<1 or not np.isclose(count*dt,duration,atol=1e-12):raise ValueError('action duration must be positive integer timesteps')
        if kind not in ('wait','force','joint_effort'):raise ValueError('unsupported operation; poses/temporary welds are not action tools')
        if kind=='force':
            e=next(e for e in self.description['entities'] if e['id']==action['entity'])
            if e['motion_mode']!='dynamic':raise ValueError('force requires dynamic body')
            applied=np.r_[action['force_N'],action.get('torque_Nm',[0,0,0])].astype(float)
            if applied.shape!=(6,) or not np.isfinite(applied).all():raise ValueError('finite force and torque required')
        if kind=='joint_effort':
            j=self.model.joint(action['relation']);idx=j.dofadr[0]
            if not np.isfinite(action['effort']):raise ValueError('finite effort required')
        record=dict(action=action,start_step=self.steps,session_ref=self.id);self.operations.append(record)
        for _ in range(count):
            self.data.xfrc_applied[:]=0;self.data.qfrc_applied[:]=0
            if kind=='force':self.data.xfrc_applied[self.model.body(action['entity']).id]=applied
            if kind=='joint_effort':self.data.qfrc_applied[idx]=action['effort']
            mujoco.mj_step(self.model,self.data);self.steps+=1;mujoco.mj_forward(self.model,self.data);self.record(action.get('phase',kind))
        record['end_step']=self.steps
        self.checkpoint_partial()
    def snapshot(self,filename):
        import mujoco
        size=mujoco.mj_stateSize(self.model,mujoco.mjtState.mjSTATE_INTEGRATION);values=np.zeros(size);mujoco.mj_getState(self.model,self.data,values,mujoco.mjtState.mjSTATE_INTEGRATION)
        np.savez(filename,integration_state=values,model_sha256=digest(self.root/'scene.xml'),steps=self.steps)
        return {'supported':'same compiled MuJoCo model only; no cross-model/topology migration','path':str(filename)}
    def finish(self):
        import mujoco
        if self.finished:raise ValueError('session already finalized; never overwrite raw evidence')
        changed=[n for n,h in self.programs.items() if not (self.root/n).is_file() or digest(self.root/n)!=h]
        if digest(self.root/'build.json')!=self.binding['build_sha256']:changed.append('build.json')
        changed.extend(n for n,h in self.binding['resources'].items() if not (self.root/n).is_file() or digest(self.root/n)!=h)
        for n,v in [('native.json',self.native),('states.json',self.rows),('contacts.json',self.contacts),('operations.json',self.operations)]:save(self.output/n,v)
        info=dict(units='SI',coordinate_convention=dict(handedness='right',up_axis='Z',quaternion_order='wxyz',velocities='world frame at body COM',contact_force='world force on body1'),unit_conversions=[],representation_precision=dict(native_state=str(self.data.qpos.dtype),native_mesh_vertices=str(self.model.mesh_vert.dtype)),observation_capabilities=dict(poses=True,velocities=True,contacts=True,forces=True,constraints=True,holding=False),sample_interval_s=float(self.model.opt.timestep),session_ref=self.id,backend='mujoco',version=mujoco.__version__,physics_hz=1/self.model.opt.timestep,steps=self.steps,environment=self.description['environment'],stages=dict(generated=True,loaded=True,ran=self.steps>0),world_binding=self.binding,native_entity_names={e['id']:e['id'] for e in self.description['entities']},contact_recording_complete=True,world_inputs_unchanged_at_end=not changed,changed_inputs=changed,native_input_refs=self.programs,native_joints=self.joints_readback,adapter_sha256=digest(__file__),operations_sha256=digest(self.output/'operations.json'),raw_hashes={n:digest(self.output/n) for n in ('native.json','states.json','contacts.json')},elapsed_s=time.monotonic()-self.started,instrumentation_limits='bounded operation API; controller source/independent review still required; sampled per timestep, no continuous geometric certificate')
        save(self.output/'session.json',info);self.finished=True;return info
