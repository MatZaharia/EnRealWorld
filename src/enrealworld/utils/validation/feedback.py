"""Numerical readback comparisons and sampled controller checks."""
from pathlib import Path
import math
import numpy as np
from enrealworld.utils.files import digest


# Metre-scale float32 mesh readback versus float64 world parameters. Explicit
# absolute units plus relative roundoff; these are conversion checks only.
TOLERANCES = {'position_m': (1e-6, 1e-6), 'mass_kg': (1e-9, 1e-6),
              'inertia_kg_m2': (1e-12, 1e-5), 'angle_rad': (1e-6, 0.), 'dimensionless': (1e-7, 1e-6),
              'acceleration_m_s2': (1e-7, 1e-6), 'velocity_m_s': (1e-7, 1e-6), 'angular_velocity_rad_s': (1e-7, 1e-6),
              'linear_damping_N_s_m': (1e-9, 1e-6), 'angular_damping_Nm_s_rad': (1e-9, 1e-6)}


def close(actual, expected, quantity):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    atol, rtol = TOLERANCES[quantity]
    return bool(a.size and a.shape == b.shape and np.isfinite(a).all()
                and np.isfinite(b).all() and np.all(np.abs(a-b) <= atol+rtol*np.abs(b)))


def rotation_error(actual, expected):
    """Shortest SO(3) angle, stable near zero and invariant to q/-q. wxyz."""
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    if a.shape != (4,) or b.shape != (4,) or not np.isfinite([a,b]).all():
        return math.inf
    if min(np.linalg.norm(a), np.linalg.norm(b)) < 1e-12:
        return math.inf
    # Normalization is only a comparison convention, never a source mutation.
    a, b = a/np.linalg.norm(a), b/np.linalg.norm(b)
    if np.dot(a,b) < 0: b = -b
    return float(4*np.arctan2(np.linalg.norm(a-b), np.linalg.norm(a+b)))


READBACK_CHECKS={'parameter_consumption','geometry_consumption','joint_consumption','independent_body','functional_space','initial_relations'}


def controller_preflight(xml_path, request):
    """Cheap MuJoCo forward-only check of supplied configurations, no simulation.

    Candidate IK solutions are provided by the caller; this tool checks FK,
    limits and named robot/environment contacts, not reachability completeness.
    """
    import mujoco
    import xml.etree.ElementTree as ET
    if mujoco.__version__!='3.3.2': raise ValueError('reviewed MuJoCo version is 3.3.2')
    xml_path=Path(xml_path).resolve();document=ET.parse(xml_path).getroot()
    if document.findall('.//include') or document.findall('.//asset/model'):
        raise ValueError('finite controller preflight requires expanded MJCF, not includes or attached submodels')
    compiler=document.find('compiler');settings=compiler.attrib if compiler is not None else {}
    resources={xml_path.name:digest(xml_path)}
    for elem in document.iter():
        if 'file' not in elem.attrib: continue
        directory=settings.get('meshdir' if elem.tag=='mesh' else 'texturedir' if elem.tag=='texture' else 'assetdir',settings.get('assetdir',''))
        path=(xml_path.parent/directory/elem.attrib['file']).resolve()
        if not path.is_relative_to(xml_path.parent) or not path.is_file():
            raise ValueError('controller resources must be present inside the MJCF directory')
        resources[str(path.relative_to(xml_path.parent))]=digest(path)
    model=mujoco.MjModel.from_xml_path(str(xml_path)); data=mujoco.MjData(model)
    robot=set(request.get('robot_bodies',[])); samples=request.get('samples',[])
    if not robot or not samples: raise ValueError('named robot bodies and candidate samples required')
    if any(mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_BODY,n)<1 for n in robot): raise ValueError('missing robot body')
    limits=request['limits']; rows=[]
    if set(limits)!={'position_m','rotation_rad','penetration_m'} or any(not math.isfinite(v) or v<0 for v in limits.values()):
        raise ValueError('explicit finite preflight limits required; not numerical mapping tolerances')
    for sample in samples:
        q=np.asarray(sample['qpos'],float)
        if q.shape!=(model.nq,) or not np.isfinite(q).all(): raise ValueError('invalid full qpos')
        if np.asarray(sample['position_m']).shape!=(3,) or not np.isfinite(sample['position_m']).all() or not math.isfinite(rotation_error(sample['quaternion_wxyz'],[1,0,0,0])):
            raise ValueError('finite target position and nonzero quaternion required')
        data.qpos[:]=q; mujoco.mj_forward(model,data)
        errors=[]
        for j in range(model.njnt):
            if model.jnt_type[j] in (mujoco.mjtJoint.mjJNT_HINGE,mujoco.mjtJoint.mjJNT_SLIDE) and model.jnt_limited[j]:
                value=q[model.jnt_qposadr[j]]; lo,hi=model.jnt_range[j]
                if not lo<=value<=hi: errors.append(mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_JOINT,j))
        site=mujoco.mj_name2id(model,mujoco.mjtObj.mjOBJ_SITE,sample['site'])
        if site<0: raise ValueError('unknown end-effector site')
        quat=np.zeros(4);mujoco.mju_mat2Quat(quat,data.site_xmat[site])
        p_error=float(np.linalg.norm(data.site_xpos[site]-sample['position_m']))
        r_error=rotation_error(quat,sample['quaternion_wxyz']); contacts=[]
        for c in data.contact:
            names=[mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_BODY,int(model.geom_bodyid[g])) for g in (c.geom1,c.geom2)]
            # Includes robot self-contact. Visual-only geoms do not collide.
            if set(names)&robot: contacts.append(dict(bodies=names,distance_m=float(c.dist)))
        depth=max([0.]+[-c['distance_m'] for c in contacts])
        rows.append(dict(label=sample['label'],qpos=q.tolist(),site_position_m=data.site_xpos[site].tolist(),site_quaternion_wxyz=quat.tolist(),position_error_m=p_error,rotation_error_rad=r_error,
                         joint_limit_failures=errors,contacts=contacts,max_contact_envelope_depth_m=depth,
                         outcome='pass' if not errors and p_error<=limits['position_m'] and r_error<=limits['rotation_rad'] and depth<=limits['penetration_m'] else 'fail'))
    return dict(outcome='pass' if all(r['outcome']=='pass' for r in rows) else 'fail', samples=rows,
                limits=limits,xml_sha256=digest(xml_path),input_resources=resources,backend='mujoco/'+mujoco.__version__,
                scope='sampled FK/limits/contact-envelope preflight only; no IK search, control tracking, grasp or continuous path proof')
