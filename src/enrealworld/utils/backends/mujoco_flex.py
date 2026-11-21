"""Small native membrane adapter; explicit cloth only, no rigid surrogate.

Consumes code-produced build/Session products. Finite support: independent triangular
membranes, no attachments or self collision; centroid poses are observations,
never rigid-body constraints. Full deformed vertices are retained in every row.
"""
from pathlib import Path
import json,time,uuid
from functools import lru_cache
import xml.etree.ElementTree as E
import numpy as np
from scipy.spatial.transform import Rotation
from enrealworld.utils.files import save, digest
from ..geometry import write_obj,arrays
BACKEND='mujoco'
CAPABILITIES={'deformable','cloth','persistent_session'}
SUPPORTED_CHECKS={'finite_states','displacement'}
ACTIONS={'wait','force'}
PRODUCTS=('scene.xml','backend-config.json')


def flex_id(model,name):
    import mujoco
    return mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_FLEX,name)

@lru_cache(maxsize=1)
def _elasticity_options():
    """Probe the installed XML schema rather than assuming a version cutoff."""
    import mujoco
    xml='<mujoco><worldbody><body name="sheet"><flexcomp name="sheet" type="grid" count="2 2 1" spacing=".1 .1 .1" dim="2" mass=".01"><elasticity young="100" poisson=".3" thickness=".001" elastic2d="stretch"/></flexcomp></body></worldbody></mujoco>'
    try:
        mujoco.MjModel.from_xml_string(xml)
        return dict(elastic2d='stretch')
    except ValueError as exc:
        if "unrecognized attribute: 'elastic2d'" not in str(exc):raise
        return {}


def probe(config):
    import mujoco
    options=_elasticity_options();attribute=' elastic2d="stretch"' if options else ''
    responses=[];stiffness=[]
    # Exercise two elasticities, rather than treating a successful import as
    # proof that this installed backend responds to the material parameter.
    for young in (10,10000):
        xml=f'<mujoco><option timestep=".0001" gravity="0 0 0"/><worldbody><body name="sheet"><flexcomp name="sheet" type="grid" count="2 2 1" spacing=".1 .1 .1" dim="2" mass=".01"><elasticity young="{young}" poisson=".3" thickness=".001"{attribute}/></flexcomp></body></worldbody></mujoco>'
        model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model);mujoco.mj_forward(model,data)
        original=data.flexvert_xpos.copy();body=model.flex_vertbodyid[0]
        for _ in range(200):
            data.xfrc_applied[body,0]=.1;mujoco.mj_step(model,data)
        mujoco.mj_forward(model,data)
        delta=data.flexvert_xpos-original;responses.append((delta-delta.mean(axis=0)).tolist())
        stiffness.append(float(np.linalg.norm(model.flex_stiffness)))
    difference=float(np.linalg.norm(np.asarray(responses[0])-responses[1]))
    if not np.isfinite(difference) or difference<=1e-7 or not all(x>0 for x in stiffness):
        raise ValueError('installed backend membrane elasticity capability unverified')
    return dict(backend=BACKEND,version=mujoco.__version__,rendering='not_required',capabilities=sorted(CAPABILITIES),elasticity_options=options,elasticity_probe=dict(young_Pa=[10,10000],response_difference_m=difference,stiffness_norms=stiffness))




def build(build_dir,config):
    import mujoco
    if set(config)-{'backend','material_model','timestep_s'}:raise ValueError('unsupported membrane numerical configuration')
    out=Path(build_dir);desc=json.loads((out/'build.json').read_text())
    root=E.Element('mujoco');E.SubElement(root,'option',timestep=str(config['timestep_s']),gravity=' '.join(map(str,desc['environment']['gravity_m_s2'])))
    world=E.SubElement(root,'worldbody')
    for entity in desc['entities']:
        v,f,_=arrays(out/entity['reference']);sp=entity['material'];pose=entity['pose']
        body=E.SubElement(world,'body',name=entity['id']+'_frame',pos=' '.join(map(str,pose['position_m'])),quat=' '.join(map(str,pose['quaternion_wxyz'])))
        flex=E.SubElement(body,'flexcomp',name=entity['id'],type='direct',dim='2',point=' '.join(map(str,v.ravel())),element=' '.join(map(str,f.ravel())),mass=str(entity['mass_kg']),radius=str(sp['thickness_m']/2))
        E.SubElement(flex,'contact',selfcollide='none',internal='false',friction=str(entity['contact']['dynamic_friction'])+' 0 0')
        E.SubElement(flex,'elasticity',young=str(sp['young_modulus_Pa']),poisson=str(sp['poisson_ratio']),thickness=str(sp['thickness_m']),damping='0',**_elasticity_options())
    E.ElementTree(root).write(out/'scene.xml')
    mujoco.MjModel.from_xml_path(str(out/'scene.xml'))
    save(out/'backend-config.json',config)


