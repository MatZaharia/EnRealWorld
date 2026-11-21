"""SAPIEN native actor construction and readback."""
from pathlib import Path
import json
import math
import numpy as np
from scipy.spatial.transform import Rotation
from enrealworld.utils.files import save, digest



def create_actor(scene, entity, resources, *, enable_visual=False):
    """Build one native rigid actor; convex pieces never become separate bodies."""
    import sapien
    from importlib.metadata import version
    if version("sapien").split(".")[0] != "3":
        raise ValueError("unsupported SAPIEN major version; actual=" + version("sapien"))
    c = entity["contact"]
    material = sapien.physx.PhysxMaterial(c["static_friction"], c["dynamic_friction"], c["restitution"])
    builder = scene.create_actor_builder()
    # Native collider defaults do not drive explicit authoritative mass properties.
    density = entity.get("density_kg_m3")
    if density is not None and (isinstance(density, bool) or not math.isfinite(density) or density <= 0):
        raise ValueError("collision density must be finite and positive when supplied")
    density_args = {} if density is None else {"density": density}
    shapes=entity.get("native_collision_shapes")
    for index,filename in enumerate(entity["collision_parts"]):
        if shapes:
            shape=shapes[index]
            if shape['geometry']['kind']!='box':raise ValueError('unsupported native collision primitive')
            pose=shape['pose']
            builder.add_box_collision(pose=sapien.Pose(p=pose['position_m'],q=pose['quaternion_wxyz']),
                half_size=np.asarray(shape['geometry']['size_m'])/2,material=material,**density_args)
        else:
            builder.add_convex_collision_from_file(filename=str(Path(resources) / filename), material=material,
                                                  **density_args)
    if enable_visual:
        builder.add_visual_from_file(filename=str(Path(resources) / entity["visual"]))
    # Diagonalize the declared symmetric tensor; eigenvectors define the COM frame.
    tensor = np.asarray(entity["inertia_tensor_kg_m2"])
    values, axes = np.linalg.eigh(tensor)
    # Eigenvectors can form a reflection; flip one axis to obtain a rotation.
    if np.linalg.det(axes) < 0:
        axes[:, 0] *= -1
    cmass = sapien.Pose(p=entity["center_of_mass_m"], q=Rotation.from_matrix(axes).as_quat(scalar_first=True))
    if entity["motion_mode"] == "dynamic":
        builder.set_mass_and_inertia(entity["mass_kg"], cmass, values)
    p = entity["pose"]
    builder.initial_pose = sapien.Pose(p=p["position_m"], q=p["quaternion_wxyz"])
    actor = builder.build_static(name=entity["id"]) if entity["motion_mode"] == "static" else builder.build(name=entity["id"])
    if entity["motion_mode"] == "dynamic":
        body = actor if hasattr(actor, "set_linear_velocity") else actor.find_component_by_type(sapien.physx.PhysxRigidDynamicComponent)
        body.set_linear_velocity(entity["initial_state"]["linear_velocity_m_s"])
        body.set_angular_velocity(entity["initial_state"]["angular_velocity_rad_s"])
    return actor


def build_into_scene(scene, build_dir, *, enable_visual=False):
    """Use a caller-owned native scene; controller and robot remain external."""
    root = Path(build_dir)
    build = json.loads((root / "build.json").read_text())
    if not build["backend_ready"]:
        raise ValueError("refusing a not-ready/failed collision candidate")
    actors = {}
    for entity in build["entities"]:
        actors[entity["id"]] = create_actor(scene, entity, root, enable_visual=enable_visual)
    return actors


def native_actor(actor, motion_mode):
    import sapien
    dynamic = motion_mode == "dynamic"
    cls = sapien.physx.PhysxRigidDynamicComponent if dynamic else sapien.physx.PhysxRigidStaticComponent
    component = (actor._objs[0] if hasattr(actor, "_objs") else actor).find_component_by_type(cls)
    shapes = []
    for sh in component.get_collision_shapes():
        p = sh.local_pose
        material = sh.physical_material
        if hasattr(sh, "vertices"):
            vertices, scale = np.asarray(sh.vertices), np.asarray(sh.scale)
        elif hasattr(sh, "half_size"):
            vertices = np.array([[x,y,z] for x in (-1,1) for y in (-1,1) for z in (-1,1)]) * np.asarray(sh.half_size)
            scale = np.ones(3)
        else:
            raise ValueError("native readback geometry not implemented: " + type(sh).__name__)
        shapes.append(dict(primitive_type="box" if hasattr(sh,"half_size") else "mesh",vertices=vertices.tolist(), scale=scale.tolist(),
            local_position_m=np.asarray(p.p).tolist(), local_quaternion_wxyz=np.asarray(p.q).tolist(),
            static_friction=float(material.static_friction), dynamic_friction=float(material.dynamic_friction),
            restitution=float(material.restitution), density_kg_m3=float(sh.density),
            contact_offset_m=float(sh.contact_offset), rest_offset_m=float(sh.rest_offset)))
    result = dict(motion_mode=motion_mode, collision_shapes=shapes)
    if dynamic:
        p = component.cmass_local_pose
        # Reconstruct the tensor in the asset frame for independent comparison
        # with the original full inertia tensor.
        axes = Rotation.from_quat(np.asarray(p.q), scalar_first=True).as_matrix()
        result.update(mass_kg=float(component.mass), center_of_mass_m=np.asarray(p.p).tolist(),
            principal_inertia_kg_m2=np.asarray(component.inertia).tolist(),
            inertia_tensor_kg_m2=(axes @ np.diag(component.inertia) @ axes.T).tolist(),
            auto_compute_mass=bool(component.auto_compute_mass),
            mass_policy=("collider density drives native mass/COM/inertia; verify against authoritative asset values"
                         if component.auto_compute_mass else
                         "explicit authoritative mass/COM/tensor; collider density does not recompute them"))
    return result


