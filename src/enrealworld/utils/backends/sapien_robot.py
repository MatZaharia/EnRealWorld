"""Opt-in primitive URDF articulation adapter. Task-local shim selects this API."""
from pathlib import Path
import json
import base64
import hashlib
import xml.etree.ElementTree as ET
import numpy as np
from . import sapien_cpu as rigid
from .robot_controls import policy, targets as resolve_targets
from enrealworld.utils.files import save, digest
BACKEND = 'sapien'
CAPABILITIES = rigid.CAPABILITIES | {'robot_control'}
ACTIONS = rigid.ACTIONS | {'joint_target', 'tool_position', 'tool_pose'}
PRODUCTS = rigid.PRODUCTS + ('robot.urdf', 'robot-source.urdf')
probe = rigid.probe


def validate(config):
    robot = config['robot']
    tree = ET.fromstring(robot['urdf'])
    if tree.tag != 'robot': raise ValueError('URDF robot required')
    resources = robot.get('resources', {})
    for name, resource in resources.items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or name in ('robot.urdf','backend-config.json','build.json'):
            raise ValueError('task-local robot resource path required')
        data = base64.b64decode(resource['base64'], validate=True)
        if hashlib.sha256(data).hexdigest() != resource['sha256']: raise ValueError('robot resource hash mismatch')
    for mesh in tree.findall('.//mesh'):
        if mesh.get('filename') not in resources: raise ValueError('URDF mesh requires declared local resource')
    for key in ('qpos', 'root_pose', 'stiffness', 'damping', 'force_limit'):
        a = np.asarray(robot[key], float)
        if not np.isfinite(a).all(): raise ValueError('finite robot '+key+' required')
    if len(robot['root_pose']) != 7 or not np.isclose(np.linalg.norm(robot['root_pose'][3:]), 1):
        raise ValueError('root_pose requires xyz + unit wxyz')
    if min(robot['stiffness'], robot['damping']) < 0 or robot['force_limit'] <= 0:
        raise ValueError('nonnegative gains and positive force limit required')
    policy(robot)
    return robot


def materialized_tree(robot):
    tree = ET.fromstring(robot['urdf'])
    # Physics-only materialization: never ask the URDF loader to create renderers.
    for link in tree.findall('link'):
        for visual in link.findall('visual'): link.remove(visual)
    for joint in tree.findall('joint'):
        for mimic in joint.findall('mimic'): joint.remove(mimic)
    for mesh in tree.findall('.//mesh'):
        mesh.set('filename', 'robot-resources/'+mesh.get('filename'))
    return tree


def build(build_dir, config):
    robot = validate(config)
    root = Path(build_dir)
    for name, resource in robot.get('resources', {}).items():
        destination = root/'robot-resources'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(resource['base64'], validate=True))
    tree = materialized_tree(robot)
    (root/'robot.urdf').write_text(ET.tostring(tree, encoding='unicode'))
    # Configuration retains original model bytes; materialized XML is separately hashed.
    (root/'robot-source.urdf').write_text(robot['urdf'])
    save(root/'backend-config.json', config)
    Session(root, root/'native-readback').finish()