class Session:
    def __init__(self,build_dir,output):
        import mujoco
        self.root=Path(build_dir);self.output=Path(output);self.output.mkdir(parents=True)
        self.description=json.loads((self.root/'build.json').read_text());self.model=mujoco.MjModel.from_xml_path(str(self.root/'scene.xml'));self.data=mujoco.MjData(self.model);mujoco.mj_forward(self.model,self.data)
        self.id=uuid.uuid4().hex;self.started=time.monotonic();self.steps=0;self.rows=[];self.operations=[]
        self.refs={n:digest(self.root/n) for n in PRODUCTS}
        self.refs.update({e['reference']:digest(self.root/e['reference']) for e in self.description['entities']})
        self.binding=dict(build_sha256=digest(self.root/'build.json'),resources={e['reference']:digest(self.root/e['reference']) for e in self.description['entities']},world_to_session=np.eye(4).tolist())
        self.native={}
        for e in self.description['entities']:
            idx=flex_id(self.model,e['id']);start=int(self.model.flex_vertadr[idx]);count=int(self.model.flex_vertnum[idx]);ids=self.model.flex_vertbodyid[start:start+count]
            self.native[e['id']]=dict(material_type='deformable',subtype='cloth',motion_mode='dynamic',vertices=self.data.flexvert_xpos[start:start+count].tolist(),mass_kg=float(self.model.body_mass[ids].sum()),vertex_count=count,flex_dimension=int(self.model.flex_dim[idx]),radius_m=float(self.model.flex_radius[idx]),dynamic_friction=float(self.model.flex_friction[idx,0]),stiffness_norm=float(np.linalg.norm(self.model.flex_stiffness[int(self.model.flex_elemadr[idx]):int(self.model.flex_elemadr[idx])+int(self.model.flex_elemnum[idx])])),triangles=self.model.flex_elem[int(self.model.flex_elemdataadr[idx]):int(self.model.flex_elemdataadr[idx])+3*int(self.model.flex_elemnum[idx])].reshape(-1,3).tolist())
        self._sample()

    def _sample(self):
        objects=[];vertices={}
        for e in self.description['entities']:
            idx=flex_id(self.model,e['id']);start=int(self.model.flex_vertadr[idx]);n=int(self.model.flex_vertnum[idx]);v=self.data.flexvert_xpos[start:start+n].copy();vertices[e['id']]=v.tolist()
            objects.append(dict(name=e['id'],pose=[*v.mean(axis=0),*e['pose']['quaternion_wxyz']],linear_velocity_m_s=((v.mean(axis=0)-np.asarray(self.rows[-1]['objects'][len(objects)]['pose'][:3]))/float(self.model.opt.timestep)).tolist() if self.rows else [0,0,0],angular_velocity_rad_s=[0,0,0]))
        self.rows.append(dict(time_s=float(self.data.time),objects=objects,soft_vertices=vertices,joints={}))

    def advance(self,action):
        import mujoco
        start=self.steps
        for _ in range(round(action['duration_s']/self.model.opt.timestep)):
            self.data.xfrc_applied[:]=0
            if action['type']=='force':
                idx=flex_id(self.model,action['entity']);v=action.get('vertex',0)
                if not isinstance(v,int):raise ValueError('cloth vertex index must be an integer')
                if not 0<=v<self.model.flex_vertnum[idx]:raise ValueError('invalid cloth vertex')
                body=self.model.flex_vertbodyid[self.model.flex_vertadr[idx]+v];self.data.xfrc_applied[body,:3]=action['force_N']
            elif action['type']!='wait':raise ValueError('unsupported membrane action')
            mujoco.mj_step(self.model,self.data);self.steps+=1;self._sample()
        self.operations.append(dict(action=action,start_step=start,end_step=self.steps))

    def finish(self):
        import mujoco
        for name,value in [('native.json',self.native),('states.json',self.rows),('contacts.json',[]),('operations.json',self.operations)]:save(self.output/name,value)
        changed=[n for n,h in self.refs.items() if digest(self.root/n)!=h]
        result=dict(backend=BACKEND,version=mujoco.__version__,session_ref=self.id,steps=self.steps,physics_hz=1/float(self.model.opt.timestep),sample_interval_s=float(self.model.opt.timestep),stages=dict(generated=True,loaded=True,ran=self.steps>0),world_binding=self.binding,environment=self.description['environment'],world_inputs_unchanged_at_end=not changed,native_input_refs=self.refs,operations_sha256=digest(self.output/'operations.json'),raw_hashes={n:digest(self.output/n) for n in ('native.json','states.json','contacts.json')},elapsed_s=time.monotonic()-self.started,observation_capabilities=dict(soft_vertices=True,contacts=False),limits='centroid pose/zero velocity placeholders are not rigid observations; use soft vertices for deformation; no contact acceptance')
        save(self.output/'session.json',result);return result


def audit_conversion(build_dir,*,native):
    desc=json.loads((Path(build_dir)/'build.json').read_text());checks=[]
    for e in desc['entities']:
        n=native[e['id']];v=arrays(Path(build_dir)/e['reference'])[0];R=Rotation.from_quat(e['pose']['quaternion_wxyz'],scalar_first=True).as_matrix()
        passed=n['material_type']=='deformable' and n['flex_dimension']==2 and len(v)==n['vertex_count'] and np.allclose(n['vertices'],v@R.T+e['pose']['position_m']) and np.isclose(n['mass_kg'],e['mass_kg']) and np.isclose(n['radius_m'],e['material']['thickness_m']/2) and np.isclose(n['dynamic_friction'],e['contact']['dynamic_friction']) and n['stiffness_norm']>0 and n['triangles']==arrays(Path(build_dir)/e['reference'])[1].tolist()
        checks.append(dict(entity=e['id'],outcome='pass' if passed else 'fail'))
    return dict(outcome='pass' if checks and all(c['outcome']=='pass' for c in checks) else 'fail',native=native,checks=checks,scope='native membrane dimension, topology, mass, radius, friction, stiffness presence and initial vertices; not complete elastic/contact equivalence')
