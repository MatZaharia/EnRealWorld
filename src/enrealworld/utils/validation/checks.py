"""Independent calculations from raw backend evidence and explicit test criteria.

No agent success flags, backend pass flags, benchmark IDs or hidden scoring.
Supported checks are finite, not a complete physical correctness certificate.
"""
from pathlib import Path
import hashlib
import subprocess
import json
import numpy as np
from scipy.spatial.transform import Rotation
from enrealworld.utils.files import digest, save
from enrealworld.utils.validation.feedback import close, rotation_error, TOLERANCES, READBACK_CHECKS
from enrealworld.utils.geometry import free_space_samples


def convex_solid_distance(a, b):
    """Exact convex-polytope Hausdorff distance, independent of vertex identity.

    Distance to a convex solid is convex: its maximum on a polytope occurs
    at a vertex. Test both directions, with interior points at zero distance.
    Degenerate/nonfinite colliders fail rather than receiving a loose fallback.
    """
    from scipy.spatial import ConvexHull, QhullError
    import trimesh
    def directed(points, target):
        try: hull = ConvexHull(target)
        except QhullError as exc: raise ValueError("degenerate convex collider") from exc
        mesh = trimesh.Trimesh(vertices=target, faces=hull.simplices, process=False)
        outside = np.max(points @ hull.equations[:, :3].T + hull.equations[:, 3], axis=1) > 0
        if not outside.any(): return 0.0
        return float(trimesh.proximity.closest_point_naive(mesh, points[outside])[1].max())
    a, b = np.asarray(a, float), np.asarray(b, float)
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError('nonfinite collider vertices')
    return max(directed(a, b), directed(b, a))


def native_shapes(native):
    result = []
    for sh in native["collision_shapes"]:
        v = np.asarray(sh["vertices"]) * np.asarray(sh["scale"])
        R = Rotation.from_quat(sh["local_quaternion_wxyz"], scalar_first=True).as_matrix()
        result.append(v @ R.T + sh["local_position_m"])
    return result


def initial_relations(compiled, native, first_row):
    """Geometry from native readback and initial state; each relation stays separate."""
    import trimesh
    from scipy.spatial import ConvexHull
    body = {o["name"]: o["pose"] for o in first_row["objects"]}
    def matrix(p):
        T=np.eye(4);T[:3,:3]=Rotation.from_quat(p[3:],scalar_first=True).as_matrix();T[:3,3]=p[:3];return T
    def world_mesh(name):
        parts=[]
        for v in native_shapes(native[name]):
            h=trimesh.convex.convex_hull(v);parts.append(h)
        m=trimesh.util.concatenate(parts);m.apply_transform(matrix(body[name]));return m
    results=[]
    up=-np.asarray(compiled["environment"]["gravity_m_s2"],float)
    up/=np.linalg.norm(up)
    for r in compiled["relations"]:
        item=dict(relation_id=r["id"],type=r["type"],evidence_level="geometry_only",outcome="not_calculated",reason=None)
        results.append(item)
        if r.get("scope") != "initial_state":
            item["reason"]="throughout/structural relation requires corresponding trajectory/constraint test";continue
        a,b=r["subject"]["node"],r["target"]["node"]
        if a not in native or b not in native or a not in body or b not in body:
            item["reason"]="relation endpoint missing from native evidence";continue
        if r["type"]=="supported_by":
            subject,target=world_mesh(a),world_mesh(b)
            v=subject.vertices;z=v@up;points=v[z<=z.min()+r["tolerance_m"]]
            eps=r["tolerance_m"]+1e-5
            hit,index,_=target.ray.intersects_location(points+up*eps,np.tile(-up,(len(points),1)),multiple_hits=False)
            gaps=np.einsum('ij,j->i',points[index]+up*eps-hit,up)-eps if len(hit) else np.array([])
            gap=float(np.min(np.abs(gaps))) if len(gaps) else None
            item.update(outcome="pass" if gap is not None and gap<=r["tolerance_m"] else "fail",
                        value=dict(minimum_absolute_gap_m=gap,sampled_bottom_points=len(points),hit_points=len(hit)),
                        scope="initial sampled bottom-to-collider proximity; not static stability proof")
        elif r["type"]=="inside":
            target=next(e for e in compiled['entities'] if e['id']==b)
            interface=next((x for x in target['interfaces'] if x['id']==r['target'].get('interface') and x['type']=='containment_region'),None)
            if not interface or not interface.get('pose') or (interface.get('geometry') or {}).get('kind')!='box':
                item['reason']='explicit box containment_region interface required';continue
            P=interface['pose'];T=matrix(body[b])@matrix(P['position_m']+P['quaternion_wxyz'])
            points=world_mesh(a).vertices;local=(np.c_[points,np.ones(len(points))]@np.linalg.inv(T).T)[:,:3]
            excess=np.max(np.abs(local)-np.asarray(interface['geometry']['size_m'])/2)
            item.update(outcome='pass' if excess<=r['tolerance_m'] else 'fail',value=dict(max_boundary_excess_m=float(excess),sampled_vertices=len(points)),scope='declared box interior, convex vertices at initial state; not retention under motion')
        else:
            item["reason"]="requires explicit containment region, clearance or contact-event test; not inferred from names/bounding boxes"
    return results


