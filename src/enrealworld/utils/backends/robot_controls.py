"""Validated, opt-in scalar URDF drive policy; no task-specific assumptions."""
import math
import xml.etree.ElementTree as ET


def policy(robot):
    tree = ET.fromstring(robot['urdf'])
    joints = {j.get('name'): j for j in tree.findall('joint')}
    active = {n: j for n, j in joints.items() if j.get('type') != 'fixed'}
    mimic = {}
    for name, joint in joints.items():
        node = joint.find('mimic')
        if node is None: continue
        parent = node.get('joint')
        if parent not in active or name not in active:
            raise ValueError('unknown or nonscalar mimic joint')
        if joint.get('type') not in ('prismatic', 'revolute', 'continuous') or active[parent].get('type') not in ('prismatic', 'revolute', 'continuous'):
            raise ValueError('only scalar mimic joints supported')
        a, b = float(node.get('multiplier', '1')), float(node.get('offset', '0'))
        if not all(map(math.isfinite, (a,b))): raise ValueError('finite mimic coefficients required')
        mimic[name] = (parent,a,b)
    if mimic and robot.get('mimic_mode') != 'synchronized_drive':
        raise ValueError('mimic requires explicit synchronized_drive mode')
    # Collapse each mimic chain to target = a * root + b, rejecting cycles.
    resolved = {}
    def resolve(name, visiting):
        if name in visiting: raise ValueError('mimic cycle')
        if name in resolved: return resolved[name]
        if name not in mimic: return name,1.,0.
        parent,a,b = mimic[name]
        root,c,d = resolve(parent, visiting | {name})
        resolved[name] = root,a*c,a*d+b
        return resolved[name]
    intervals = {}
    for name, joint in active.items():
        limit = joint.find('limit')
        intervals[name] = (-math.inf, math.inf) if joint.get('type') == 'continuous' else (float(limit.get('lower')), float(limit.get('upper')))
    # Project child limits back onto the root joint and intersect all bounds.
    feasible = dict(intervals)
    for name in mimic:
        root,a,b = resolve(name,set())
        lo,hi = intervals[name]
        if a == 0:
            if not lo <= b <= hi: raise ValueError('mimic limit conflict')
        else:
            x,y = sorted(((lo-b)/a,(hi-b)/a))
            l,h = feasible[root]; feasible[root] = max(l,x),min(h,y)
            if feasible[root][0] > feasible[root][1]: raise ValueError('mimic limit conflict')
    for name, gains in robot.get('joint_drives', {}).items():
        if name not in active or set(gains)-{'stiffness','damping','force_limit'}: raise ValueError('unknown joint drive configuration')
        for key,value in gains.items():
            if not math.isfinite(value) or value < 0 or (key == 'force_limit' and value == 0): raise ValueError('invalid joint drive gain')
    if type(robot.get('passive_force_compensation',False)) is not bool: raise ValueError('passive compensation must be boolean')
    links = {l.get('name') for l in tree.findall('link')}
    pairs = robot.get('self_collision_exclusions', [])
    seen = set()
    if len(pairs) > 32: raise ValueError('at most 32 explicit collision pairs supported')
    for pair in pairs:
        names = pair['links']
        if len(names)!=2 or len(set(names))!=2 or not set(names)<=links or not pair.get('source_ref'):
            raise ValueError('explicit internal link pair and source_ref required')
        key = tuple(sorted(names))
        if key in seen: raise ValueError('duplicate collision pair')
        seen.add(key)
    return resolved, feasible


def targets(values, current, resolved, limits):
    result = dict(current); result.update(values)
    for name,(root,a,b) in resolved.items():
        expected = a*result[root]+b
        if name in values and not math.isclose(values[name], expected, abs_tol=1e-8): raise ValueError('conflicting mimic target')
        result[name] = expected
    for name,value in result.items():
        lo,hi = limits[name]
        if not math.isfinite(value) or not lo <= value <= hi: raise ValueError('joint target outside mimic/native limits')
    return result
