"""Headless CPU SAPIEN rigid execution. No renderer or robot is implied."""
from pathlib import Path
import json,time,uuid
import numpy as np
from .sapien import build_into_scene,native_actor
from enrealworld.utils.files import save, digest
BACKEND='sapien'
CAPABILITIES={'rigid','mesh','fixed','persistent_session'}
ACTIONS={'wait','force'}
PRODUCTS=('backend-config.json',)


def probe(config):
    import sapien
    from importlib.metadata import version
    if version('sapien').split('.')[0]!='3':raise ValueError('unsupported SAPIEN major version')
    scene=sapien.Scene([sapien.physx.PhysxCpuSystem()]);scene.step()
    return dict(backend='sapien',version=version('sapien'),physics='cpu',rendering='disabled')


def build(build_dir,config):
    dt=config.get('timestep_s')
    if not isinstance(dt,(int,float)) or not np.isfinite(dt) or dt<=0:raise ValueError('positive finite timestep required')
    save(Path(build_dir)/'backend-config.json',config)
    Session(build_dir,Path(build_dir)/'native-readback').finish()


class Session:
    def __init__(self,build_dir,output):
        import sapien
        probe({});self.root=Path(build_dir);self.output=Path(output);self.output.mkdir(parents=True,exist_ok=False)
        self.description=json.loads((self.root/'build.json').read_text());self.config=json.loads((self.root/'backend-config.json').read_text());self.dt=self.config['timestep_s']
        sapien.physx.set_scene_config(gravity=self.description['environment']['gravity_m_s2'])
        self.scene=sapien.Scene([sapien.physx.PhysxCpuSystem()]);self.scene.set_timestep(self.dt)
        self.actors=build_into_scene(self.scene,self.root)
        self.components={n:a.find_component_by_type(sapien.physx.PhysxRigidDynamicComponent) for n,a in self.actors.items()}
        self.native={e['id']:native_actor(self.actors[e['id']],e['motion_mode']) for e in self.description['entities']}
        self.rows=[];self.contacts=[];self.operations=[];self.steps=0;self.id=uuid.uuid4().hex;self.started=time.monotonic();self.finished=False
        # Bind the session to its build and geometry bytes so later edits cannot
        # be mistaken for evidence from the original native world.
        resources=sorted({e[k] for e in self.description['entities'] for k in ('reference','visual')}|{p for e in self.description['entities'] for p in e['collision_parts']})
        self.binding=dict(build_sha256=digest(self.root/'build.json'),resources={n:digest(self.root/n) for n in resources},world_to_session=np.eye(4).tolist())
        self.programs={'backend-config.json':digest(self.root/'backend-config.json')};self.record('initial')

    def record(self,phase):
        objects=[]
        for name,a in self.actors.items():
            c=self.components[name];p=a.pose
            v=c.linear_velocity if c else np.zeros(3);w=c.angular_velocity if c else np.zeros(3)
            objects.append(dict(name=name,pose=np.r_[p.p,p.q].tolist(),linear_velocity_m_s=np.asarray(v).tolist(),angular_velocity_rad_s=np.asarray(w).tolist()))
        self.rows.append(dict(time_s=self.steps*self.dt,phase=phase,objects=objects,joints={}))
        for c in self.scene.get_contacts():
            for p in c.points:self.contacts.append(dict(time_s=self.steps*self.dt,phase=phase,body0=c.bodies[0].entity.name,body1=c.bodies[1].entity.name,position_m=np.asarray(p.position).tolist(),normal=np.asarray(p.normal).tolist(),separation_m=float(p.separation),impulse_N_s=np.asarray(p.impulse).tolist()))

    def step_physics(self):
        self.scene.step()

    def advance(self,action):
        if self.finished:raise ValueError('session finalized')
        if set(action)-{'type','entity','force_N','torque_Nm','duration_s','phase'}:raise ValueError('unsupported action fields')
        kind=action['type'];duration=action['duration_s'];count=round(duration/self.dt)
        if kind not in ACTIONS or count<1 or not np.isclose(count*self.dt,duration,atol=1e-12):raise ValueError('unsupported action or duration')
        if kind=='force':
            c=self.components.get(action['entity']);force=np.asarray(action['force_N'],float);torque=np.asarray(action.get('torque_Nm',[0,0,0]),float)
            if c is None or force.shape!=(3,) or torque.shape!=(3,) or not np.isfinite(np.r_[force,torque]).all():raise ValueError('force needs dynamic body and finite vectors')
        record=dict(action=action,start_step=self.steps,session_ref=self.id);self.operations.append(record)
        # Forces are applied on every requested step; samples retain the phase.
        for _ in range(count):
            if kind=='force':c.add_force_torque(force,torque)
            self.step_physics();self.steps+=1;self.record(action.get('phase',kind))
        record['end_step']=self.steps

    def finish(self):
        if self.finished:raise ValueError('session finalized')
        from importlib.metadata import version
        changed=[n for n,h in {**self.programs,**self.binding['resources'],'build.json':self.binding['build_sha256']}.items() if digest(self.root/n)!=h]
        for name,value in [('native.json',self.native),('states.json',self.rows),('contacts.json',self.contacts),('operations.json',self.operations)]:save(self.output/name,value)
        info=dict(session_ref=self.id,backend='sapien',version=version('sapien'),physics_hz=1/self.dt,steps=self.steps,environment=self.description['environment'],stages=dict(generated=True,loaded=True,ran=self.steps>0),world_binding=self.binding,native_entity_names={n:n for n in self.actors},contact_recording_complete=True,world_inputs_unchanged_at_end=not changed,changed_inputs=changed,native_input_refs=self.programs,native_joints={},adapter_sha256=digest(__file__),operations_sha256=digest(self.output/'operations.json'),raw_hashes={n:digest(self.output/n) for n in ('native.json','states.json','contacts.json')},elapsed_s=time.monotonic()-self.started,observation_capabilities=dict(poses=True,velocities=True,contacts=True,forces=True,constraints=False,holding=False),instrumentation_limits='CPU rigid bodies; wait/force only; no robot/controller or rendering')
        save(self.output/'session.json',info);self.finished=True;return info