class Session(rigid.Session):
    def __init__(self, build_dir, output):
        self.robot = None
        super().__init__(build_dir, output)
        import sapien
        cfg = validate(self.config)
        if (self.root/'robot-source.urdf').read_text() != cfg['urdf']:
            raise ValueError('robot URDF differs from configuration; rebuild')
        expected_tree = materialized_tree(cfg)
        if (self.root/'robot.urdf').read_text() != ET.tostring(expected_tree, encoding='unicode'):
            raise ValueError('materialized robot URDF differs from configuration; rebuild')
        loader = self.scene.create_urdf_loader()
        loader.fix_root_link = cfg['fix_root_link']
        self.robot = loader.load(str(self.root/'robot.urdf'))
        if self.robot is None: raise ValueError('native URDF load failed')
        self.robot.set_root_pose(sapien.Pose(cfg['root_pose'][:3], cfg['root_pose'][3:]))
        self.joints = {j.name: j for j in self.robot.get_active_joints()}
        if any(j.dof != 1 for j in self.joints.values()): raise ValueError('only scalar active joints supported')
        if len(cfg['qpos']) != len(self.joints): raise ValueError('qpos dimension mismatch')
        self.mimic, self.control_limits = policy(cfg)
        self.drive_targets = resolve_targets(dict(zip(self.joints,cfg['qpos'])), {}, self.mimic, self.control_limits)
        self.robot.set_qpos(cfg['qpos'])
        for joint, q in zip(self.joints.values(), cfg['qpos']):
            gains = {k:cfg.get('joint_drives',{}).get(joint.name,{}).get(k,cfg[k]) for k in ('stiffness','damping','force_limit')}
            joint.set_drive_properties(**gains)
            joint.set_drive_target(q)
        self._configure_collision_pairs(cfg)
        self.programs['robot-source.urdf'] = digest(self.root/'robot-source.urdf')
        for name, resource in cfg.get('resources', {}).items():
            relative = 'robot-resources/'+name
            if digest(self.root/relative) != resource['sha256']: raise ValueError('robot resource changed')
            self.programs[relative] = resource['sha256']
        self.programs['robot.urdf'] = digest(self.root/'robot.urdf')
        self.rows = []; self.record('initial')

    def _configure_collision_pairs(self, cfg):
        links = {link.name:link for link in self.robot.get_links()}
        pairs = cfg.get('self_collision_exclusions',[])
        if not pairs: return
        shapes = [s for link in self.robot.get_links() for s in link.get_collision_shapes()]
        used = 0
        for shape in shapes: used |= shape.get_collision_groups()[2]
        available = [1 << i for i in range(32) if not used & (1 << i)]
        if len(pairs)>len(available): raise ValueError('insufficient collision filter bits')
        for pair,bit in zip(pairs,available):
            selected = [s for name in pair['links'] for s in links[name].get_collision_shapes()]
            if len({s.get_collision_groups()[3] & 0xffff for s in selected})>1:
                raise ValueError('native pair filter IDs differ')
            for shape in selected:
                groups = list(shape.get_collision_groups()); groups[2] |= bit
                shape.set_collision_groups(groups)

    def step_physics(self):
        if self.config['robot'].get('passive_force_compensation',False):
            self.robot.set_qf(self.robot.compute_passive_force(gravity=True, coriolis_and_centrifugal=True))
        self.scene.step()

    def record(self, phase):
        super().record(phase)
        if self.robot is not None:
            self.rows[-1]['joints'] = {name: dict(position=float(q), velocity=float(v)) for name, q, v in zip(self.joints, self.robot.get_qpos(), self.robot.get_qvel())}
            self.rows[-1]['robot_links'] = {link.name: np.r_[link.pose.p, link.pose.q].tolist() for link in self.robot.get_links()}

    def advance(self, action):
        if action['type'] == 'tool_pose':
            import sapien
            if set(action)-{'type','pose','duration_s','phase','gripper_targets'}: raise ValueError('unsupported tool_pose fields')
            ik = self.config['robot']['ik']
            links = [link.name for link in self.robot.get_links()]
            pose = np.asarray(action['pose'], float)
            if pose.shape != (7,) or not np.isfinite(pose).all() or not np.isclose(np.linalg.norm(pose[3:]),1): raise ValueError('pose requires xyz unit wxyz')
            target = self.robot.get_root_pose().inv() * sapien.Pose(pose[:3],pose[3:])
            model = self.robot.create_pinocchio_model()
            q, success, error = model.compute_inverse_kinematics(links.index(ik['link']), target, initial_qpos=self.robot.get_qpos(), active_qmask=np.asarray(ik['active_qmask'], dtype=np.int32), eps=ik['eps'], max_iterations=ik['max_iterations'])
            if not success: raise ValueError('native IK failed: '+str(error))
            targets = {name:float(value) for name,value,active in zip(self.joints,q,ik['active_qmask']) if active}
            fingers = action.get('gripper_targets',{})
            if set(fingers) & targets.keys(): raise ValueError('gripper cannot override IK joints')
            targets.update(fingers)
            converted = dict(type='joint_target',targets=targets,duration_s=action['duration_s'],phase=action.get('phase','tool_pose'))
            start = len(self.operations); self.advance(converted)
            self.operations[start].update(action=action,resolved_joint_action=converted,ik_error=np.asarray(error).tolist())
            return
        if action['type'] == 'tool_position':
            if set(action)-{'type','position_m','gripper_targets','duration_s','phase'}: raise ValueError('unsupported tool_position fields')
            mapping = self.config['robot']['cartesian_mapping']
            position = np.asarray(action['position_m'], float)
            if position.shape != (3,) or not np.isfinite(position).all(): raise ValueError('finite xyz required')
            matrix = np.asarray(mapping['axes'], float).T
            delta = position - np.asarray(mapping['origin_m'], float)
            q, *_ = np.linalg.lstsq(matrix, delta, rcond=None)
            if not np.allclose(matrix @ q, delta, atol=1e-8): raise ValueError('unreachable Cartesian target')
            targets = dict(zip(mapping['joints'], q.tolist()))
            fingers = action.get('gripper_targets', {})
            if set(fingers) & targets.keys(): raise ValueError('gripper cannot override Cartesian joints')
            targets.update(fingers)
            converted = dict(type='joint_target', targets=targets, duration_s=action['duration_s'], phase=action.get('phase','tool_position'))
            start = len(self.operations)
            self.advance(converted)
            self.operations[start]['action'] = action
            self.operations[start]['resolved_joint_action'] = converted
            return
        if action['type'] != 'joint_target': return super().advance(action)
        if self.finished: raise ValueError('session finalized')
        if set(action)-{'type','targets','duration_s','phase'}: raise ValueError('unsupported joint_target fields')
        targets = action['targets']
        if not targets or set(targets)-self.joints.keys(): raise ValueError('unknown/empty joint targets')
        count = round(action['duration_s']/self.dt)
        if count < 1 or not np.isclose(count*self.dt, action['duration_s'], atol=1e-12): raise ValueError('duration must align with timestep')
        for name, value in targets.items():
            limits = self.joints[name].get_limits()[0]
            if not np.isfinite(value) or not limits[0] <= value <= limits[1]: raise ValueError('joint target outside native limits')
        resolved = resolve_targets(targets, self.drive_targets, self.mimic, self.control_limits)
        self.drive_targets = resolved
        for name, value in resolved.items(): self.joints[name].set_drive_target(value)
        operation = dict(action=action, start_step=self.steps, session_ref=self.id)
        self.operations.append(operation)
        for _ in range(count):
            self.step_physics(); self.steps += 1; self.record(action.get('phase','joint_target'))
        operation['end_step'] = self.steps

    def finish(self):
        info = super().finish()
        info['adapter_sha256'] = digest(__file__)
        info['native_joints'] = {name: dict(qpos=float(q), limits=j.get_limits().tolist()) for (name,j),q in zip(self.joints.items(),self.robot.get_qpos())}
        info['execution_scope'] = dict(controller='caller-configured native joint drives / optional IK', fix_root_link=self.config['robot']['fix_root_link'], root_pose=self.config['robot']['root_pose'], additional_constraints=self.config.get('execution_scope', {}).get('additional_constraints', []), declared=self.config.get('execution_scope', {}), target_environment_equivalence='unverified', grasp_evidence='requires declared contacts/lift/hold criteria; spring hold is not free friction grasp evidence', robot_controls={k:self.config['robot'].get(k) for k in ('mimic_mode','joint_drives','passive_force_compensation','self_collision_exclusions')}, mimic_semantics='affine synchronized targets; independent finite-force drives, not mechanical constraint', rendering='visual nodes omitted; original model retained')
        info['instrumentation_limits'] = 'Native CPU URDF joint drives and sampled links/contacts; native Pinocchio IK when configured; no grasp inference; opt-in affine mimic target synchronization only'
        save(self.output/'session.json', info)
        return info