def evaluate(test, raw_dir, output, *, build_dir=None, task_root=None):
    """Return per-check outcomes; absent/empty evidence is never a pass."""
    root = Path(raw_dir)
    names = ("session.json", "native.json", "states.json", "contacts.json")
    missing = [n for n in names if not (root/n).is_file()]
    checks = []
    data = {}
    if not missing:
        data = {n: json.loads((root/n).read_text()) for n in names}
    rows = data.get("states.json", [])
    native = data.get("native.json", {})
    session = data.get("session.json", {})
    contacts = data.get("contacts.json", [])
    # Check recorded hashes before interpreting samples; a diagnostic or
    # interrupted session cannot supply formal acceptance evidence.
    integrity = all((root/n).is_file() and session.get('raw_hashes',{}).get(n)==digest(root/n)
                    for n in ('states.json','contacts.json','native.json')) if session else False
    if session.get('operations_sha256'):
        integrity = integrity and (root/'operations.json').is_file() and digest(root/'operations.json')==session['operations_sha256']
    if session.get('world_inputs_unchanged_at_end') is False:integrity=False
    diagnostic_copy=session.get('diagnostic_only') is True or any((p/'diagnostic-only.json').is_file() for p in (root,*root.parents))
    if diagnostic_copy or session.get('incomplete') is True or (root/'interrupted.json').is_file():integrity=False
    readback=test.get('execution_mode')=='readback' and not test.get('actions') and bool(test.get('checks')) and all(c.get('type') in READBACK_CHECKS for c in test['checks'])
    valid = (len(rows) >= (1 if readback else 2) and all(isinstance(r.get("objects"), list) and r["objects"] for r in rows))
    valid = valid and integrity
    if valid:
        t = np.array([r["time_s"] for r in rows], float)
        valid = bool(np.isfinite(t).all() and np.all(np.diff(t) > 0))
        valid = valid and session.get("steps")==len(rows)-1 and bool(session.get("physics_hz"))
        if valid:
            valid = bool(np.allclose(np.diff(t),1/session["physics_hz"],atol=1e-10))
    else:
        t = np.array([])
    objects = {}
    if valid:
        initial_names = [o["name"] for o in rows[0]["objects"]]
        valid = len(initial_names) == len(set(initial_names)) and all([o["name"] for o in r["objects"]] == initial_names for r in rows)
        if valid:
            objects = {n: dict(poses=np.asarray([r["objects"][i]["pose"] for r in rows], float),
                v=np.asarray([r["objects"][i]["linear_velocity_m_s"] for r in rows], float),
                w=np.asarray([r["objects"][i]["angular_velocity_rad_s"] for r in rows], float)) for i,n in enumerate(initial_names)}
            valid = all(np.isfinite(a).all() for o in objects.values() for a in o.values())
    operation_reason=None
    operations_verified=None
    if 'actions' in test and (session.get('backend')=='mujoco' or session.get('operations_sha256')):
        path=root/'operations.json'
        ops=json.loads(path.read_text()) if path.is_file() else []
        performed=[x.get('action') for x in ops]
        boundaries=bool(ops) and ops[0].get('start_step')==0 and ops[-1].get('end_step')==session.get('steps')
        boundaries=boundaries and all(x.get('end_step',-1)>x.get('start_step',-1) for x in ops) and all(a.get('end_step')==b.get('start_step') for a,b in zip(ops,ops[1:]))
        if readback:boundaries=not ops and session.get('steps')==0
        operations_verified=bool(boundaries and performed==test['actions'] and session.get('operations_sha256')==digest(path)) if path.is_file() else False
        if not operations_verified:operation_reason='missing/mismatched operation sequence or step boundaries against TestSpec'
    compiled = json.loads((Path(build_dir)/"build.json").read_text()) if build_dir else None
    compiled_entities = {e["id"]: e for e in compiled["entities"]} if compiled else {}
    binding_reason=None
    if compiled:
        binding=session.get('world_binding') or {}
        expected_resources=sorted({e[role] for e in compiled['entities'] for role in ('reference','visual')} |
                                  {p for e in compiled['entities'] for p in e['collision_parts']})
        if binding.get('build_sha256')!=digest(Path(build_dir)/'build.json') or binding.get('resources')!={n:digest(Path(build_dir)/n) for n in expected_resources}:
            binding_reason='raw session missing/mismatched actual world/resource binding'
        elif valid:
            W=np.asarray(binding['world_to_session'])
            if W.shape!=(4,4) or not close(W[:3,:3].T@W[:3,:3],np.eye(3),'dimensionless'):
                binding_reason='invalid world-to-session mapping'
            else:
                for n,e in compiled_entities.items():
                    if n not in objects:
                        binding_reason='compiled entity missing from raw initial state';break
                    p=e['pose'];expected_p=W[:3,:3]@p['position_m']+W[:3,3]
                    expected_R=W[:3,:3]@Rotation.from_quat(p['quaternion_wxyz'],scalar_first=True).as_matrix()
                    actual=objects[n]['poses'][0]
                    if not close(actual[:3],expected_p,'position_m') or not rotation_error(actual[3:],Rotation.from_matrix(expected_R).as_quat(scalar_first=True))<=TOLERANCES['angle_rad'][0]:
                        binding_reason='native initial pose differs from bound world';break
                if not close(W[:3,:3]@compiled['environment']['gravity_m_s2'],session.get('environment',{}).get('gravity_m_s2',[]),'acceleration_m_s2'):
                    binding_reason='backend environment differs from bound world'
    allowed_targets=set(objects) | {r['id'] for r in (compiled or {}).get('relations',[])}
    missing_targets=[n for n in test.get('targets',[]) if isinstance(n,str) and n not in allowed_targets]
    mapping = session.get("native_entity_names", {})
    def name(n):
        return mapping.get(n, n)
    for i, spec in enumerate(test.get("checks", [])):
        item = dict(id=spec.get("id", f"check-{i}"), type=spec.get("type"), outcome="not_calculated",
                    criterion=spec, reason=None, value=None)
        checks.append(item)
        if not spec.get("source_ref"):
            item["reason"] = "criterion has no input/assumption source"
            continue
        if missing or not valid or missing_targets or binding_reason or operation_reason:
            item["reason"] = operation_reason or binding_reason or "missing/empty/inconsistent raw evidence or targets: " + str(missing+missing_targets)
            continue
        entity = spec.get("entity")
        if entity is not None and entity not in objects:
            item["reason"] = "missing entity " + entity
            continue
        try:
            kind = spec["type"]
            passed = None
            if kind=='relation_process':
                from enrealworld.utils.validation.process_checks import evaluate_relation
                process=evaluate_relation(spec,rows,contacts,native,session)
                item.update(process);continue
            if kind == "complete_interaction":
                from enrealworld.utils.validation.interaction_contract import evaluate as evaluate_interaction
                item.update(evaluate_interaction(spec,rows,contacts,native,session));continue
            if kind == "finite_states":
                passed, item["value"] = True, len(rows)
            elif kind == "continuous_session":
                item['value']=dict(session_ref=session.get('session_ref'),steps=session.get('steps'),sample_clock_continuous=True)
                item['reason']='raw clock continuity observed; absence of callback resets/state overrides/attachments requires independent controller-source audit'
                continue
            elif kind == 'sample_clock_continuity':
                passed=bool(session.get('session_ref'));item['value']=dict(session_ref=session.get('session_ref'),samples=len(rows))
            elif kind == "lift":
                xyz = objects[entity]["poses"][:, :3]
                axis = np.asarray(spec["up_axis"], float)
                if not np.isclose(np.linalg.norm(axis), 1):
                    raise ValueError("unit up_axis required")
                item["value"] = float((xyz[-1]-xyz[0]) @ axis)
                passed = item["value"] >= spec["min_m"]
            elif kind == "rest":
                duration = spec["window_s"]
                if t[-1]-t[0] < duration:
                    item["reason"] = "insufficient time window"
                    continue
                window = t >= t[-1]-duration
                linear = np.linalg.norm(objects[entity]["v"][window], axis=1)
                angular = np.linalg.norm(objects[entity]["w"][window], axis=1)
                item["value"] = dict(max_linear_m_s=float(linear.max()), max_angular_rad_s=float(angular.max()), samples=int(window.sum()))
                passed = linear.max() <= spec["max_linear_m_s"] and angular.max() <= spec["max_angular_rad_s"]
            elif kind in ("robot_penetration", "penetration"):
                robot_names = set(spec.get("robot_link_names", []))
                if kind == "robot_penetration" and not robot_names:
                    item["reason"] = "explicit robot link names required"
                    continue
                relevant = [c for c in contacts if kind == "penetration" or c["body0"] in robot_names or c["body1"] in robot_names]
                values = [-c["separation_m"] for c in relevant]
                item["value"] = dict(max_depth_m=max([0.] + values),
                    worst_contact=max(relevant, key=lambda c:-c["separation_m"]) if relevant else None,
                    contact_points=len(relevant), scope="native contact separation at recorded physics steps; not complete triangle intersection")
                passed = item["value"]["max_depth_m"] <= spec["max_m"]
                if not session.get("contact_recording_complete", False):
                    item["reason"] = "contact export completeness not established"
                    continue
            elif kind == "grasp_contact":
                links = set(spec["finger_link_names"])
                by_time={}
                for c in contacts:
                    if (entity in (name(c["body0"]),name(c["body1"])) and
                        np.linalg.norm(c["impulse_N_s"])>spec["min_impulse_N_s"]):
                        link=c["body0"] if name(c["body1"])==entity else c["body1"]
                        by_time.setdefault(c['time_s'],set()).add(link)
                longest=count=0
                for row in rows:
                    if links and links<=by_time.get(row['time_s'],set()):count+=1
                    else:count=0
                    longest=max(longest,count)
                duration=longest/session['physics_hz']
                item["value"] = dict(longest_bilateral_contact_s=duration,required_links=sorted(links))
                passed=bool(links) and duration>=spec['min_hold_s']
            elif kind == "parameter_consumption":
                expected = compiled_entities.get(entity)
                actual = native.get(entity)
                if not expected or not actual or actual["motion_mode"] != "dynamic":
                    item["reason"] = "dynamic native and original build parameters required"
                    continue
                quantities=dict(mass_kg='mass_kg',center_of_mass_m='position_m',inertia_tensor_kg_m2='inertia_kg_m2')
                comparisons={key:close(actual[key],expected[key],quantity) for key,quantity in quantities.items()}
                item['mapping_policy']='mapping/2; independent dimensional readback, legacy common atol/rtol not used'
                comparisons["shape_count"] = len(actual["collision_shapes"]) == len(expected["collision_parts"])
                if session.get('backend')=='mujoco':
                    comparisons['friction']=bool(actual['collision_shapes']) and all(close(s['dynamic_friction'],expected['contact']['dynamic_friction'],'dimensionless') for s in actual['collision_shapes'])
                    item['mapping_limits']='sliding friction only; distinct static friction/restitution are not measured as equivalent'
                else:
                    comparisons["friction"] = bool(actual['collision_shapes']) and all(close([s["static_friction"],s["dynamic_friction"],s["restitution"]],
                        [expected["contact"]["static_friction"],expected["contact"]["dynamic_friction"],expected["contact"]["restitution"]], "dimensionless") for s in actual["collision_shapes"])
                item["value"], passed = comparisons, bool(comparisons) and all(comparisons.values())
            elif kind == 'geometry_consumption':
                from enrealworld.utils.geometry import arrays
                from scipy.optimize import linear_sum_assignment
                actual=native_shapes(native[entity]);expected=compiled_entities[entity]['collision_parts']
                if not actual or len(actual)!=len(expected):
                    passed=False;item['value']='shape count mismatch'
                else:
                    originals=[arrays(Path(build_dir)/path)[0] for path in expected]
                    distances=np.array([[convex_solid_distance(v,o) for o in originals] for v in actual])
                    # A perfect matching of acceptable pairs tolerates collider ordering
                    # but cannot hide missing pieces or merge a decomposition into one hull.
                    rows_match, cols_match=linear_sum_assignment(distances > spec['max_m'])
                    errors=distances[rows_match,cols_match]
                    item['value']=dict(max_convex_solid_error_m=float(errors.max()),
                        matched_parts=cols_match.tolist(), scope='bidirectional convex solid Hausdorff per collider in entity frame',
                        repair='Preserve source shape and decomposition; inspect native scale/local pose and cooking. Redundant/interior/reordered vertices need no repair.')
                    passed=bool(np.all(errors<=spec['max_m']))
            elif kind == 'joint_consumption':
                actual=session.get('native_joints',{}).get(spec['relation']);rel=next((r for r in (compiled or {}).get('relations',[]) if r['id']==spec['relation']),None)
                if not actual or not rel:
                    item['reason']='actual native joint readback missing';continue
                parent=compiled_entities[rel['parent']['node']];axis=Rotation.from_quat(parent['pose']['quaternion_wxyz'],scalar_first=True).apply(rel['joint']['axis_in_parent'])
                linear=rel['joint']['type']=='prismatic'
                q='position_m' if linear else 'angle_rad';v='velocity_m_s' if linear else 'angular_velocity_rad_s'
                comparisons=dict(axis=close(axis,actual['axis_world'],'dimensionless'),limits=close(rel['joint']['limits'],actual['limits'],q),
                    damping=close(rel['joint']['damping'],actual['damping'],'linear_damping_N_s_m' if linear else 'angular_damping_Nm_s_rad'),
                    position=close(rel['initial_state']['position'],actual['initial_position'],q),velocity=close(rel['initial_state']['velocity'],actual['initial_velocity'],v))
                item['mapping_policy']='mapping/2; joint units chosen by prismatic/revolute type'
                item['value']={k:bool(v) for k,v in comparisons.items()};passed=all(comparisons.values())
            elif kind in ('joint_limits','joint_motion'):
                relation=spec['relation'];series=[r.get('joints',{}).get(relation) for r in rows]
                declared=next((r for r in (compiled or {}).get('relations',[]) if r['id']==relation and r['type']=='joint'),None)
                if not declared or not all(x is not None for x in series):
                    item['reason']='missing declared joint or full joint trajectory';continue
                values=np.asarray([x['position'] for x in series],float)
                if not np.isfinite(values).all():raise ValueError('nonfinite joint state')
                if kind=='joint_limits':
                    lo,hi=declared['joint']['limits'];excess=max(float((lo-values).max()),float((values-hi).max()),0.)
                    item['value']=dict(max_violation=excess,unit=declared['initial_state']['unit'],samples=len(values));passed=excess<=spec['tolerance']
                else:
                    phases=[r['phase'] for r in rows];mask=np.array([p==spec['phase'] for p in phases])
                    if not mask.any():item['reason']='action phase not observed';continue
                    if spec.get('metric','range')=='final':value=float(values[mask][-1])
                    else:value=float(np.ptp(values[mask]))
                    item['value']=value;passed=spec['minimum']<=value<=spec['maximum']
            elif kind == 'fixed_body':
                positions=objects[entity]['poses'][:,:3];rotations=Rotation.from_quat(objects[entity]['poses'][:,3:],scalar_first=True)
                drift=float(np.linalg.norm(positions-positions[0],axis=1).max());angle=float((rotations[0].inv()*rotations).magnitude().max())
                item['value']=dict(max_translation_m=drift,max_rotation_rad=angle,samples=len(rows));passed=drift<=spec['max_translation_m'] and angle<=spec['max_rotation_rad']
            elif kind == 'displacement':
                xyz=objects[entity]['poses'][:,:3];value=float((xyz[-1]-xyz[0])@np.asarray(spec['axis'],float))
                item['value']=value;passed=spec['minimum_m']<=value<=spec['maximum_m']
            elif kind == "functional_space":
                item["value"] = free_space_samples(native_shapes(native[entity]), spec["points_asset_local_m"])
                passed = item["value"]["passed"]
            elif kind == "independent_body":
                if session.get('backend')=='mujoco':
                    if 'native_free_joint' not in native[entity]:
                        item['reason']='native DOF/constraint evidence missing';continue
                    passed=native[entity]['native_free_joint'] and native[entity]['native_equality_constraints']==0
                    item['value']={k:native[entity][k] for k in ('native_free_joint','native_joint_count','native_equality_constraints')}
                    item['scope']='independent free body with no model equality constraints; constrained/partial-DOF independence not certified'
                else:
                    passed = native[entity]["motion_mode"] == "dynamic"
                    item["value"] = native[entity]["motion_mode"]
            elif kind == "initial_relations":
                if not compiled or not compiled["relations"]:
                    item["reason"]="no declared relations to validate";continue
                selected=spec.get('relation_ids')
                description=dict(compiled)
                if selected is not None:
                    description['relations']=[r for r in compiled['relations'] if r['id'] in selected]
                    if {r['id'] for r in description['relations']}!=set(selected):
                        item['reason']='requested relation missing';continue
                result=initial_relations(description,native,rows[0]);item["value"]=result
                if any(r['outcome']=='fail' for r in result):
                    item['outcome']='fail';continue
                if any(r["outcome"]=="not_calculated" for r in result):
                    item["reason"]="some relations need additional applicable tests";continue
                passed=bool(result) and all(r["outcome"]=="pass" for r in result)
            else:
                item["reason"] = "unimplemented check; agent may add a task-local verified measurement"
                continue
            item["outcome"] = "pass" if passed else "fail"
        except (KeyError, ValueError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
            item.update(outcome="not_calculated", reason=str(exc))
    result = dict(execution_mode="readback" if readback else "dynamic",behavior_passed=None,protocol="enrealworld-evaluation/1", operations_verified=operations_verified, test_id=test["id"],
                  test_sha256=hashlib.sha256(json.dumps(test, sort_keys=True).encode()).hexdigest(),
                  evidence_refs={str((root/n).resolve().relative_to(Path(task_root).resolve())) if task_root else str((root/n).resolve()): digest(root/n) for n in names if (root/n).is_file()},
                  checks=checks, outcome="fail" if any(c["outcome"]=="fail" for c in checks)
                  else "not_calculated" if not checks or any(c["outcome"] in ("not_calculated","unsupported") for c in checks) else "pass",
                  limits=["sampled native state/contact evidence", "no continuous surface-intersection or real-world accuracy proof"])
    save(output, result)
    return result