class PersistentSession:
    """One continuous world with raw state/contact export; no resetting per action.

    Caller supplies the step function and optional robot state observer. This
    class has no built-in robot, IK, task solver, thresholds or success flag.
    """

    def __init__(self, scene, actors, modes, step, output, *, hz, environment,
                 robot_observer=None, input_refs=None, build_dir=None, world_to_session=None):
        import uuid
        from importlib.metadata import version
        self.scene, self.actors, self.modes = scene, actors, modes
        self.step_native, self.robot_observer = step, robot_observer
        self.output, self.hz, self.steps = Path(output), hz, 0
        self.output.mkdir(parents=True, exist_ok=False)
        self.rows, self.contacts = [], []
        self.identity = uuid.uuid4().hex
        self.info = dict(session_ref=self.identity, backend="sapien", version=version("sapien"),
                         physics_hz=hz, environment=environment, input_refs=input_refs or {},
                         resets_during_actions=None, state_overrides_during_actions=None,
                         object_attachments_during_actions=None, contact_recording_complete=True,
                         instrumentation_limits='arbitrary callbacks are not intercepted; source audit required for reset/override/attachment absence',
                         stages=dict(generated=True, loaded=True, ran=False))
        self.info["native_entity_names"] = {a._objs[0].name: n for n, a in actors.items()}
        if build_dir is not None:
            path=Path(build_dir);description=json.loads((path/'build.json').read_text())
            resources=sorted({e[role] for e in description['entities'] for role in ('reference','visual')} |
                             {p for e in description['entities'] for p in e['collision_parts']})
            self.info['world_binding']=dict(build_sha256=digest(path/'build.json'),
                resources={n:digest(path/n) for n in resources},
                world_to_session=np.eye(4).tolist() if world_to_session is None else np.asarray(world_to_session).tolist())
        self.native = {n: native_actor(a, modes[n]) for n, a in actors.items()}
        self.record("initial")

    def record(self, phase):
        values = []
        for name, actor in self.actors.items():
            p = actor.pose
            v = actor.linear_velocity[0].cpu().numpy() if self.modes[name] == "dynamic" else np.zeros(3)
            w = actor.angular_velocity[0].cpu().numpy() if self.modes[name] == "dynamic" else np.zeros(3)
            values.append(dict(name=name, pose=np.r_[p.p[0].cpu().numpy(), p.q[0].cpu().numpy()].tolist(),
                               linear_velocity_m_s=v.tolist(), angular_velocity_rad_s=w.tolist()))
        robot = self.robot_observer() if self.robot_observer else None
        self.rows.append(dict(time_s=self.steps/self.hz, phase=phase, objects=values, robot=robot))
        # Every simulated step, including zero-impulse contact envelope points.
        for contact in self.scene.sub_scenes[0].get_contacts():
            for point in contact.points:
                self.contacts.append(dict(time_s=self.steps/self.hz, phase=phase,
                    body0=contact.bodies[0].entity.name, body1=contact.bodies[1].entity.name,
                    position_m=np.asarray(point.position).tolist(), normal=np.asarray(point.normal).tolist(),
                    separation_m=float(point.separation), impulse_N_s=np.asarray(point.impulse).tolist()))

    def advance(self, count, *, phase, control=None):
        if count < 1:
            raise ValueError("positive continuous step count required")
        for _ in range(count):
            if control:
                control()
            self.step_native()
            self.steps += 1
            self.record(phase)

    def finish(self, destination=None):
        output = Path(destination) if destination is not None else self.output
        if any((output/n).exists() for n in ("native.json", "states.json", "contacts.json", "session.json")):
            raise ValueError("raw checkpoint already exported; use a new destination for continued session")
        output.mkdir(parents=True, exist_ok=True)
        save(output / "native.json", self.native)
        save(output / "states.json", self.rows)
        save(output / "contacts.json", self.contacts)
        self.info["stages"]["ran"] = self.steps > 0
        self.info.update(steps=self.steps, duration_s=self.steps/self.hz, samples=len(self.rows),
                         behavior_passed=None, raw_hashes={k: digest(output/k) for k in ("native.json", "states.json", "contacts.json")})
        save(output / "session.json", self.info)
        return self.info
